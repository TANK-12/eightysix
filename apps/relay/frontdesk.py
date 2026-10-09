"""The WhatsApp front desk: a local Jan model answers Emerson first.

Emerson (2026-10-06): Jan should take most WhatsApp messages itself with a
strong system prompt, and hand off to Claude, who takes over, does the work
and replies. So a plain message goes to Jan (setting `whatsapp_frontdesk`,
"jan" or "off"), which either answers or ends its answer with a hand-off line:

    HANDOFF chat: <note>   the Claude chat session takes the messages over
    HANDOFF work: <text>   a work task starts (or the open one gets it)

The prompt is `frontdesk_prompt.md`, a plain file Emerson can edit; it is
read on every message. The model is Relay's own Jan setting (role
`frontdesk` in ~/.config/forge/jan/relay.json), loaded on first use and
released after its idle time, as every Forge app does.

Jan runs in a thread so the boss loop never blocks on it; the boss starts it
and applies its answer (`Desk.step`). The chat task is in status `desk`
while Jan has it. Its messages stay `[new]` until the answer is applied, so a
boss restart mid-answer simply asks again. If Jan fails, the messages go to
the Claude chat as before, and Jan is skipped for a few minutes.
"""

from __future__ import annotations

import os
import re
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SHARED = Path(os.environ.get("FORGE_SHARED_DIR") or ROOT.parent.parent / "shared")
for extra in (str(ROOT), str(SHARED)):
    if extra not in sys.path:
        sys.path.insert(0, extra)

import actions  # noqa: E402
import chat  # noqa: E402
import commands  # noqa: E402
import forge_jan  # noqa: E402
import items  # noqa: E402
import localchat  # noqa: E402
import store  # noqa: E402

PROMPT_FILE = ROOT / "frontdesk_prompt.md"
DESK = "desk"
DEFAULT_MODEL = "Qwen3_5-4B-IQ4_XS"
ROLE = "frontdesk"
RECENT = 12
SKIP_AFTER_FAIL = 600  # seconds Jan is skipped after a failure
HANDOFF = re.compile(
    r"^\s*\**HANDOFF\s+(chat|work)\**\s*[:\-]\s*\**\s*(.+)$", re.I | re.S
)

JAN = localchat.JAN  # one AppJan for Relay: roles frontdesk and local


def enabled(settings: dict, failed_at: float = 0.0) -> bool:
    if settings.get("whatsapp_frontdesk") != "jan":
        return False
    return time.time() - failed_at > SKIP_AFTER_FAIL


def model() -> str:
    return JAN.model_for(ROLE, DEFAULT_MODEL)


def system_prompt() -> str:
    try:
        return PROMPT_FILE.read_text(encoding="utf-8")
    except OSError:
        return "You are Relay's WhatsApp front desk. Answer Emerson briefly."


def parse(answer: str) -> tuple[str, str, str]:
    """Jan's answer -> (reply for Emerson, hand-off kind or "", note)."""
    lines = answer.strip().splitlines()
    for i in range(len(lines) - 1, -1, -1):
        m = HANDOFF.match(lines[i])
        if m:
            note = " ".join([m.group(2).strip(), *map(str.strip, lines[i + 1 :])])
            reply = "\n".join(lines[:i]).strip()
            return reply, m.group(1).lower(), note.strip()
    return answer.strip(), "", ""


def facts() -> str:
    lines = [f"Now: {time.strftime('%A %d %B %Y, %H:%M')}", actions.status_text()]
    work = chat.open_work()
    if work:
        tail = actions._state_tail(work, 5)
        lines.append(
            f"Open WhatsApp work task {work['id']} ({work.get('status')}): "
            f"{work.get('title')}" + (f"\nIts latest notes:\n{tail}" if tail else "")
        )
    return "\n".join(lines)


def user_prompt(task: dict, messages: list[str]) -> str:
    entries = chat._split(task.get("body", ""))[1]
    earlier = [e for e in entries if not e.startswith(chat.NEW)][-RECENT:]
    talk = "\n".join(f"- {e}" for e in earlier) or "- (nothing yet)"
    new = "\n".join(f"- {m}" for m in messages)
    return (
        f"Facts:\n{facts()}\n\nThe chat so far:\n{talk}\n\n"
        f"New from Emerson (answer these):\n{new}"
    )


def ask(task: dict, messages: list[str]) -> str:
    name = model()
    with JAN.using(name):
        return forge_jan.chat(
            name,
            system_prompt(),
            user_prompt(task, messages),
            temperature=0.4,
            max_tokens=500,
            timeout=180,
            extra={"top_p": 0.9, "top_k": 20},
        )


