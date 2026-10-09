"""What a command does. Shared by mail (via the boss), the terminal and the
page, so all three behave the same. Nothing here launches a session: it only
writes files; the boss launches on its next tick (poked straight away).
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

import chat
import items
import meters
import picker
import quick
import runs
import store
from commands import Command

HELP = """\
Relay commands (first line of the mail, or the subject):

  status             what is running, queued and waiting on you
  pause / resume     stop or allow new launches (running work carries on)
  stop 12            stop task 12 (in a task's thread, just "stop")
  retry 12           run a stopped, failed or blocked task again
  tell 12 <text>     a note to task 12's running session (it reads it after
                     its next step, before anything else)
  digest             the daily summary, now
  goal: <title>      a goal; the lines below describe it. Relay plans tasks for it
  task: [goal] <text>   a task, added to that goal when you name one
  progress [12]      where each running task is (its State notes), or task 12's
  usage              both usage meters and when they reset
  say [@name] <text> a note on the crew board to every session (or one)
  notify quiet|mine|all   WhatsApp: only answers / also your tasks' results
                     and anything needing you (default) / everything
  #12 <text>         WhatsApp: more for task 12 (told now if it is running,
                     else added to the work task)
  new: <text>        WhatsApp work task (one at a time; more is added to it)
  boss <question>    WhatsApp: straight to Relay's boss: what runs, ETAs,
                     usage, stop, queue or tell a task; answers in a minute
                     or two. The word boss alone sends every message there
  help               this list

Quick commands, answered at once without a model (any channel):
{quick}

Anything else is a new task: write what you want, one line or three pages,
and a fresh session works on it and mails you the result. Replying in a
task's thread continues that task's work.

Optional lines at the top of a request:
  important          max effort and first in the queue
  folder: ~/Forge/apps/cosmos
  effort: low|medium|high|xhigh|max
  account: default|hey|second
  model: opus|sonnet|haiku
  done when: <how to tell it is finished>
"""


def ago(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 90:
        return f"{seconds}s"
    if seconds < 5400:
        return f"{seconds // 60}m"
    return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"


def meters_text(readings: dict) -> str:
    rows = meters.describe(readings, store.settings())
    return "\n".join("  " + row for row in rows) or "  no accounts"


def status_text() -> str:
    st = store.state()
    s = store.settings()
    now = time.time()
    lines = []
    beat = st.get("heartbeat") or 0
    if not beat or now - beat > 300:
        lines.append(
            "Warning: the boss has not ticked "
            + (f"for {ago(now - beat)}" if beat else "yet")
            + " (check the relay-boss service)."
        )
    if s["paused"]:
        lines.append("Paused: no new launches.")
    if st.get("wait_reason"):
        lines.append(f"Waiting: {st['wait_reason']}")
    active = runs.active()
    lines.append(f"\nRunning ({len(active)}):")
    for run in active:
        info = runs.summary(run)
        task = items.find_task(run["task"]) if run.get("task") else None
        name = (
            f"task {run['task']} {task.get('title', '')}"
            if task
            else f"planning {run.get('goal')}"
        )
        lines.append(
            f"  {name} [{run['kind']}, {run['account']}, {run['effort']}] "
            f"{ago(now - run['started'])}, {info['context_tokens'] // 1000}k context, "
            f"last: {info['last_action'] or 'starting'}"
        )
    tasks = items.all_tasks()
    queued = [t for t in tasks if t.get("status") == "queued"]
    lines.append(f"\nQueued ({len(queued)}):")
    lines += [f"  {t['id']} {t.get('title')}" for t in queued[:10]]
    waiting = [t for t in tasks if t.get("status") in ("blocked", "parked")]
    if waiting:
        lines.append("\nWaiting on you:")
        lines += [
            f"  {t['id']} {t.get('title')} ({t.get('status')}: {t.get('note', '')})"
            for t in waiting
        ]
    goals = [g for g in items.all_goals() if g.get("status") != "done"]
    if goals:
        lines.append("\nGoals:")
        lines += [f"  {g['slug']} [{g.get('status')}] {g.get('title')}" for g in goals]
    lines.append("\nUsage:\n" + meters_text(st.get("meters") or {}))
    return "\n".join(lines).strip()


def digest_text(since: float) -> str:
    tasks = items.all_tasks()
    done = [
        t
        for t in tasks
        if t.get("status") == "done" and items.num(t, "finished") >= since
    ]
    lines = [f"Finished since {time.strftime('%a %H:%M', time.localtime(since))}:"]
    lines += [f"  {t['id']} {t.get('title')}" for t in done] or ["  nothing"]
    return "\n".join(lines) + "\n\n" + status_text()


def _state_tail(task: dict, lines: int = 8) -> str:
    try:
        body = open(task["path"], encoding="utf-8").read()
    except (OSError, KeyError):
        return ""
    _, sep, state = body.partition("## State")
    kept = [ln for ln in state.strip().splitlines() if ln.strip()]
    return "\n".join(kept[-lines:]) if sep else ""


def progress_text(number=None) -> str:
    """Where work is: each running task's State notes and its latest step."""
    now = time.time()
    active = [r for r in runs.active() if r.get("task")]
    if number is not None:
        task = items.find_task(number)
        if not task:
            return f"There is no task {number}."
        run = next((r for r in active if str(r["task"]) == str(task["id"])), None)
        head = f"#{task['id']} {task.get('title')} [{task.get('status')}]"
        if run:
            info = runs.summary(run)
            head += f", {ago(now - run['started'])} in, last: {info['last_action']}"
            if info["last_text"]:
                head += f"\nSaid: {info['last_text'][-300:]}"
        return head + "\n" + (_state_tail(task, 14) or "(no State notes yet)")
    if not active:
        queued = sum(1 for t in items.all_tasks() if t.get("status") == "queued")
        wait = store.state().get("wait_reason") or ""
        return f"Nothing running. {queued} queued." + (
            f" Waiting: {wait}" if wait else ""
        )
    parts = []
    for run in active:
        task = items.find_task(run["task"]) or {}
        info = runs.summary(run)
        parts.append(
            f"#{run['task']} {task.get('title', '')} ({ago(now - run['started'])}, "
            f"{run['account']}), last: {info['last_action'] or 'starting'}\n"
            + (_state_tail(task, 5) or "")
        )
    return "\n\n".join(parts)


