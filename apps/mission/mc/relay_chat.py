"""The WhatsApp chat with Relay, mirrored live (Emerson's note 1295, task 109).

Emerson runs his sessions from his WhatsApp chat with Relay, so Mission
shows that thread and lets him type into it.

Reading: Relay's chat task keeps the talk under `## Messages` (the last 40
lines, "Thu 15:49 Emerson: ..."; "[new] " marks one the chat has not read
yet). Relay's own chat module splits them, borrowed read-only like store
and items.

Writing: `relay as-whatsapp` (Relay's cli.py) handles the line exactly as
the boss handles one from WhatsApp: a command, a plain chat line, or
`boss: ...` for the boss line. Nothing of Relay's rules is copied here.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess

from mc import borrow
from mc.actions import ActionError

NEW = "[new] "
ENTRY = re.compile(r"^(\w{3} \d{1,2}:\d{2}) ([^:\n]{1,20}): (.*)$", re.S)
BOSS = re.compile(r"^\s*(@boss\b|boss\s*[:,\-])", re.I)
ANSWERING = ("queued", "running", "handing_over", "desk")
SAY_TIMEOUT = 90


def parse(entries: list[str]) -> list[dict]:
    """Messages entries as {key, at, who, me, text, new}. A key stays the
    same while the line is kept, so the page only adds what is new."""
    count: dict[str, int] = {}
    out = []
    for entry in entries:
        new = entry.startswith(NEW)
        body = entry[len(NEW) :] if new else entry
        found = ENTRY.match(body)
        at, who, text = found.groups() if found else ("", "Relay", body)
        base = hashlib.sha1(f"{at}|{who}|{text}".encode()).hexdigest()[:12]
        count[base] = count.get(base, 0) + 1
        out.append(
            {
                "key": f"{base}-{count[base]}",
                "at": at,
                "who": who.strip(),
                "me": who.strip() == "Emerson",
                "text": text,
                "new": new,
            }
        )
    return out


def thread(seen: str = "") -> dict:
    """The chat as it stands. `seen` is the version the page already has:
    then the messages are left out (`same`)."""
    borrow.setup()
    import chat  # Relay's  # pyright: ignore[reportMissingImports]
    import items  # pyright: ignore[reportMissingImports]
    import store  # pyright: ignore[reportMissingImports]

    number = store.settings().get("whatsapp_chat_task") or 0
    task = items.find_task(number) if number else None
    if not task:
        return {"task": None, "status": "", "answering": False, "version": ""}
    entries = chat._split(task.get("body", ""))[1]
    status = str(task.get("status") or "")
    out = {
        "task": task.get("id"),
        "status": status,
        "answering": status in ANSWERING,
        "version": hashlib.sha1("\n\n".join(entries).encode()).hexdigest()[:16],
    }
    if seen and seen == out["version"]:
        return {**out, "same": True}
    return {**out, "messages": parse(entries)}


def command() -> list[str]:
    relay = borrow.app_dir("relay")
    python = os.path.join(relay, ".venv", "bin", "python")
    return [python, os.path.join(relay, "cli.py"), "as-whatsapp"]


def say(text: str, boss: bool = False) -> dict:
    """Send `text` as if Emerson had typed it on WhatsApp; `boss` asks the
    boss line (as "boss: ..." does there). Returns Relay's printed answer."""
    text = text.strip()
    if boss and not BOSS.match(text):
        text = "boss: " + text
    argv = command()
    if not (os.path.exists(argv[0]) and os.path.exists(argv[1])):
        raise ActionError(503, "Relay is not installed here")
    try:
        done = subprocess.run(
            argv, input=text, capture_output=True, text=True, timeout=SAY_TIMEOUT
        )
    except subprocess.TimeoutExpired:
        raise ActionError(
            504, "Relay took too long to take that; check the chat before sending again"
        )
    if done.returncode:
        why = (done.stderr.strip().splitlines() or ["no reason given"])[-1]
        raise ActionError(502, f"Relay could not take that: {why[:300]}")
    return {"ok": True, "reply": done.stdout.strip()[:4000]}