class Desk:
    """One Jan answer at a time, in a thread; the boss applies the result."""

    def __init__(self, asker=ask, local_asker=localchat.ask) -> None:
        self.asker = asker
        self.local_asker = local_asker
        self.thread: threading.Thread | None = None
        self.result: dict | None = None
        self.watching = False
        self.failed_at = 0.0

    def busy(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def start(self, task: dict, messages: list[str], local: bool = False) -> None:
        asker = self.local_asker if local else self.asker

        def work():
            try:
                self.result = {
                    "messages": messages,
                    "answer": asker(task, messages),
                    "local": local,
                }
            except Exception as e:  # any failure falls back to the Claude chat
                self.result = {
                    "messages": messages,
                    "error": f"{type(e).__name__}: {e}",
                    "local": local,
                }

        self.result = None
        self.thread = threading.Thread(target=work, daemon=True, name="relay-desk")
        self.thread.start()
        if not self.watching:
            JAN.watch()  # releases the model once it sits idle
            self.watching = True

    def step(self, settings: dict, state: dict | None = None) -> str:
        """Apply a finished answer, then start Jan on any waiting messages:
        the local chat (localchat.py) when it is picked or stands in for
        Claude, else the front desk. Returns what happened, for the event
        log ("" when nothing did)."""
        task = chat.chat_task(create=False)
        if not task or self.busy():
            return ""
        done = ""
        if self.result is not None:
            result, self.result = self.result, None
            if result.get("local"):
                done = localchat.apply(task, result)
            else:
                if "error" in result:
                    self.failed_at = time.time()
                done = apply(task, result)
            task = items.find_task(task["id"]) or task
        if task.get("status") != DESK:
            return done
        messages = chat.new_messages(task)
        if not messages:
            task["status"] = chat.IDLE
            items.save(task)
            return done
        if localchat.active(settings, state):
            self.start(task, messages, local=True)
            return done or f"local chat asked Jan ({len(messages)} message(s))"
        if not enabled(settings, self.failed_at):
            to_claude(task)
            return done or "front desk off: to the Claude chat"
        self.start(task, messages)
        return done or f"front desk asked Jan ({len(messages)} message(s))"


def to_claude(task: dict, note: str = "") -> None:
    task = items.find_task(task["id"]) or task
    if note:
        chat._add_entry(task, f"{chat.NEW}{chat._stamp()} Jan handed over: {note}")
        task = items.find_task(task["id"]) or task
    task.update(status="queued", note="")
    items.save(task)
    store.poke()


def apply(task: dict, result: dict) -> str:
    messages = result["messages"]
    if "error" in result:
        to_claude(task)
        return f"Jan failed ({result['error'][:200]}): to the Claude chat"
    reply, kind, note = parse(result["answer"])
    if reply:
        chat.reply(reply, who="Jan")
    if kind == "chat":
        to_claude(task, note)
        return "Jan handed over to the Claude chat"
    chat.mark_read(task, messages)
    task = items.find_task(task["id"]) or task
    if kind == "work":
        cmd = commands.parse("", "new: " + note, source="whatsapp")
        said, _made = actions.apply(cmd, "whatsapp")
        if said:
            chat.reply(said)
    if task.get("status") == DESK and not chat.has_new(task):
        task["status"] = chat.IDLE
        items.save(task)
    return "Jan answered" + (" and started work" if kind == "work" else "")


def samples() -> int:
    """`frontdesk.py --samples`: ask live Jan every sample message and score
    its answer-or-hand-off call against tests/frontdesk_samples.json."""
    data = store.read_json(ROOT / "tests" / "frontdesk_samples.json") or {}
    task = {"body": ""}
    right = 0
    for sample in data.get("samples", []):
        started = time.time()
        try:
            reply, kind, note = parse(ask(task, [f"Emerson: {sample['text']}"]))
        except forge_jan.JanError as e:
            print(f"Jan failed: {e}")
            return 1
        got = kind or "answer"
        right += got == sample["want"]
        mark = "ok  " if got == sample["want"] else "MISS"
        print(
            f"{mark} want {sample['want']:6} got {got:6} {time.time() - started:4.1f}s"
        )
        print(f"     {sample['text']}\n     -> {reply[:160]!r} {note[:120]!r}")
    total = len(data.get("samples", []))
    print(f"{right}/{total} right on {model()}")
    JAN.release_mine()
    return 0


if __name__ == "__main__":
    sys.exit(samples() if "--samples" in sys.argv else 0)
