"""Where the Crew Room reads from, gathered in one object.

Every source takes a Context instead of reaching for ~/.claude or /proc
directly, which is what lets the tests point the whole app at a fixture tree.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field


def read_cmdline(proc_dir: str, pid: int) -> list[str]:
    try:
        with open(os.path.join(proc_dir, str(pid), "cmdline"), "rb") as fh:
            raw = fh.read()
    except OSError:
        return []
    return [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]


def read_comm(proc_dir: str, pid: int) -> str:
    try:
        with open(os.path.join(proc_dir, str(pid), "comm"), encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


@dataclass
class Context:
    claude_dir: str
    proc_dir: str = "/proc"
    now: float = field(default_factory=time.time)
    clock_ticks: int = 100
    cpu_count: int = 1
    # where the Claude app's manifest is found, for its tab names; "" skips it
    forge_apps_dir: str = ""

    @classmethod
    def from_env(cls) -> "Context":
        home = os.path.expanduser("~")
        try:
            ticks = os.sysconf("SC_CLK_TCK")
        except (ValueError, OSError):
            ticks = 100
        return cls(
            claude_dir=os.environ.get("CREWROOM_CLAUDE_DIR")
            or os.path.join(home, ".claude"),
            proc_dir=os.environ.get("CREWROOM_PROC_DIR") or "/proc",
            clock_ticks=ticks,
            cpu_count=os.cpu_count() or 1,
            forge_apps_dir=os.environ.get("CREWROOM_FORGE_APPS_DIR")
            or os.path.join(home, "Forge", "apps"),
        )


def proc_start_ticks(proc_dir: str, pid: int) -> str | None:
    """Field 22 of /proc/<pid>/stat, the process start time in clock ticks.
    None when the process is gone."""
    fields = read_stat(proc_dir, pid)
    return fields[19] if fields and len(fields) > 19 else None


def read_stat(proc_dir: str, pid: int) -> list[str] | None:
    """The fields of /proc/<pid>/stat after the command name. The name sits in
    brackets and may itself contain spaces, so split after the last ')'.
    Index 0 is field 3 (state), so field n is index n - 3."""
    try:
        with open(os.path.join(proc_dir, str(pid), "stat"), encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None
    close = text.rfind(")")
    if close < 0:
        return None
    return text[close + 1 :].split()
