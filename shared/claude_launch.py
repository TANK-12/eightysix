"""Finding the claude command and building a headless `claude -p` command line.

Shared by Crew Room (background tasks from its page) and Relay (the boss that
runs sessions unattended). The prompt always goes in on stdin and the output
is stream-json, one event per line, so the caller can watch it from a file.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def find_claude(env_var: str = "") -> str | None:
    override = os.environ.get(env_var) if env_var else None
    if override:
        return override
    found = shutil.which("claude")
    if found:
        return found
    # Forge and systemd services can start without ~/.local/bin on PATH.
    local = Path.home() / ".local" / "bin" / "claude"
    return str(local) if local.is_file() else None


def headless_command(
    claude: str,
    session_id: str,
    mode: str,
    model: str = "",
    effort: str = "",
    name: str = "",
    resume: str = "",
) -> list[str]:
    """`resume` continues an earlier session by id instead of starting
    `session_id`; it must run under the same account and folder."""
    args = [claude, "-p", "--output-format", "stream-json", "--verbose"]
    args += ["--permission-mode", mode]
    args += ["--resume", resume] if resume else ["--session-id", session_id]
    if model:
        args += ["--model", model]
    if effort:
        args += ["--effort", effort]
    if name:
        args += ["--name", name]
    return args
