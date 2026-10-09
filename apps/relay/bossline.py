"""The boss line: Emerson talks to Relay's boss (the commander) straight
from WhatsApp and gets a real answer back within a minute or two
(Emerson, 2026-10-07: "a more direct line of communication").

Which messages go here: one that starts with "boss" ("boss how long is 63
going to take", "boss: stop the cosmos job"), or every plain message while
the chat mode is boss (the word "boss" on its own switches it on; claude,
desk or local switch back). Everything else is unchanged: commands, the
chat, new: work and tasks.

It is cheap on purpose (memory crew-relaunch-cost): no session stays open.
Each question is ONE lean Claude turn (oneshot.py: no tools, no settings,
own system prompt) that reads a compact State summary (summary(), a few
thousand characters) and the last few boss exchanges, so a turn costs its
own small prompt and nothing more. Its instructions are bossline_prompt.md
(plain text, read on every question). Steering comes back as ACTION lines,
run through the same commands as mail after a guard (allowed()): stop,
retry, pause, resume, tell, say and task. With no account able to launch,
the answer is the plain-Python summary, no model.
"""

from __future__ import annotations

import re
import statistics
import threading
import time
from pathlib import Path
from typing import Callable

import actions
import chat
import commands
import items
import meters
import oneshot
import runs
import store

PROMPT = Path(__file__).with_name("bossline_prompt.md")
MODE = "boss"  # the whatsapp_frontdesk value of the boss chat mode
ACTION = re.compile(r"^\s*\**ACTION\**\s*:?\s*(.+)$", re.I)
# A bare command line outside an ACTION line is never run nor sent.
BARE = re.compile(r"^\s*`*(stop|retry|tell|pause|resume|say|task:)\b.*`*$", re.I)
KEEP = 6  # boss exchanges remembered
ANSWER_CHARS = 2000  # of each remembered answer
RECENT = 15 * 60  # his boss questions this recent still count as asking
SUMMARY_CHARS = 7000
TAIL_LINES = 4
LABEL = "Boss: "

# An action runs only when his own words asked for that kind of thing, not
# under a "don't" (the critic, 2026-10-07: "when will 1 end?" and "don't stop
# anything" both passed an older, looser list).
WORDS = {
    "stop": r"\b(stop|kill|cancel|halt|abort)\b",
    "retry": r"\b(retry|rerun|re-run|restart|(try|run) (it |that |this )?again)\b",
    "pause": r"\b(pause|hold off)\b",
    "resume": r"\b(resume|unpause|carry on|start launching)\b",
    # not "tell me ...", "let me know", "remind me", "did you get my message"
    "tell": r"\b(tell|remind) (?!me\b|us\b)\w|\blet (?!me\b|us\b)\S.{0,30} know\b"
    r"|\bpass (it |this |that )?on\b|\bmessage (?!me\b)(it|them|that|this|the|#?\d)",
    "say": r"\b(post|announce)\b|\b(on|to) the (crew )?board\b"
    r"|\b(tell|let) (everyone|every session|all (the )?sessions|the crew)\b",
    # "email a task", "make taks to fix this", "start a new session to fix it"
    # (Emerson, 2026-10-08; the older list refused all three, task 105), but
    # not "how many open tasks", "is the new session done", "send the job"
    "task": r"\b(queue|kick off|spawn)\b"
    r"|\b(start|add|make|create|open|launch|new|write)\b.{0,20}\b(task|taks|job)\b"
    r"|\b(email|send|give) (me )?(a|an|another|one more) (new |separate )?(task|taks"
    r"|job)\b|\b(start|launch|open|fire up|spin up|spawn|get) (a|an|another|one"
    r"|some) (new |separate |fresh )?(session|helper|agent)\b"
    r"|\bget (claude|a session|an? agent|someone) to\b"
    r"|^(please |can you |could you )?(fix|build|make|add|write|create|run|set up"
    r"|clean|update|change|redo|start)\b",
}
# A number he wrote that may be a task: not "80 percent", "60fps" or "13:00".
BARE_NUMBER = re.compile(
    r"(?<![:.\d])\b(\d+)\b(?![:.]\d|\s*(?:%|per ?cent|fps|k\b|[mg]b\b|mins?\b"
    r"|minutes?|hours?|hrs?\b|h\b|secs?\b|seconds?|s\b|am\b|pm\b|x\b|st\b|nd\b"
    r"|rd\b|th\b))",
    re.I,
)
NEGATED = re.compile(r"\b(don'?t|do not|never|no need to|not)\b[^.?!]{0,25}$", re.I)


