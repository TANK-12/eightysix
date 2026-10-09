"""Is the laptop free enough to start another session?

Memory local-compute-contention: Jan, renders and Claude share one laptop.
Relay never touches Jan or a render; when one is busy it simply waits.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path


def _ticks(proc: Path, pid: str) -> int:
    try:
        fields = (proc / pid / "stat").read_text().rsplit(")", 1)[1].split()
        return int(fields[11]) + int(fields[12])
    except (OSError, IndexError, ValueError):
        return 0


def _named(proc: Path, names: tuple[str, ...]) -> list[tuple[str, str]]:
    found = []
    for entry in proc.iterdir() if proc.is_dir() else []:
        if not entry.name.isdigit():
            continue
        try:
            comm = (entry / "comm").read_text().strip()
            if comm in names:
                args = (entry / "cmdline").read_bytes().replace(b"\0", b" ")
                found.append((entry.name, args.decode("utf-8", "replace")))
        except OSError:
            continue
    return found


def jan_cpu(proc: Path = Path("/proc"), sample: float = 1.0) -> float:
    """Percent of one CPU all llama-server processes used over `sample` s."""
    pids = [pid for pid, _ in _named(proc, ("llama-server",))]
    if not pids:
        return 0.0
    before = sum(_ticks(proc, p) for p in pids)
    time.sleep(sample)
    after = sum(_ticks(proc, p) for p in pids)
    hz = os.sysconf("SC_CLK_TCK")
    return max(0.0, (after - before) / hz / sample * 100)


def rendering(proc: Path = Path("/proc")) -> bool:
    for _, args in _named(proc, ("blender",)):
        words = args.split()
        if "-b" in words or "--background" in words:
            return True
    return False


def busy(settings: dict, proc: Path = Path("/proc")) -> str:
    """Why not to launch now; "" when the machine is free enough."""
    free_gb = shutil.disk_usage(Path.home()).free / 1e9
    if free_gb < settings["min_free_gb"]:
        return f"only {free_gb:.1f} GB disk free"
    load = os.getloadavg()[0] / (os.cpu_count() or 1)
    if load > settings["max_load_per_cpu"]:
        return f"load is high ({load:.2f} per CPU)"
    if settings.get("wait_for_renders", True) and rendering(proc):
        return "a Blender render is running"
    cpu = jan_cpu(proc)
    if cpu > settings["busy_jan_cpu"]:
        return f"Jan is busy ({cpu:.0f}% CPU)"
    return ""
