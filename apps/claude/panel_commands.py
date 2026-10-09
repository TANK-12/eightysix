"""Claude Code commands that Claude may run on its own session in the panel.

Claude asks through the panel's MCP tool `panel_command` (browser_mcp.py). A
command cannot run in the middle of a turn, so the tool only queues it: one
JSON line in the conversation's queue file. When the turn ends the runner
(runner.Conversation) takes the queue and sends each command as the next
message, and the page shows "Claude asked to /compact".

Adding a command is one entry in COMMANDS. Standard library only: the MCP
server runs on the system Python.
"""

from __future__ import annotations

import fcntl
import json
import time
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def _locked(path: Path):
    """One writer or taker of a queue at a time (the MCP server appends, the
    panel takes), across processes: an flock on a lock file beside it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_name(path.name + ".lock"), "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


# name -> what it does (shown to Claude in the tool's description), and
# whether it takes words after it ("args": "none" / "optional" / "required").
COMMANDS: dict[str, dict] = {
    "compact": {
        "args": "optional",
        "help": "summarise the conversation so far to free context; the words say what to keep",
    },
    "context": {"args": "none", "help": "show how full the context window is"},
    "usage": {"args": "none", "help": "show the account's usage and limits"},
    "recap": {"args": "none", "help": "write a short recap of the session"},
    "rename": {"args": "required", "help": "give the session a new name"},
}

MAX_ARGS = 2000


def command_line(name: str, args: str = "") -> str:
    """The checked command as it is sent, e.g. "/compact keep the test list".
    Raises ValueError for anything not in COMMANDS or wrongly given."""
    if not isinstance(name, str) or not isinstance(args, str):
        raise ValueError("command and args must be text")
    name = name.strip().lstrip("/")
    spec = COMMANDS.get(name)
    if spec is None:
        raise ValueError(f"Not an allowed command: {name or '(none)'}")
    words = " ".join(args.split())[:MAX_ARGS]
    if spec["args"] == "none" and words:
        raise ValueError(f"/{name} takes nothing after it")
    if spec["args"] == "required" and not words:
        raise ValueError(f"/{name} needs words after it")
    return f"/{name} {words}".strip()


def queue(path: Path, name: str, args: str = "") -> str:
    """Add a command to a conversation's queue; returns the command line."""
    line = command_line(name, args)
    with _locked(path), open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"command": line, "at": time.time()}) + "\n")
    return line


def take_next(path: Path) -> str | None:
    """The oldest queued command, removed from the queue (the rest wait for
    the turn it starts to end). Lines that are not valid JSON, or not an
    allowed command any more, are dropped."""
    if not path.exists():
        return None
    with _locked(path):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return None
        found: str | None = None
        while lines and found is None:
            raw = lines.pop(0)
            try:
                line = str(json.loads(raw).get("command") or "")
                name, _, args = line.lstrip("/").partition(" ")
                found = command_line(name, args)
            except Exception:  # noqa: BLE001 - any bad line is dropped, never jams
                continue
        if lines:
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
            tmp.replace(path)
        else:
            path.unlink(missing_ok=True)
    return found