def match(text: str) -> str | None:
    """The question in a "boss ..." message, else None."""
    m = commands.BOSS.match(text or "")
    return m.group(1).strip() if m else None


def in_mode(settings: dict | None = None) -> bool:
    return (settings or store.settings()).get("whatsapp_frontdesk") == MODE


# ---- the queue of questions --------------------------------------------------------


def _file() -> Path:
    return store.path("bossline.json")


def _load() -> dict:
    data = store.read_json(_file()) or {}
    return {"waiting": data.get("waiting") or [], "history": data.get("history") or []}


def ask_later(text: str) -> str:
    """Queue a question for the boss process; the answer goes to WhatsApp."""
    data = _load()
    data["waiting"].append({"at": round(time.time()), "q": text.strip()})
    store.write_json(_file(), data)
    store.event("boss", f"boss line asked: {text[:80]}")
    store.poke()
    return ""  # the answer comes by itself


def take() -> list[str]:
    data = _load()
    waiting = [w["q"] for w in data["waiting"] if w.get("q")]
    if waiting:
        data["waiting"] = []
        store.write_json(_file(), data)
    return waiting


def recent(now: float | None = None) -> list[str]:
    """His boss questions of the last RECENT seconds, oldest first."""
    now = now or time.time()
    return [
        h["q"]
        for h in _load()["history"]
        if h.get("q") and now - float(h.get("at") or 0) < RECENT
    ]


def remember(questions: list[str], answer: str) -> None:
    data = _load()
    data["history"].append(
        {
            "at": round(time.time()),
            "q": " / ".join(questions)[:600],
            "a": answer[:ANSWER_CHARS],
        }
    )
    data["history"] = data["history"][-KEEP:]
    store.write_json(_file(), data)


# ---- what the boss knows -----------------------------------------------------------


def _ago(seconds: float) -> str:
    return actions.ago(seconds)


def _typical(tasks: list[dict]) -> str:
    """How long recent tasks took from queued to done: a base for ETAs."""
    done = sorted(
        (
            t
            for t in tasks
            if t.get("status") == "done"
            and items.num(t, "finished") > items.num(t, "created") > 0
        ),
        key=lambda t: items.num(t, "finished"),
    )[-20:]
    took = [(items.num(t, "finished") - items.num(t, "created")) / 60 for t in done]
    if not took:
        return ""
    return (
        f"Typical task time (queued to done, last {len(took)}): median "
        f"{statistics.median(took):.0f} min, longest {max(took):.0f} min."
    )


def _board(settings: dict, count: int = 6) -> list[str]:
    import json

    path = Path.home() / ".claude" / "crew" / settings["board"] / "board.json"
    try:
        notes = json.loads(path.read_text()).get("notes") or []
    except (OSError, ValueError):
        return []
    now = time.time()
    return [
        f"- {n.get('from')} ({_ago(now - float(n.get('t') or now))} ago): "
        + " ".join(str(n.get("text") or "").split())[:180]
        for n in notes[-count:]
    ]