def usage_text() -> str:
    st = store.state()
    readings = st.get("meters") or {}
    lines = [meters_text(readings)]
    for name, m in sorted(readings.items()):
        back = meters.until(m.get("resets"))
        if back:
            lines.append(f"  {name} 5-hour window resets {back}")
    if st.get("wait_reason"):
        lines.append(f"Waiting: {st['wait_reason']}")
    return "\n".join(lines)


def say(text: str, to: str = "") -> str:
    board = store.settings()["board"]
    extra = ["--to", to] if to else []
    if not _crew("post", board, "Emerson", text, *extra):
        return "Could not reach the crew board."
    return f"Posted on the {board} board" + (f" to {to}." if to else " to everyone.")


def set_notify(level: str) -> str:
    store.save_settings({"whatsapp_notify": level})
    return f"WhatsApp notifications: {level}."


def _wait_note() -> str:
    wait = store.state().get("wait_reason") or ""
    return f"\nNot starting yet: {wait}" if wait else ""


def _folder(value: str) -> str:
    return os.path.expanduser(value) if value else ""


def add_task(
    cmd: Command,
    source: str,
    thread: str = "",
    subject: str = "",
    follow_of: str = "",
) -> dict:
    opts = cmd.options
    goal = cmd.goal or "inbox"
    if follow_of and not cmd.goal:
        parent = items.find_task(follow_of)
        goal = (parent or {}).get("goal") or "inbox"
    task = items.new_task(
        cmd.title,
        cmd.text,
        goal=goal,
        priority=opts.get("priority", "normal"),
        folder=_folder(opts.get("folder", "")),
        done_when=opts.get("done_when", ""),
        effort=opts.get("effort", ""),
        account=opts.get("account", ""),
        model=opts.get("model", ""),
        source=source,
        thread=thread,
        subject=subject,
        follow_of=follow_of,
    )
    store.event("task", f"task {task['id']} queued from {source}: {task['title']}")
    store.poke()
    return task


def add_goal(cmd: Command, source: str, thread: str = "", subject: str = "") -> dict:
    opts = cmd.options
    goal = items.new_goal(
        cmd.title,
        cmd.text,
        priority=opts.get("priority", "normal"),
        folder=_folder(opts.get("folder", "")),
        check=opts.get("check", ""),
    )
    if thread:
        goal.update(thread=thread, subject=subject)
        items.save(goal)
    store.event("goal", f"goal {goal['slug']} added from {source}: {goal['title']}")
    store.poke()
    return goal


