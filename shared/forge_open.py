"""Ask the running Forge window to show one of its apps.

Forge listens on a Unix socket in the runtime folder. A caller (Acchan's
launch_app, or `forge.py --app <name>` started while Forge is already open)
sends one line, `open <name>`, and gets `ok` back when Forge knows that app
or `unknown` when it does not. `open` with no name is only a ping. A plain
`forge.py` launched while Forge runs hidden in the background sends
`show <token>` instead: the running window comes up, and the desktop's
activation token lets GNOME or Hyprland give it the focus. When nothing answers, the caller starts Forge
itself with `--app <name>`. Stdlib only: forge.py runs on the system python and
Acchan on its own venv, and both import this file from shared/.
"""

from __future__ import annotations

import json
import os
import socket
import threading
from pathlib import Path
from typing import Callable

FORGE_DIR = Path(__file__).resolve().parents[1]
APPS_DIR = FORGE_DIR / "apps"
FORGE_PY = FORGE_DIR / "forge.py"
SOCKET = (
    Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    / "forge"
    / "forge.sock"
)


def forge_apps(apps_dir: Path = APPS_DIR) -> list[dict]:
    """Every app with a readable forge_app.json: name, label, tagline."""
    found = []
    for manifest in sorted(Path(apps_dir).glob("*/forge_app.json")):
        try:
            data = json.loads(manifest.read_text())
        except (OSError, ValueError):
            continue
        name = data.get("name") or manifest.parent.name
        found.append(
            {
                "name": name,
                "label": data.get("label") or name,
                "tagline": data.get("tagline", ""),
            }
        )
    return found


def request_open(name: str, path: Path = SOCKET, timeout: float = 2.0) -> str | None:
    """'ok' or 'unknown' from the running Forge, or None when none answers."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(timeout)
            conn.connect(str(path))
            conn.sendall(f"open {name}\n".encode())
            reply = conn.recv(64).decode(errors="replace").strip()
    except OSError:
        return None
    return reply or None


def request_show(
    token: str = "", path: Path = SOCKET, timeout: float = 2.0
) -> str | None:
    """Ask the running Forge to show its window; None when none answers.
    `token` is the launcher's XDG_ACTIVATION_TOKEN, passed on so the window
    may take the focus."""
    token = "".join(c for c in token if c.isprintable() and not c.isspace())[:200]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(timeout)
            conn.connect(str(path))
            conn.sendall(f"show {token}\n".encode())
            reply = conn.recv(64).decode(errors="replace").strip()
    except OSError:
        return None
    return reply or None


def forge_running() -> bool:
    """True when some forge.py process is running, socket or not (a Forge
    started before this file existed has no socket, and a second one must
    not be started beside it)."""
    me = os.getpid()
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit() or int(proc.name) == me:
            continue
        try:
            args = (proc / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        if any(a.endswith(b"Forge/forge.py") for a in args[:3]):
            return True
    return False


def serve(
    on_open: Callable[[str], bool],
    path: Path = SOCKET,
    on_show: Callable[[str], None] | None = None,
) -> socket.socket | None:
    """Answer `open <name>` and `show <token>` requests on a daemon thread.
    on_open runs on that thread and returns whether the app is known; on_show
    gets the activation token. Returns the listening socket (close it to
    stop), or None when another live Forge already answers."""
    if request_open("", path=path, timeout=0.5) is not None:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)  # left behind by a Forge that crashed
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.listen(4)

    def loop() -> None:
        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                return  # closed
            with conn:
                try:
                    conn.settimeout(2)
                    line = conn.recv(256).decode(errors="replace").strip()
                    verb, _, name = line.partition(" ")
                    if verb == "show" and on_show is not None:
                        on_show(name)
                        known = True
                    else:
                        known = verb == "open" and (not name or on_open(name))
                    conn.sendall(b"ok\n" if known else b"unknown\n")
                except OSError:
                    continue

    threading.Thread(target=loop, daemon=True).start()
    return server
