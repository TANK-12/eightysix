"""Code - VS Code inside Forge, via OpenVSCode Server (Gitpod, MIT).

OpenVSCode Server is a Node program with its own web server, so this app is a
small wrapper around it: on start it launches `openvscode-server/` on a local
port and with a connection token that are both kept across starts (see
keep_port and keep_token for why), and the page (`static/`) frames the
editor. Everything the editor keeps (settings, extensions, history) lives in
`data/`, beside it, not in ~/.openvscode-server.

Security: the editor answers only with the connection token, and the token is
handed out only by `/api/session`, which needs the `X-Forge: 1` header (a web
page open in the Forge Browser cannot send it cross-origin). The editor is
bound to 127.0.0.1.

The editor stays in this process group, so Forge's close (SIGTERM to the
whole group) also ends it; the lifespan hook stops it on a normal shutdown.

Run standalone with:
    .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8460
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import time
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
SHARED_DIR = Path(os.environ.get("FORGE_SHARED_DIR", ROOT.parent.parent / "shared"))
SERVER_DIR = ROOT / "openvscode-server"
DATA_DIR = Path(os.environ.get("CODE_DATA_DIR", ROOT / "data"))
HOME = Path.home()

# Defaults for the editor (see write_defaults_extension); Emerson's own settings win.
DEFAULT_SETTINGS = {
    "workbench.colorTheme": "Default Dark Modern",
    "workbench.startupEditor": "none",
    # The chat panel on the right stays shut until opened (Ctrl+Alt+I).
    "workbench.secondarySideBar.defaultVisibility": "hidden",
    "window.menuBarVisibility": "compact",
    "editor.fontFamily": "'CaskaydiaCove Nerd Font Mono', 'JetBrains Mono', 'DejaVu Sans Mono', monospace",
    "editor.fontLigatures": True,
    "editor.fontSize": 14,
    "terminal.integrated.fontFamily": "'CaskaydiaCove Nerd Font Mono', monospace",
    "files.autoSave": "afterDelay",
    # A personal editor on Emerson's own files: no "do you trust this folder?" prompt.
    "security.workspace.trust.enabled": False,
    "telemetry.telemetryLevel": "off",
    "update.mode": "none",
    # Forge's neutrals, so the editor sits in the same frame as every other app.
    "workbench.colorCustomizations": {
        "editor.background": "#0f1115",
        "sideBar.background": "#171a21",
        "activityBar.background": "#171a21",
        "panel.background": "#0f1115",
        "terminal.background": "#0f1115",
        "titleBar.activeBackground": "#171a21",
        "statusBar.background": "#171a21",
        "tab.inactiveBackground": "#171a21",
        "editorGroupHeader.tabsBackground": "#171a21",
        "focusBorder": "#6ea8fe",
    },
}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def port_is_free(port: int) -> bool:
    # SO_REUSEADDR, as node sets it: a port the editor just let go of still
    # counts as free while its old connections wind down.
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def keep_port(data_dir: Path) -> int:
    """The editor's port, the same one every start while it is free.

    The editor keeps a person's settings and layout in the browser, per
    address, so a new port each start forgot them all."""
    saved = data_dir / "editor-port"
    try:
        port = int(saved.read_text())
    except (OSError, ValueError):
        port = 0
    if not (1024 < port < 65536 and port_is_free(port)):
        port = free_port()
        saved.write_text(str(port))
    return port


def keep_token(data_dir: Path) -> str:
    """The connection token, kept across starts in a private file.

    The editor's page remembers the token in a cookie. A fresh token each
    start left an open or reloaded page holding the old one, and the editor
    refused it over and over ("auth mismatch")."""
    path = data_dir / "connection-token"
    try:
        token = path.read_text().strip()
    except OSError:
        token = ""
    if len(token) < 24:
        token = secrets.token_urlsafe(24)
        path.write_text(token)
    path.chmod(0o600)
    return token


def hide_missing_browser_entries(server_dir: Path) -> list[str]:
    """Built-in extensions whose in-browser half OpenVSCode doesn't ship.

    git-base, emmet and a few others name a dist/browser file that isn't in
    the download, so the browser asked for it and failed on every start.
    Without the `browser` entry they run in the server's extension host, as
    they do in desktop VS Code. Returns the extensions changed."""
    changed = []
    for manifest in sorted((server_dir / "extensions").glob("*/package.json")):
        try:
            data = json.loads(manifest.read_text())
        except (OSError, ValueError):
            continue
        entry = data.get("browser")
        if not isinstance(entry, str) or not data.get("main"):
            continue
        target = manifest.parent / entry
        if target.exists() or target.with_name(target.name + ".js").exists():
            continue
        del data["browser"]
        manifest.write_text(json.dumps(data, indent=2) + "\n")
        changed.append(manifest.parent.name)
    return changed


def server_command(
    server_dir: Path, port: int, token_file: Path, data_dir: Path
) -> list[str]:
    # node + server-main.js directly: bin/openvscode-server is a shell script
    # that doesn't exec, so stopping it would leave node running.
    return [
        str(server_dir / "node"),
        str(server_dir / "out" / "server-main.js"),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--connection-token-file",
        str(token_file),
        "--server-data-dir",
        str(data_dir),
        "--telemetry-level",
        "off",
        "--accept-server-license-terms",
        # A personal editor on Emerson's own files: no Restricted Mode. The
        # setting can't do this in the web build (it is read from the
        # browser's own settings before any default applies); this can.
        "--disable-workspace-trust",
    ]


def write_defaults_extension(server_dir: Path) -> Path:
    """Forge's defaults as a tiny built-in extension (`configurationDefaults`).

    OpenVSCode keeps a person's own settings in the browser, so a server-side
    settings.json is never read. Defaults from an extension are: they apply
    everywhere and anything Emerson sets himself still wins. Rewritten on
    every start, so it survives replacing `openvscode-server/` with a newer one.
    """
    ext = server_dir / "extensions" / "forge-defaults"
    ext.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": "forge-defaults",
        "displayName": "Forge defaults",
        "description": "Forge's look and behaviour for the Code app. Your own settings override these.",
        "publisher": "forge",
        "version": "1.0.0",
        "engines": {"vscode": "*"},
        "contributes": {"configurationDefaults": DEFAULT_SETTINGS},
    }
    path = ext / "package.json"
    text = json.dumps(manifest, indent=2) + "\n"
    if not path.exists() or path.read_text() != text:
        path.write_text(text)
    return path


def write_machine_settings(data_dir: Path) -> Path:
    """The server-side ("Remote [Machine]") settings, for the few an extension
    can't default. Only keys missing from the file are added."""
    path = data_dir / "data" / "Machine" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        current = json.loads(path.read_text())
    except (OSError, ValueError):
        current = {}
    wanted = {"security.workspace.trust.enabled": False}
    merged = {**wanted, **current}
    if merged != current:
        path.write_text(json.dumps(merged, indent=2) + "\n")
    return path