def summary(settings: dict | None = None, now: float | None = None) -> str:
    """Relay right now in a few thousand characters."""
    settings = settings or store.settings()
    now = now or time.time()
    st = store.state()
    lines = [f"Now: {time.strftime('%a %d %b %H:%M', time.localtime(now))}"]
    if settings["paused"]:
        lines.append("Relay is paused: no new launches until resume.")
    if st.get("wait_reason") and st["wait_reason"] != "paused":
        lines.append(f"Launch note: {st['wait_reason']}")
    active = runs.active()
    lines.append(f"Running ({len(active)}):")
    for run in active:
        task = items.find_task(run["task"]) if run.get("task") else None
        info = runs.summary(run)
        if run["kind"] == "chat":
            name = f"#{run['task']} the WhatsApp chat itself (not a work task)"
        elif run.get("task"):
            name = f"#{run['task']} {(task or {}).get('title', '')[:90]}"
        else:
            name = f"planning goal {run.get('goal')}"
        lines.append(
            f"- {name} [{run['kind']}, {run['account']}, {run['effort']}] "
            f"{_ago(now - run['started'])} in, {info['context_tokens'] // 1000}k "
            f"context, last step: {str(info['last_action'] or 'starting')[:120]}"
        )
        tail = actions._state_tail(task, TAIL_LINES) if task else ""
        lines += ["    " + ln.strip()[:200] for ln in tail.splitlines()]
    tasks = items.all_tasks()
    queued = [t for t in tasks if t.get("status") == "queued"]
    lines.append(f"Queued ({len(queued)}):")
    lines += [f"- #{t['id']} {str(t.get('title'))[:90]}" for t in queued[:8]]
    waiting = [t for t in tasks if t.get("status") in ("blocked", "parked")]
    if waiting:
        lines.append("Waiting on Emerson:")
        lines += [
            f"- #{t['id']} {str(t.get('title'))[:80]} ({t.get('status')}: "
            f"{str(t.get('note', ''))[:120]})"
            for t in waiting[:6]
        ]
    done = sorted(
        (
            t
            for t in tasks
            if t.get("status") in ("done", "stopped", "failed")
            and items.num(t, "finished") > now - 12 * 3600
        ),
        key=lambda t: items.num(t, "finished"),
    )[-8:]
    if done:
        lines.append("Ended in the last 12 hours:")
        lines += [
            f"- #{t['id']} {str(t.get('title'))[:80]} ({t.get('status')}, "
            f"{_ago(now - items.num(t, 'finished'))} ago)"
            for t in done
        ]
    typical = _typical(tasks)
    if typical:
        lines.append(typical)
    lines.append("Usage:")
    lines += ["- " + ln for ln in meters.describe(st.get("meters") or {}, settings)]
    board = _board(settings)
    if board:
        lines.append("Latest crew board notes:")
        lines += board
    text = "\n".join(lines)
    return (
        text if len(text) <= SUMMARY_CHARS else text[: SUMMARY_CHARS - 20] + "\n(cut)"
    )


def prompt(questions: list[str], settings: dict | None = None) -> str:
    history = _load()["history"]
    talk = "\n".join(
        f"[{time.strftime('%H:%M', time.localtime(h['at']))}] Emerson: {h['q']}\n"
        f"You: {h['a']}"
        for h in history
    )
    return (
        f"State:\n{summary(settings)}\n\n"
        + (f"Earlier on the boss line:\n{talk}\n\n" if talk else "")
        + "Emerson now:\n"
        + "\n".join(questions)
    )


# ---- one answer --------------------------------------------------------------------


class NoRoom(RuntimeError):
    pass


def answer(questions: list[str], settings: dict, readings: dict) -> str:
    """One lean Claude turn; NoRoom when no account can take it."""
    account, why = oneshot.account_for(readings, settings)
    if not account:
        raise NoRoom(why)
    return oneshot.ask(
        prompt(questions, settings),
        PROMPT.read_text(encoding="utf-8"),
        account,
        model=settings["boss_line_model"],
        effort=settings["boss_line_effort"],
        timeout=150,
    )


def parse(answer_text: str) -> tuple[str, list[str]]:
    """The model's answer -> (text for Emerson, ACTION lines)."""
    text, acts = [], []
    for line in answer_text.strip().splitlines():
        m = ACTION.match(line)
        if m:
            act = m.group(1).strip().strip("`*").strip()
            if act:
                acts.append(act)
        elif not BARE.match(line):
            text.append(line)
    return "\n".join(text).strip(), acts


def _kind(act: str) -> str:
    word = act.split(None, 1)[0].lower().rstrip(":") if act.split() else ""
    return word


