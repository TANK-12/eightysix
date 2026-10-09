"""Window titles in Hyprland: what was open, not just which app. Only runs in
a Hyprland session; in GNOME or Plasma it returns nothing (the apps feeder
covers those)."""

from __future__ import annotations

import json
import os
import subprocess
import time

NAME = "hyprland"
LABEL = "Hyprland windows"
DESCRIPTION = "New windows and their titles (Hyprland sessions only)."
DEFAULT_ON = True
INTERVAL = 15


def clients() -> list[dict] | None:
    if not os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return None
    try:
        out = subprocess.run(
            ["hyprctl", "clients", "-j"], capture_output=True, text=True, timeout=5
        ).stdout
        return json.loads(out)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def collect(
    state: dict, now: float | None = None, windows: list[dict] | None = None
) -> list[dict]:
    windows = clients() if windows is None else windows
    if windows is None:
        return []
    now = time.time() if now is None else now
    current = {str(w["address"]): w for w in windows if w.get("address")}
    first = "seen" not in state
    seen = set(state.get("seen", []))
    state["seen"] = sorted(current)
    if first:
        return []
    events = []
    for address in sorted(set(current) - seen):
        w = current[address]
        title = (w.get("title") or "").strip()
        klass = w.get("class") or "window"
        events.append(
            {
                "ts": now,
                "source": NAME,
                "kind": "app_open",
                "title": f"{klass}: {title}"[:200] if title else f"New {klass} window",
                "tags": [klass[:30]],
                "key": f"hyprland:{address}",
            }
        )
    return events