def set_paused(paused: bool) -> str:
    store.save_settings({"paused": paused})
    store.event("pause" if paused else "resume", "paused" if paused else "resumed")
    store.poke()
    return (
        "Paused: no new sessions start. Running ones carry on (stop them by number)."
        if paused
        else "Resumed: queued work will start as usage allows."
    )


def stop_task(number) -> str:
    task = items.find_task(number) if number is not None else None
    if not task:
        return f"There is no task {number}."
    task["status"] = "stopped"
    items.save(task)
    stopped = 0
    for run in runs.active():
        if str(run.get("task")) == str(task["id"]):
            runs.stop(run)
            stopped += 1
    store.event("stop", f"task {task['id']} stopped by Emerson")
    store.poke()
    return f"Stopped task {task['id']} ({task.get('title')})" + (
        f", ended {stopped} running session." if stopped else "; it was not running."
    )


def retry_task(number) -> str:
    task = items.find_task(number) if number is not None else None
    if not task:
        return f"There is no task {number}."
    if task.get("status") in items.ACTIVE:
        return f"Task {task['id']} is already running."
    task.update(
        status="queued",
        fails=0,
        attempts=0,
        note="",
        reviewed_at=0,
        review_fails=0,
        review_note="",
    )
    items.save(task)
    store.event("retry", f"task {task['id']} queued again")
    store.poke()
    return f"Task {task['id']} ({task.get('title')}) is queued again."


def finishing(run_id: str) -> str:
    """A work session close to done says so (`relay finishing`, Emerson
    2026-10-08): the boss leaves it past the context hand-over for
    finishing_minutes, so it finishes where it is. The first call counts."""
    run = None
    if run_id and all(c in "0123456789abcdef-" for c in run_id):
        run = store.read_json(runs.run_dir(run_id) / "run.json")
    if not isinstance(run, dict) or run.get("kind") != "work" or run.get("ended"):
        return "Only a running Relay work session can say this."
    now = time.time()
    since = float(run.get("finishing") or 0)
    minutes = picker.finishing_minutes(store.settings())
    if minutes <= 0:
        return (
            "Relay gives no finishing time now (finishing_minutes is 0): it hands "
            "this session over at its context line as usual."
        )
    if not since:
        since = run["finishing"] = now
        runs.save(run)
        store.event(
            "finishing",
            f"task {run.get('task')}: close to finishing, no context hand-over "
            f"for {minutes:g} min",
        )
    until = time.strftime("%H:%M", time.localtime(since + minutes * 60))
    if now >= since + minutes * 60:
        return (
            f"Your finishing time ran out at {until}: bring State up to date and "
            "end it with status: continue."
        )
    return (
        f"Noted: Relay will not hand this session over for its context size "
        f"until {until}. Finish the task, end State with status: done and write "
        "your report."
    )


def crew_note(to: str, text: str) -> bool:
    return _crew("post", store.settings()["board"], "Emerson", text, "--to", to)


