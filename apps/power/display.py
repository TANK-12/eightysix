"""Switch the laptop panel's refresh rate: Hyprland's Lua interface (`hyprctl eval`),
or on GNOME the Mutter D-Bus script in display_gnome.py."""

from __future__ import annotations

import json
import os
import re
import subprocess

GNOME_SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "display_gnome.py"
)

SAFE_NAME = re.compile(r"^[A-Za-z0-9-]+$")
SAFE_MODE = re.compile(r"^(\d+)x(\d+)@(\d+(?:\.\d+)?)Hz$")


def internal_panel(monitors: list[dict]) -> dict | None:
    return next((m for m in monitors if str(m.get("name", "")).startswith("eDP")), None)


def monitor_argv(mon: dict, hz: int) -> list[str] | None:
    """The hyprctl command that sets `mon` to `hz`, or None if nothing should run."""
    name = str(mon.get("name", ""))
    if not SAFE_NAME.match(name) or round(float(mon["refreshRate"])) == hz:
        return None
    mode = None
    for candidate in mon.get("availableModes", []):
        match = SAFE_MODE.match(candidate)
        if (
            match
            and int(match[1]) == mon["width"]
            and int(match[2]) == mon["height"]
            and round(float(match[3])) == hz
        ):
            mode = candidate
            break
    if mode is None:
        return None
    fields = [
        f'output = "{name}"',
        f'mode = "{mode}"',
        f'position = "{int(mon["x"])}x{int(mon["y"])}"',
        f'scale = {float(mon["scale"]):g}',
    ]
    if mon.get("transform"):
        fields.append(f'transform = {int(mon["transform"])}')
    return ["hyprctl", "eval", "hl.monitor({ " + ", ".join(fields) + " })"]


def _set_refresh_gnome(hz: int) -> str:
    try:
        proc = subprocess.run(
            ["/usr/bin/python3", GNOME_SCRIPT, str(hz)],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"could not switch: {exc}"
    return proc.stdout.strip() or proc.stderr.strip()[-200:] or "no answer from GNOME"


def set_refresh(hz: int) -> str:
    if "GNOME" in os.environ.get("XDG_CURRENT_DESKTOP", "") and not os.environ.get(
        "HYPRLAND_INSTANCE_SIGNATURE"
    ):
        return _set_refresh_gnome(hz)
    try:
        out = subprocess.run(
            ["hyprctl", "monitors", "-j"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout
        panel = internal_panel(json.loads(out))
    except (OSError, subprocess.SubprocessError, ValueError):
        return "Hyprland not reachable"
    if panel is None:
        return "no laptop panel found"
    argv = monitor_argv(panel, hz)
    if argv is None:
        return f"already {hz} Hz or not supported"
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        return f"could not switch: {exc}"
    return (
        f"switched to {hz} Hz"
        if result.stdout.strip() == "ok"
        else result.stdout.strip()
    )
