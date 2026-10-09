"""Forge's own apps opening and closing. Each app has its own port (in its
forge_app.json); an app counts as open while something listens on that port.
Nothing in forge.py needs changing for this."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

NAME = "forge"
LABEL = "Forge apps"
DESCRIPTION = "Forge apps opening and closing."
DEFAULT_ON = True
INTERVAL = 20

APPS = Path(
    os.environ.get("CALENDAR_FORGE_APPS") or Path(__file__).resolve().parents[2]
)


def forge_ports(apps: Path = APPS) -> dict[int, str]:
    ports = {}
    for manifest in apps.glob("*/forge_app.json"):
        try:
            d = json.loads(manifest.read_text())
            ports[int(d["port"])] = (
                d.get("label") or d.get("name") or manifest.parent.name
            )
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return ports


def listening(proc_net=("/proc/net/tcp", "/proc/net/tcp6")) -> set[int]:
    ports = set()
    for path in proc_net:
        try:
            lines = Path(path).read_text().splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            parts = line.split()
            if len(parts) > 3 and parts[3] == "0A":  # LISTEN
                ports.add(int(parts[1].rsplit(":", 1)[1], 16))
    return ports


def collect(
    state: dict, now: float | None = None, ports=None, open_ports=None
) -> list[dict]:
    now = time.time() if now is None else now
    ports = forge_ports() if ports is None else ports
    open_ports = listening() if open_ports is None else open_ports
    running = {name for port, name in ports.items() if port in open_ports}
    first = "open" not in state
    was = set(state.get("open", []))
    state["open"] = sorted(running)
    if first:
        return []
    events = [
        {
            "ts": now,
            "source": NAME,
            "kind": "app_open",
            "title": f"Forge: opened {n}",
            "tags": [n[:30]],
            "key": f"forge:open:{n}:{int(now)}",
        }
        for n in sorted(running - was)
    ]
    events += [
        {
            "ts": now,
            "source": NAME,
            "kind": "app_close",
            "title": f"Forge: closed {n}",
            "tags": [n[:30]],
            "key": f"forge:close:{n}:{int(now)}",
        }
        for n in sorted(was - running)
    ]
    return events