def _crew(*args: str) -> bool:
    """Runs one crew board command; True when it worked."""
    if not store.CREW.is_file():
        return False
    try:
        done = subprocess.run(
            [sys.executable, str(store.CREW), *args], capture_output=True, timeout=20
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def tell_task(number, text: str) -> str:
    """Emerson's note to a running session, through the crew board: the notes
    hook shows it to that session after its next tool call."""
    task = items.find_task(number) if number is not None else None
    if not task:
        return f"There is no task {number}."
    if task.get("status") not in items.ACTIVE:
        return (
            f"Task {task['id']} is not running ({task.get('status')}). Reply in its "
            "thread, or write a new task, to give it more work."
        )
    if task.get("status") == "reviewing":
        # no work session runs during its review: the note goes into its
        # request, where the review and the next session both read it
        chat.add_to_task(task, text, queue=False)
        store.event("tell", f"task {task['id']} (in review): {text[:80]}")
        return (
            f"Task {task['id']} is being reviewed right now: your note is in its "
            "request, and its next session reads it."
        )
    note = f"Emerson, for Relay task {task['id']} (act on this first, then ack): {text}"
    kind = "chat" if chat.is_chat(task) else "work"
    if not crew_note(f"relay-{task['id']}-{kind}", note):
        return "Could not reach the crew board; the note was not sent."
    store.event("tell", f"task {task['id']}: {text[:80]}")
    return f"Told task {task['id']}. It sees the note after its next step."


def _boss_mode() -> bool:
    import bossline

    return bossline.in_mode()


def chat_message(text: str) -> str:
    """A plain WhatsApp message: to the chat session, which answers it
    itself (so nothing is sent back here)."""
    task, running = chat.route(text)
    if running:
        crew_note(
            f"relay-{task['id']}-chat",
            "New WhatsApp message from Emerson. Take it with `relay inbox` and "
            "answer it with `relay reply`.",
        )
    store.event("chat", f"to chat {task['id']}: {text[:80]}")
    return ""


def add_work(cmd: Command, follow_of: str = "") -> tuple[str, dict | None]:
    """The WhatsApp work task: at most one open. More work while it is open
    is told to it (running) or added to its request (waiting)."""
    text = cmd.text
    if follow_of:
        text = f"(about task {follow_of}) {text}"
    current = chat.open_work()
    if current:
        if current.get("status") in items.ACTIVE:
            told = tell_task(current["id"], text)
            if told.startswith("Told"):
                return (
                    f"Added to work task {current['id']}: it is running and "
                    "sees it after its next step.",
                    None,
                )
            return told, None
        chat.add_to_task(current, text)
        return f"Added to work task {current['id']}; it picks it up next.", None
    s = store.settings()
    cmd.options = {
        **cmd.options,
        "model": cmd.options.get("model") or s["whatsapp_work_model"],
        "effort": cmd.options.get("effort") or s["whatsapp_work_effort"],
    }
    task = add_task(cmd, "whatsapp", follow_of=follow_of)
    store.save_settings({"whatsapp_work_task": task["id"]})
    return (
        f"Work task {task['id']} queued on {task.get('model')} at "
        f"{task.get('effort')}. The result comes here; ask me how it is going "
        "any time." + _wait_note(),
        task,
    )


def apply(
    cmd: Command,
    source: str,
    thread_task: str = "",
    thread: str = "",
    subject: str = "",
) -> tuple[str, dict | None]:
    """Carry out `cmd`; (reply text, new task or goal or None)."""
    if cmd.kind == "help":
        if source == "whatsapp":
            return quick.command_list(), None
        return HELP.replace("{quick}", quick.help_lines("  ")), None
    if cmd.kind == "quick":
        return quick.run(cmd.title, tuple(cmd.options.get("args") or ())), None
    if cmd.kind == "status":
        return status_text(), None
    if cmd.kind == "digest":
        return digest_text(time.time() - 86400), None
    if cmd.kind in ("pause", "resume"):
        return set_paused(cmd.kind == "pause"), None
    if cmd.kind == "tell":
        return tell_task(cmd.number, cmd.text), None
    if cmd.kind == "progress":
        number = cmd.number if cmd.number is not None else None
        return progress_text(number), None
    if cmd.kind == "usage":
        return usage_text(), None
    if cmd.kind == "notify":
        return set_notify(cmd.text), None
    if cmd.kind == "say":
        return say(cmd.text, cmd.title), None
    if source == "whatsapp" and thread_task and cmd.kind in ("task", "chat", "boss"):
        running = items.find_task(thread_task) or {}
        if running.get("status") in items.ACTIVE:
            return tell_task(thread_task, cmd.text), None
        return add_work(cmd, follow_of=thread_task)
    if cmd.kind == "boss" or (cmd.kind == "chat" and _boss_mode()):
        import bossline  # it uses this module

        return bossline.ask_later(cmd.text), None
    if cmd.kind == "chat":
        return chat_message(cmd.text), None
    if cmd.kind == "work" or (source == "whatsapp" and cmd.kind == "task"):
        return add_work(cmd)
    if cmd.kind in ("stop", "retry"):
        number = cmd.number if cmd.number is not None else thread_task or None
        if number is None:
            return f"Which task? Write {cmd.kind} and its number.", None
        return (stop_task(number) if cmd.kind == "stop" else retry_task(number)), None
    if cmd.kind == "goal":
        goal = add_goal(cmd, source, thread, subject)
        return (
            f"Goal {goal['slug']} added: {goal['title']}. A short planning "
            "session will split it into tasks and I will mail you as they finish.",
            goal,
        )
    task = add_task(cmd, source, thread, subject, follow_of=thread_task)
    more = f" (follows up task {thread_task})" if thread_task else ""
    return (
        f"Got it: task {task['id']} queued{more}: {task['title']}.\n"
        f"Priority {task['priority']}. "
        + (
            "I will mail the result when it finishes.\n"
            "Reply 'stop' in this thread to cancel it."
            if source == "mail"
            else f"See it with: relay status (stop it with: relay stop {task['id']})."
        ),
        task,
    )