class Editor:
    """The one OpenVSCode Server process this app runs."""

    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self.port = 0
        self.token = ""
        self.error = ""

    def start(self) -> None:
        node, main = SERVER_DIR / "node", SERVER_DIR / "out" / "server-main.js"
        if not (node.exists() and main.exists()):
            self.error = f"{SERVER_DIR} is missing; see README.md to fetch it"
            return
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        write_defaults_extension(SERVER_DIR)
        write_machine_settings(DATA_DIR)
        hide_missing_browser_entries(SERVER_DIR)
        self.port = keep_port(DATA_DIR)
        self.token = keep_token(DATA_DIR)
        log = open(DATA_DIR / "server.log", "w")
        self.proc = subprocess.Popen(
            server_command(
                SERVER_DIR, self.port, DATA_DIR / "connection-token", DATA_DIR
            ),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            cwd=HOME,
        )

    def ready(self) -> bool:
        if not self.proc or self.proc.poll() is not None:
            return False
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{self.port}/version", timeout=1)
            return True
        except OSError:
            return False

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def status(self) -> dict:
        running = bool(self.proc and self.proc.poll() is None)
        if self.proc and not running and not self.error:
            self.error = (
                f"the editor stopped (exit {self.proc.returncode}); see data/server.log"
            )
        return {
            "ready": running and self.ready(),
            "error": self.error,
            "base": f"http://127.0.0.1:{self.port}" if running else "",
            "token": self.token if running else "",
            "home": str(HOME),
        }


def editor_url(base: str, token: str, folder: str, file: str | None = None) -> str:
    """The address that opens `folder` in the editor, with `file` open in it."""
    url = f"{base}/?tkn={quote(token)}&folder={quote(folder)}"
    if file:
        host = base.split("://", 1)[1]
        payload = json.dumps([["openFile", f"vscode-remote://{host}{quote(file)}"]])
        url += f"&payload={quote(payload)}"
    return url


editor = Editor()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    editor.start()
    yield
    editor.stop()


app = FastAPI(title="Forge Code", lifespan=lifespan)


def forge_only(x_forge: str | None = Header(default=None)) -> None:
    if x_forge != "1":
        raise HTTPException(403, "Send X-Forge: 1")


guard = [Depends(forge_only)]


@app.get("/api/session", dependencies=guard)
def session() -> dict:
    return editor.status()


@app.get("/api/url", dependencies=guard)
def url(path: str = "", root: str = "") -> dict:
    """Where to point the frame for a folder or a file. A file opens inside `root`
    (the folder already open) when it lies under it, otherwise inside its own folder."""
    st = editor.status()
    if not st["ready"]:
        raise HTTPException(503, st["error"] or "The editor is still starting")
    # A path the OS can't even look up (a NUL byte, a name past the length
    # limit) is the caller's mistake: 400, never a 500.
    try:
        p = Path(os.path.expanduser(path or str(HOME))).resolve()
        if not p.exists():
            raise HTTPException(404, f"{p} doesn't exist")
        folder, file = (p, None) if p.is_dir() else (p.parent, p)
        if file and root:
            r = Path(root).resolve()
            if r.is_dir() and r in file.parents:
                folder = r
    except (ValueError, OSError) as e:
        raise HTTPException(400, f"That path can't be opened: {e}")
    return {
        "url": editor_url(
            st["base"], st["token"], str(folder), str(file) if file else None
        ),
        "folder": str(folder),
        "file": str(file) if file else None,
    }


@app.post("/api/restart", dependencies=guard)
def restart() -> dict:
    editor.stop()
    editor.error = ""
    editor.start()
    for _ in range(100):
        if editor.ready():
            break
        time.sleep(0.1)
    return editor.status()


if SHARED_DIR.is_dir():
    app.mount("/shared", StaticFiles(directory=str(SHARED_DIR)), name="shared")
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