def _named(task: dict | None, said: str) -> bool:
    """He named this task by a word of its title ("stop the cosmos job")."""
    if not task:
        return False
    words = set(re.findall(r"[a-z]{4,}", str(task.get("title", "")).lower()))
    return bool((words - COMMON) & set(re.findall(r"[a-z]{4,}", said)))


COMMON = {
    "relay", "forge", "task", "tasks", "with", "from", "that", "this", "them",
    "what", "make", "into", "when", "about", "emerson", "fix", "fixes", "more",
    "also", "should", "still", "work", "working", "very", "last", "thing",
    "done", "running", "then", "there", "their", "they", "have", "just",
}  # fmt: skip


def _asks(kind: str, texts: list[str]) -> bool:
    """One of these texts asks for this kind of action, not under a "don't"."""
    for text in texts:
        found = re.search(WORDS[kind], text, re.M)
        if found and not NEGATED.search(text[: found.start()]):
            return True
    return False


def _refuses(kind: str, texts: list[str]) -> bool:
    """One of these texts says not to ("don't tell 12 yet")."""
    for text in texts:
        found = re.search(WORDS[kind], text, re.M)
        if found and NEGATED.search(text[: found.start()]):
            return True
    return False


def _only_work() -> str:
    """The one running work task's number, "" with none or several."""
    work = [str(r["task"]) for r in runs.active() if r["kind"] == "work"]
    return work[0] if len(work) == 1 else ""


def _numbers(text: str) -> tuple[list[str], list[str]]:
    """(numbers marked as tasks: "#12", "task 12"; other bare numbers)."""
    marked = re.findall(r"(?:#|\btask\s*#?|\bnumber\s*)(\d+)\b", text)
    return marked, BARE_NUMBER.findall(text)


# Kinds that may lean on his boss questions of the last 15 minutes: passing a
# note on, a board note and queuing a task. Stop, pause, resume and retry
# steer running work, so they need his words in this message.
LEANS = ("tell", "say", "task")


def allowed(act: str, questions: list[str], earlier: list[str] | None = None) -> bool:
    """His words asked for this kind of action (not under a "don't"), and a
    task it names is one he gave by number or named by a word of its title;
    for a tell with neither, the only work task running ("tell it ...").

    tell, say and task may also lean on his boss questions of the last 15
    minutes (`earlier`, default recent()): "do it yourself" right after
    "tell it to hand off at 80" (task 105). A "don't" now always wins."""
    kind = _kind(act)
    if kind not in WORDS:
        return False
    now = [q.lower() for q in questions]
    back = [q.lower() for q in (recent() if earlier is None else earlier)]
    if _refuses(kind, now):
        return False
    texts = now + back if kind in LEANS else now
    if not _asks(kind, texts):
        return False
    if kind not in ("stop", "retry", "tell"):
        return True
    number = re.match(r"\S+\s+(?:task\s*)?#?(\d+)", act, re.I)
    if not number:
        return False
    n = number.group(1)
    task = items.find_task(n)
    # this message's numbers first; earlier ones only when it gives none
    for said in [" ".join(now)] + ([" ".join(back)] if kind in LEANS else []):
        marked, bare = _numbers(said)
        if marked or bare:
            return n in (marked or bare)
        if _named(task, said):
            return True
    return kind == "tell" and n == _only_work()


def act(line: str, questions: list[str]) -> str:
    """Run one ACTION line through Relay's own commands; what happened."""
    if not allowed(line, questions):
        store.event("boss", f"boss line action refused: {line[:80]}")
        return f"(Not done: {line[:60]}, you did not ask for that.)"
    kind = _kind(line)
    if kind == "task":
        body = re.sub(r"^\s*task\s*:?\s*", "", line, flags=re.I).strip()
        cmd = commands.parse("", "task: " + body, source="whatsapp")
        if cmd.kind != "task" or not cmd.text.strip():
            return "(No task queued: the request was empty.)"
        task = actions.add_task(cmd, "whatsapp")
        store.event("boss", f"boss line queued task {task['id']}")
        return f"Queued task {task['id']}: {task['title']}."
    cmd = commands.parse("", line, source="whatsapp")
    if cmd.kind not in ("stop", "retry", "pause", "resume", "tell", "say"):
        return f"(Not done: {line[:60]} is not a boss action.)"
    said = actions.apply(cmd, "whatsapp")[0]
    store.event("boss", f"boss line ran: {line[:80]}")
    return said


