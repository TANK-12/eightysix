"""Desktop apps opening and closing, in any desktop (GNOME, Hyprland, Plasma).

An "app" is anything with a visible launcher entry (.desktop file without
NoDisplay). Native apps are matched by their running program's name, Flatpak
apps by `flatpak ps`. The first read only notes what is already running, so
starting the calendar does not log every open app at once."""

from __future__ import annotations

import os
import shlex
import subprocess
import time
from pathlib import Path

NAME = "apps"
LABEL = "Apps opened"
DESCRIPTION = "Desktop apps opening and closing, with how long they were open."
DEFAULT_ON = True
INTERVAL = 30

DESKTOP_DIRS = [
    Path("/usr/share/applications"),
    Path.home() / ".local/share/applications",
    Path("/var/lib/flatpak/exports/share/applications"),
    Path.home() / ".local/share/flatpak/exports/share/applications",
]
# Helpers that have launchers but are not "opening an app" in any useful sense.
IGNORE = {
    "sh",
    "bash",
    "env",
    "python3",
    "python",
    "flatpak",
    "gio",
    "xdg-open",
    "systemctl",
}


def parse_desktop(text: str) -> dict:
    entry, inside = {}, False
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            inside = line == "[Desktop Entry]"
        elif inside and "=" in line:
            k, v = line.split("=", 1)
            entry.setdefault(k.strip(), v.strip())
    return entry


def launchers(dirs=DESKTOP_DIRS) -> tuple[dict, dict]:
    """({program name: app name}, {flatpak id: app name})."""
    programs, flatpaks = {}, {}
    for folder in dirs:
        if not folder.is_dir():
            continue
        for path in folder.glob("*.desktop"):
            try:
                e = parse_desktop(path.read_text(errors="replace"))
            except OSError:
                continue
            if (
                e.get("NoDisplay") == "true"
                or e.get("Type", "Application") != "Application"
            ):
                continue
            name = e.get("Name") or path.stem
            if "flatpak" in str(folder) or "flatpak run" in e.get("Exec", ""):
                flatpaks[path.stem] = name
                continue
            try:
                program = os.path.basename(shlex.split(e.get("Exec", ""))[0])
            except (ValueError, IndexError):
                continue
            if program and program not in IGNORE:
                programs.setdefault(program, name)
    return programs, flatpaks


def running_programs(proc: Path = Path("/proc")) -> set[str]:
    names = set()
    me = os.getuid()
    for p in proc.iterdir():
        if not p.name.isdigit():
            continue
        try:
            if p.stat().st_uid != me:
                continue
            names.add(os.path.basename(os.readlink(p / "exe")))
        except OSError:
            continue
    return names


def running_flatpaks() -> set[str]:
    try:
        out = subprocess.run(
            ["flatpak", "ps", "--columns=application"],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    return {line.strip() for line in out.splitlines() if line.strip()}


def minutes(seconds: float) -> str:
    m = int(seconds // 60)
    return f"{m // 60} h {m % 60} min" if m >= 60 else f"{max(1, m)} min"


def collect(
    state: dict, now: float | None = None, programs=None, flatpaks=None
) -> list[dict]:
    now = time.time() if now is None else now
    if programs is None or flatpaks is None:
        progs, paks = launchers()
        running = {progs[n] for n in running_programs() if n in progs}
        running |= {paks.get(a, a) for a in running_flatpaks() if a in paks}
    else:
        running = set(programs) | set(flatpaks)
    was: dict = state.get("open", {})
    first = "open" not in state
    events = []
    if not first:
        for app in sorted(running - set(was)):
            events.append(
                {
                    "ts": now,
                    "source": NAME,
                    "kind": "app_open",
                    "title": f"Opened {app}",
                    "tags": [app[:30]],
                    "key": f"apps:open:{app}:{int(now)}",
                }
            )
        for app in sorted(set(was) - running):
            opened = was[app]
            events.append(
                {
                    "ts": now,
                    "source": NAME,
                    "kind": "app_close",
                    "title": f"Closed {app} (open {minutes(now - opened)})",
                    "tags": [app[:30]],
                    "key": f"apps:close:{app}:{int(now)}",
                }
            )
    state["open"] = {app: was.get(app, now) for app in running}
    return events
