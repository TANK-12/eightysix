"""Where a session runs: folder, terminal device and program, name, when it
started, and for an ended session the command that opens it again.

On GNOME an app cannot raise one particular terminal tab (checked 2026-09-16:
every claude's parent is a bash under the single gnome-terminal-server), so
Emerson chose this description in place of "jump to its terminal".
"""

from __future__ import annotations

import glob
import json
import os
import shlex
from datetime import datetime

import launch
import transcripts
from context import Context, read_cmdline, read_comm, read_stat
from sources import sessions

# Parents skipped on the way up to the program that owns the terminal.
SHELLS = {"bash", "zsh", "fish", "sh", "dash", "nu", "sudo", "env", "nohup", "login"}
# Process name -> how to say it. Anything else shows its own name.
TERMINALS = {
    "gnome-terminal-server": "GNOME Terminal",
    "kgx": "GNOME Console",
    "konsole": "Konsole",
    "kitty": "kitty",
    "alacritty": "Alacritty",
    "foot": "foot",
    "wezterm-gui": "WezTerm",
    "xterm": "xterm",
    "tmux": "tmux",
    "sshd": "SSH",
    "code": "VS Code",
}
PARENT_LEVELS = 12
BACKGROUND_LABEL = "Crew Room background task"


def terminal_device(proc_dir: str, pid: int) -> str | None:
    """/dev/pts/N from the process's standard input, None for a pipe."""
    try:
        target = os.readlink(os.path.join(proc_dir, str(pid), "fd", "0"))
    except OSError:
        return None
    return target if target.startswith(("/dev/pts/", "/dev/tty")) else None


def terminal_program(proc_dir: str, pid: int) -> str | None:
    """The first parent that is not a shell, in plain words."""
    current = pid
    for _ in range(PARENT_LEVELS):
        fields = read_stat(proc_dir, current)
        try:
            parent = int(fields[1]) if fields and len(fields) > 1 else 0
        except ValueError:
            return None
        if parent <= 1:
            return None
        args = read_cmdline(proc_dir, parent)
        name = os.path.basename(args[0]) if args else read_comm(proc_dir, parent)
        name = name.lstrip("-")
        if name not in SHELLS:
            return None if name in ("systemd", "init") else TERMINALS.get(name, name)
        current = parent
    return None


def live_session(ctx: Context, session_id: str) -> tuple[int, dict] | None:
    for path in glob.glob(os.path.join(ctx.claude_dir, "sessions", "*.json")):
        try:
            with open(path, encoding="utf-8") as fh:
                info = json.load(fh)
            pid = int(info.get("pid") or os.path.basename(path).split(".")[0])
        except (OSError, ValueError, TypeError, AttributeError):
            continue
        if str(info.get("sessionId")) == session_id and sessions.is_alive(
            ctx, pid, info.get("procStart")
        ):
            return pid, info
    return None


def _epoch(stamp: object) -> float | None:
    try:
        return datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def describe(ctx: Context, session_id: str) -> dict | None:
    """None when nothing at all is known about the session."""
    live = live_session(ctx, session_id)
    transcript = sessions.find_transcript(ctx, session_id)
    task = launch.find_task(session_id)
    if not (live or transcript or task):
        return None
    info: dict = {
        "id": session_id,
        "alive": live is not None,
        "task": (
            {"prompt": task.get("prompt"), "model": task.get("model")} if task else None
        ),
    }
    if live:
        pid, data = live
        info.update(
            pid=pid,
            name=data.get("name"),
            folder=data.get("cwd"),
            tty=terminal_device(ctx.proc_dir, pid),
            terminal=(
                BACKGROUND_LABEL if task else terminal_program(ctx.proc_dir, pid)
            ),
            background=bool(task) or data.get("entrypoint") == "sdk-cli",
            started_at=(data.get("startedAt") or 0) / 1000,
            resume=None,
        )
        return info
    head = transcripts.read_head(transcript) if transcript else []
    first = next((e for e in head if e.get("cwd")), {})
    title = None
    for entry in transcripts.read_tail(transcript) if transcript else []:
        title = entry.get("aiTitle") or title
    folder = (task or {}).get("folder") or first.get("cwd")
    command = f"claude --resume {session_id}"
    info.update(
        pid=None,
        name=title,
        folder=folder,
        tty=None,
        terminal=None,
        background=bool(task),
        started_at=(task or {}).get("started_at") or _epoch(first.get("timestamp")),
        resume=f"cd {shlex.quote(folder)} && {command}" if folder else command,
    )
    return info