def run_actions(acts: list[str], questions: list[str]) -> list[str]:
    """Each ACTION line in turn; one that fails says so and the rest go on."""
    done = []
    for line in acts[:4]:
        try:
            done.append(act(line, questions))
        except Exception as e:  # the answer must still reach him
            store.event("boss", f"boss line action failed: {line[:60]}: {e}")
            done.append(f"(Failed: {line[:60]}: {type(e).__name__}.)")
    return done


def deliver(questions: list[str], result: dict) -> str:
    """Send the answer (and what its actions did) to WhatsApp."""
    if "error" in result:
        no_room = result.get("no_room")
        head = (
            "No Claude account can take a question right now"
            if no_room
            else "I could not get a Claude answer just now"
        )
        text = (
            f"{head} ({result['error'][:160]}), so here is the plain state:\n\n"
            + short_state()
            + "\n\nCommands still work: stop 12, tell 12 <note>, pause, resume."
        )
        chat.reply(LABEL + text, who="Boss")
        remember(questions, text)
        return f"boss line answered without Claude: {result['error'][:120]}"
    text, acts = parse(result["answer"])
    done = run_actions(acts, questions)
    full = "\n".join([text or "(no words)"] + [d for d in done if d])
    chat.reply(LABEL + full, who="Boss")
    remember(questions, full)
    return "boss line answered" + (f", {len(done)} action(s)" if done else "")


def short_state() -> str:
    """The plain fallback: running, queued and both meters."""
    text = actions.status_text()
    keep = [ln for ln in text.splitlines() if ln.strip() and "Goals:" not in ln]
    return "\n".join(keep)[:1500]


class Line:
    """At most one boss question in flight, in a thread; the boss process
    calls step() every few seconds (Boss.quick)."""

    def __init__(
        self,
        asker: Callable[[list[str], dict, dict], str] = answer,
    ) -> None:
        self.asker = asker
        self.thread: threading.Thread | None = None
        self.result: dict | None = None

    def busy(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def step(self, settings: dict, readings: Callable[[], dict]) -> str:
        if self.busy():
            return ""
        done = ""
        if self.result is not None:
            result, self.result = self.result, None
            try:
                done = deliver(result["questions"], result)
            except Exception as e:  # not retried: its actions may have run
                store.event("boss", f"boss line reply failed: {e}")
                done = f"boss line reply failed: {type(e).__name__}"
        if _load()["waiting"]:
            now_readings = readings()  # before take(): a failure keeps the questions
            questions = take()
            if questions:
                self.start(questions, settings, now_readings)
        return done

    def start(self, questions: list[str], settings: dict, readings: dict) -> None:
        def work():
            try:
                said = self.asker(questions, settings, readings)
                self.result = {"questions": questions, "answer": said}
            except Exception as e:  # any failure still gets him an answer
                self.result = {
                    "questions": questions,
                    "error": (
                        f"{type(e).__name__}: {e}"
                        if not isinstance(e, NoRoom)
                        else str(e)
                    ),
                    "no_room": isinstance(e, NoRoom),
                }

        self.result = None
        self.thread = threading.Thread(target=work, daemon=True, name="relay-boss-line")
        self.thread.start()


def ask_now(text: str) -> str:
    """The terminal's `relay boss <text>`: the same turn, answered here and
    not sent to WhatsApp. Actions run as they would from WhatsApp."""
    settings = store.settings()
    questions = [text]
    try:
        said = answer(questions, settings, meters.read())
    except NoRoom as e:
        return f"No account can take it ({e}).\n\n{short_state()}"
    words, acts = parse(said)
    done = run_actions(acts, questions)
    full = "\n".join([words] + [d for d in done if d])
    remember(questions, full)
    return full
