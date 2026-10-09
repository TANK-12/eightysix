"""Claude - Claude Code inside Forge, linked to the Forge Browser, with file attachments.

A thin HTTP layer over runner.py. Each conversation is a `claude -p` process in
streaming JSON mode; the page long-polls its events. Claude gets the Forge
Browser through browser_mcp.py (an MCP server), so it can open, search and
read the pages the user sees. Links in Claude's answers open in the Forge
Browser, and the page open there can be attached to a message.

Accounts: /api/profiles lists the account profiles (one Claude Code config
directory each), switches the active one, adds and removes them, and relays
`claude auth login` for a profile: the sign-in address goes to the page, the
code the sign-in page shows comes back and is fed to the CLI.

Every /api route requires the header `X-Forge: 1`. A web page open in the
Forge Browser cannot send a custom header to this port without a CORS
preflight this app never grants, so a page cannot talk to Claude through it.

Run standalone with:
    FORGE_SHARED_DIR=/home/ejb/Forge/shared \\
    .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8445
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

import avatar_chat
import clipboard
import docs_library
import personas
import projects
import roadmap
import names
import everyone
import runner
import voice as voice_mod
import voice_ask

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
SHARED_DIR = Path(os.environ.get("FORGE_SHARED_DIR", ROOT.parent.parent / "shared"))
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

import forge_avatars as avatars  # noqa: E402  (shared: models, motions, puppets)
import forge_accounts  # noqa: E402  (shared: web logins, accounts.json)
import forge_session_names  # noqa: E402  (shared: Relay task titles)
import forge_jan  # noqa: E402  (shared: this app's own Jan model settings)
import forge_theme  # noqa: E402  (shared: Forge settings, the archive hours)

conversations = runner.Registry()
conversations.archive_hours = lambda: float(
    forge_theme.load().get("claude_archive_hours", runner.AUTO_ARCHIVE_HOURS)
)
conversations.resume_after_restart = lambda: bool(
    forge_theme.load().get("claude_resume", True)
)
cast = personas.Personas(conversations.data_dir)
speaker = voice_mod.Voice(conversations.data_dir / "voice")
desk = voice_ask.VoiceDesk(lambda: conversations)
jan = forge_jan.AppJan("claude", roles=("motions", "chat"))
chats = avatar_chat.History(conversations.data_dir / "avatar_chat")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Conversations cut off by Forge quitting or a reboot carry on (on a
    # thread, one at a time); Forge starts this app at launch for it.
    conversations.resume_interrupted()
    claude_version.get()  # start working it out before the page asks
    yield
    conversations.stop_all()
    speaker.stop()
    jan.stop()


def forge_only(x_forge: str | None = Header(default=None)) -> None:
    if x_forge != "1":
        raise HTTPException(403, "Send X-Forge: 1")


class SafeJSON(JSONResponse):
    """JSON with every non-ASCII character escaped: a lone UTF-16 half (an
    emoji cut in two) in a stored title or event then goes out as \\udXXX
    instead of failing the whole response with a 500."""

    def render(self, content) -> bytes:
        return json.dumps(
            content, ensure_ascii=True, allow_nan=False, separators=(",", ":")
        ).encode("ascii")


app = FastAPI(
    title="Claude", lifespan=lifespan, dependencies=[], default_response_class=SafeJSON
)
guarded = [Depends(forge_only)]


def local_host(host: str | None = Header(default=None)) -> None:
    """Voice routes also need a local Host: a DNS-rebinding page counts as
    same-origin and can send X-Forge, but its Host is its own name."""
    if (host or "").rsplit(":", 1)[0] not in ("127.0.0.1", "localhost"):
        raise HTTPException(403, "Local host only")


voice_guarded = [Depends(forge_only), Depends(local_host)]


def browser(command: dict, timeout: float = 60) -> dict:
    """One command to the Forge Browser's queue."""
    request = urllib.request.Request(
        f"{runner.BROWSER_URL}/api/agent/do",
        data=json.dumps(command).encode(),
        headers={"Content-Type": "application/json", "X-Forge": "1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, OSError, ValueError) as e:
        return {"ok": False, "error": f"The Forge Browser did not answer ({e})"}


def conversation(conv_id: str) -> runner.Conversation:
    conv = conversations.get(conv_id)
    if conv is None:
        raise HTTPException(404, "No such conversation")
    return conv


class ClaudeVersion:
    """`claude --version`, worked out on a thread and kept: running it takes a
    second or more (up to 10 s on a slow start), and every page's first paint
    waits on /api/options. Re-checked in the background every 10 minutes, so
    an update shows without a restart."""

    MAX_AGE = 600.0

    def __init__(self) -> None:
        self.text = ""
        self.checked = 0.0
        self.done = threading.Event()
        self._lock = threading.Lock()
        self._running = False

    def _find(self) -> None:
        cmd = runner.claude_command()
        text = ""
        if cmd:
            try:
                text = subprocess.run(
                    [*cmd, "--version"], capture_output=True, text=True, timeout=10
                ).stdout.strip()
            except (OSError, subprocess.SubprocessError):
                text = ""
        with self._lock:
            self.text, self.checked, self._running = text, time.time(), False
        self.done.set()

    def get(self, wait: float = 0.0) -> str:
        with self._lock:
            stale = time.time() - self.checked > self.MAX_AGE
            if stale and not self._running:
                self._running = True
                threading.Thread(target=self._find, daemon=True).start()
        self.done.wait(wait)
        return self.text


claude_version = ClaudeVersion()


@app.get("/api/options", dependencies=guarded)
def options():
    cmd = runner.claude_command()
    version = claude_version.get(wait=0.3)
    try:
        with urllib.request.urlopen(f"{runner.BROWSER_URL}/api/state", timeout=0.6):
            browser_up = True
    except (urllib.error.URLError, OSError):
        browser_up = False
    return {
        "claude": bool(cmd),
        "version": version,
        "models": runner.MODELS,
        "efforts": runner.EFFORTS,
        "agent_limits": runner.AGENT_LIMITS,
        "ultracode": {"unsupported_models": runner.ULTRACODE_UNSUPPORTED},
        "modes": runner.MODES,
        "default_mode": runner.DEFAULT_MODE,
        "home": str(Path.home()),
        "browser": browser_up,
        "active_profile": conversations.profiles.active(),
    }


# --- accounts -------------------------------------------------------------------


def profile_name(name: str) -> str:
    if not conversations.profiles.exists(name):
        raise HTTPException(404, "No such account")
    return name


@app.get("/api/profiles", dependencies=guarded)
def list_profiles(refresh: int = 0):
    if refresh:
        for name in conversations.profiles.names():
            conversations.profiles.forget_status(name)
    return conversations.profiles.describe()


@app.post("/api/profiles", dependencies=guarded)
def add_profile(payload: dict):
    try:
        name = conversations.profiles.add(str(payload.get("name") or ""))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"name": name, **conversations.profiles.describe()}


@app.delete("/api/profiles/{name}", dependencies=guarded)
def remove_profile(name: str):
    try:
        conversations.profiles.remove(profile_name(name))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return conversations.profiles.describe()


@app.post("/api/profiles/{name}/activate", dependencies=guarded)
def activate_profile(name: str):
    """Make it the default account for new tabs. A conversation keeps the
    account it was created on for good."""
    conversations.profiles.set_active(profile_name(name))
    return conversations.profiles.describe()


@app.post("/api/profiles/{name}/login", dependencies=guarded)
def start_login(name: str):
    try:
        login = conversations.profiles.login(profile_name(name))
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    deadline = time.time() + 15
    while login.state == "starting" and login.running() and time.time() < deadline:
        time.sleep(0.1)
    return login.snapshot()


@app.get("/api/profiles/{name}/login", dependencies=guarded)
def login_state(name: str):
    state = conversations.profiles.login_state(profile_name(name))
    return state or {"profile": name, "state": "none"}


@app.post("/api/profiles/{name}/login/code", dependencies=guarded)
def login_code(name: str, payload: dict):
    login = conversations.profiles.logins.get(profile_name(name))
    code = str(payload.get("code") or "").strip()
    if not code:
        raise HTTPException(400, "Paste the code the sign-in page shows")
    if login is None:
        raise HTTPException(409, "No sign-in is running for that account")
    try:
        login.code(code)
    except (RuntimeError, OSError) as e:
        raise HTTPException(409, str(e))
    deadline = time.time() + 20
    while login.state == "checking" and time.time() < deadline:
        time.sleep(0.1)
    if login.state == "done":
        conversations.profiles.forget_status(name)
    return login.snapshot()


@app.post("/api/profiles/{name}/login/cancel", dependencies=guarded)
def cancel_login(name: str):
    login = conversations.profiles.logins.pop(profile_name(name), None)
    if login:
        login.cancel()
    return {"cancelled": bool(login)}


@app.get("/api/commands", dependencies=guarded)
def list_commands():
    """The slash commands and skills Claude Code reported when a session last
    started, for the / and . menu under the message box."""
    return {"commands": conversations.commands()}


@app.get("/api/conversations", dependencies=guarded)
def list_conversations():
    return {"conversations": conversations.list(), "focus": conversations.take_focus()}


@app.get("/api/sessions", dependencies=guarded)
def claude_sessions():
    """Claude Code session id -> the conversation running it, so the Board can
    show its name."""
    return {
        "sessions": {
            m["session_id"]: {
                "id": m["id"],
                "name": m.get("name", ""),
                "title": m.get("title", ""),
            }
            for m in conversations.list()
            if m.get("session_id")
        }
    }


@app.get("/api/everyone", dependencies=guarded)
def everyone_list():
    """Every Claude session (working, idle, cold) with its helper agents, and
    the tab that runs it when it is one of ours."""
    rows = everyone.sessions(
        Path.home() / ".claude/sessions", Path.home() / ".claude/projects"
    )
    for row in rows:
        row["relay"] = forge_session_names.relay_task(row["name"])
        meta = conversations.find_session(row["session_id"])
        row["conversation"] = (
            {"id": meta["id"], "title": meta.get("title", "")} if meta else None
        )
    return {"sessions": rows}


@app.post("/api/everyone/{session_id}/message", dependencies=guarded)
def everyone_message(session_id: str, payload: dict):
    text = str(payload.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "Write something")
    try:
        return everyone.message(session_id, text)
    except LookupError as e:
        raise HTTPException(404, str(e))


@app.post("/api/everyone/{session_id}/open", dependencies=guarded)
def everyone_open(session_id: str, payload: dict):
    """Our own tab opens; a cold session resumes in a new tab. A session running
    elsewhere is not resumed: two processes on one session would split it."""
    meta = conversations.find_session(session_id)
    if meta:
        return {"id": meta["id"]}
    if payload.get("state") != "cold":
        raise HTTPException(409, "It is running elsewhere; send it a message instead")
    conv = conversations.create(
        str(payload.get("cwd") or ""), "", runner.DEFAULT_MODE, "", ""
    )
    conv.meta["session_id"] = session_id
    conv.meta["title"] = "Resumed " + str(payload.get("name") or session_id[:8])
    conv.save_meta()
    return {"id": conv.meta["id"]}


@app.post("/api/sessions/{session_id}/focus", dependencies=guarded)
def focus_session(session_id: str, pid: int = 0):
    """Open the tab of the conversation running this session the next time the
    page looks (the Board's "Go to it" for sessions that are not in a terminal)."""
    meta = conversations.find_session(session_id, pid)
    if meta is None:
        raise HTTPException(404, "No conversation here runs that session")
    conversations.ask_focus(meta["id"])
    return {
        "id": meta["id"],
        "name": meta.get("name", ""),
        "title": meta.get("title", ""),
    }


@app.post("/api/conversations", dependencies=guarded)
def create_conversation(payload: dict):
    conv = conversations.create(
        str(payload.get("cwd") or ""),
        str(payload.get("model") or ""),
        str(payload.get("mode") or runner.DEFAULT_MODE),
        str(payload.get("profile") or ""),
        str(payload.get("effort") or ""),
    )
    return conv.snapshot()


@app.post("/api/conversations/{conv_id}/settings", dependencies=guarded)
def change_settings(conv_id: str, payload: dict):
    """Model, effort, ultracode, agent limits, permission level, folder or archived. They apply from the next message:
    the process is ended (after the turn in progress) so the next message starts with them.
    """
    conv = conversation(conv_id)
    # wrong types are refused before anything changes
    for key in ("model", "effort", "mode", "cwd", "title", "name"):
        if key in payload and not isinstance(payload[key], str):
            raise HTTPException(400, f"{key} must be text")
    if "folder" in payload and not isinstance(payload["folder"], (str, type(None))):
        raise HTTPException(400, "folder must be text")
    for key in ("ultracode", "archived"):
        if key in payload and not isinstance(payload[key], bool):
            raise HTTPException(400, f"{key} must be true or false")
    changed = False
    if "model" in payload and payload["model"] in runner.MODELS:
        changed |= conv.meta.get("model") != payload["model"]
        conv.meta["model"] = payload["model"]
    if "effort" in payload and payload["effort"] in runner.EFFORTS:
        changed |= conv.meta.get("effort", "") != payload["effort"]
        conv.meta["effort"] = payload["effort"]
    if isinstance(payload.get("ultracode"), bool):
        changed |= bool(conv.meta.get("ultracode")) != payload["ultracode"]
        conv.meta["ultracode"] = payload["ultracode"]
        if not payload["ultracode"]:
            conv.meta.pop("ultracode_state", None)
    if "limits" in payload:
        limits = dict(conv.meta.get("limits") or {})
        for key, value in runner.clean_limits(payload["limits"]).items():
            if value is None:
                limits.pop(key, None)
            else:
                limits[key] = value
        if limits != (conv.meta.get("limits") or {}):
            changed = True
            conv.meta["limits"] = limits
    if "mode" in payload and payload["mode"] in runner.MODES:
        changed |= conv.meta.get("mode") != payload["mode"]
        conv.meta["mode"] = payload["mode"]
    if "cwd" in payload:
        cwd = os.path.expanduser(str(payload["cwd"]))
        if not os.path.isdir(cwd):
            raise HTTPException(400, "That folder does not exist")
        changed |= conv.meta.get("cwd") != cwd
        conv.meta["cwd"] = cwd
    if "title" in payload:
        conv.meta["title"] = runner.clean_text(str(payload["title"]))[:80]
    if names.clean(payload.get("name") or ""):
        conv.meta["name"] = names.clean(runner.clean_text(payload["name"]))
    if "folder" in payload:
        try:
            conversations.file_into(conv_id, str(payload["folder"] or ""))
        except ValueError as e:
            raise HTTPException(400, str(e))
    if "archived" in payload:
        conversations.set_archived(conv_id, bool(payload["archived"]))
    conv.save_meta()
    if changed:
        # mid-turn, the process ends once the turn is over
        conv.close()
    return conv.snapshot()


# --- projects: the Enjoy layout (A15) -------------------------------------------


def project_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except KeyError as e:
        raise HTTPException(404, str(e.args[0]) if e.args else "Not found")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/roadmap", dependencies=guarded)
def get_roadmap():
    """The Enjoy layout's roadmap: session briefs and open board notes (A28)."""
    return roadmap.build(roadmap.SESSIONS, roadmap.BOARD)


@app.get("/api/docs", dependencies=guarded)
def list_docs(q: str = ""):
    """The Docs section: every doc from doc_sources.json, newest first."""
    return docs_library.listing(q)


@app.get("/api/docs/read", dependencies=guarded)
def read_doc(path: str):
    """One listed doc's text; anything not in the listing is refused."""
    try:
        return docs_library.read(path)
    except KeyError:
        raise HTTPException(404, "Not a listed doc")


@app.get("/api/projects", dependencies=guarded)
def list_projects():
    return projects.listing(conversations)


@app.post("/api/projects", dependencies=guarded)
def create_project(payload: dict):
    return project_call(
        projects.create,
        conversations,
        str(payload.get("name") or ""),
        str(payload.get("cwd") or ""),
    )


@app.post("/api/projects/{pid}", dependencies=guarded)
def update_project(pid: str, payload: dict):
    return project_call(
        projects.update,
        conversations,
        pid,
        cwd=payload.get("cwd"),
        workflows=payload.get("workflows"),
        name=payload.get("name"),
    )


@app.post("/api/projects/{pid}/workflows/{index}/run", dependencies=guarded)
def run_workflow(pid: str, index: int):
    """A saved workflow as a new task in its project, started at once."""
    project = project_call(projects.get, conversations, pid)
    flows = project["workflows"]
    if not 0 <= index < len(flows):
        raise HTTPException(404, "No such workflow")
    conv = conversations.create(project["cwd"], "", runner.DEFAULT_MODE, "", "")
    conversations.file_into(conv.meta["id"], project["name"])
    conv.meta["title"] = flows[index]["name"][:80]
    conv.save_meta()
    try:
        conv.send(projects.workflow_prompt(flows[index]), [])
    except (RuntimeError, ValueError) as e:
        raise HTTPException(409, str(e))
    return conv.snapshot()


@app.get("/api/projects/{pid}/notes", dependencies=guarded)
def list_notes(pid: str):
    return {"notes": project_call(projects.notes, conversations, pid)}


@app.get("/api/projects/{pid}/notes/{name}", dependencies=guarded)
def read_note(pid: str, name: str):
    return {
        "name": name,
        "text": project_call(projects.read_note, conversations, pid, name),
    }


@app.post("/api/projects/{pid}/notes", dependencies=guarded)
def save_note(pid: str, payload: dict):
    return project_call(
        projects.save_note,
        conversations,
        pid,
        str(payload.get("name") or ""),
        str(payload.get("text") or ""),
    )


@app.delete("/api/projects/{pid}/notes/{name}", dependencies=guarded)
def delete_note(pid: str, name: str):
    project_call(projects.delete_note, conversations, pid, name)
    return {"ok": True}


@app.post("/api/conversations/{conv_id}/seen", dependencies=guarded)
def mark_seen(conv_id: str):
    conversation(conv_id).mark_seen()
    return {"ok": True}


# --- folders of conversations ---------------------------------------------------


def folder_call(fn, *args, **kwargs):
    try:
        return {"folders": fn(*args, **kwargs)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/folders", dependencies=guarded)
def list_folders():
    return {"folders": conversations.folders()}


@app.post("/api/folders", dependencies=guarded)
def add_folder(payload: dict):
    return folder_call(conversations.add_folder, str(payload.get("name") or ""))


@app.post("/api/folders/update", dependencies=guarded)
def update_folder(payload: dict):
    collapsed = payload.get("collapsed")
    return folder_call(
        conversations.update_folder,
        str(payload.get("name") or ""),
        new_name=payload.get("new_name"),
        collapsed=None if collapsed is None else bool(collapsed),
    )


@app.post("/api/folders/delete", dependencies=guarded)
def delete_folder(payload: dict):
    return folder_call(conversations.delete_folder, str(payload.get("name") or ""))


@app.delete("/api/conversations/{conv_id}", dependencies=guarded)
def delete_conversation(conv_id: str):
    if not conversations.delete(conv_id):
        raise HTTPException(404, "No such conversation")
    return {"ok": True}


@app.get("/api/conversations/{conv_id}/events", dependencies=guarded)
def events(conv_id: str, after: int = -1, wait: float = 0, boot: str = ""):
    """Events after `after`. `boot` is the id the page got with its last
    answer: when the backend restarted since (or the page is past the end,
    an old page with no boot id), seq numbers no longer match, so every event
    comes back with reset=true and the page draws the conversation afresh."""
    conv = conversation(conv_id)
    reset = (bool(boot) and boot != conv.boot) or after >= len(conv.events)
    if reset:
        found = conv.events_after(-1)
    else:
        found = conv.events_after(after, max(0.0, min(25.0, wait)))
    return {
        "events": found,
        "busy": conv.busy,
        "meta": conv.snapshot(),
        "boot": conv.boot,
        "reset": reset,
    }


@app.post("/api/conversations/{conv_id}/send", dependencies=guarded)
def send(conv_id: str, payload: dict):
    conv = conversation(conv_id)
    text = payload.get("text") or ""
    listed = payload.get("files") or []
    if not isinstance(text, str):
        raise HTTPException(400, "text must be text")
    if not isinstance(listed, list) or not all(isinstance(n, str) for n in listed):
        raise HTTPException(400, "files must be a list of file names")
    names = [runner.safe_name(n) for n in listed]
    files = [conv.attachments / n for n in names if (conv.attachments / n).is_file()]
    if not text.strip() and not files:
        raise HTTPException(400, "Write something or attach a file")
    try:
        conv.send(text, files)
    except RuntimeError as e:
        # Claude Code could not be started or reached: not a server crash
        raise HTTPException(503, str(e))
    return {"ok": True}


@app.post("/api/conversations/{conv_id}/stop", dependencies=guarded)
def stop(conv_id: str):
    return {"stopped": conversation(conv_id).stop()}


@app.post("/api/conversations/{conv_id}/close", dependencies=guarded)
def close(conv_id: str):
    """Its tab closed; the process ends once any running turn is done."""
    return {"closed": conversation(conv_id).close()}


@app.post("/api/conversations/{conv_id}/files", dependencies=guarded)
def upload(conv_id: str, payload: dict):
    """A file as base64 JSON, so no multipart dependency is needed."""
    conv = conversation(conv_id)
    try:
        data = base64.b64decode(str(payload.get("data") or ""), validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "The file data is not base64")
    try:
        path = conv.save_attachment(str(payload.get("name") or "file"), data)
    except ValueError as e:
        raise HTTPException(413, str(e))
    return {"name": path.name, "path": str(path), "bytes": len(data)}


@app.post("/api/conversations/{conv_id}/paste-image", dependencies=guarded)
def paste_image(conv_id: str):
    """The image on the desktop clipboard, attached as a file. The page asks
    for this when a paste brought no file with it (WebKitGTK and a copied
    screenshot)."""
    conv = conversation(conv_id)
    found = clipboard.read_image()
    if found is None:
        raise HTTPException(404, "There is no image on the clipboard")
    data, media = found
    try:
        path = conv.save_attachment("pasted" + clipboard.EXTENSIONS[media], data)
    except ValueError as e:
        raise HTTPException(413, str(e))
    return {"name": path.name, "path": str(path), "bytes": len(data)}


@app.get("/api/conversations/{conv_id}/files/{name}")
def attached_image(conv_id: str, name: str):
    """An image attached to this conversation, for thumbnails. Unguarded
    because an <img> cannot send headers, so it serves images only, and only
    from the conversation's own attachment folder."""
    conv = conversation(conv_id)
    path = conv.attachments / runner.safe_name(name)
    media = runner.IMAGE_TYPES.get(path.suffix.lower())
    if media is None or not path.is_file():
        raise HTTPException(404, "No such image")
    return FileResponse(path, media_type=media)


@app.post("/api/clipboard/image", dependencies=guarded)
def copy_image(payload: dict):
    """Put an image from a reply on the desktop clipboard."""
    try:
        data = base64.b64decode(str(payload.get("data") or ""), validate=True)
        clipboard.write_image(data, str(payload.get("media") or ""))
    except (binascii.Error, ValueError) as e:
        raise HTTPException(400, str(e) or "Not an image")
    except OSError as e:
        raise HTTPException(503, str(e))
    return {"ok": True, "bytes": len(data)}


@app.post("/api/conversations/{conv_id}/attach-page", dependencies=guarded)
def attach_page(conv_id: str, payload: dict | None = None):
    """The page open in the Forge Browser, saved as a text file to attach."""
    conv = conversation(conv_id)
    command = {"op": "read", "max_chars": 200000}
    if payload and payload.get("tab") is not None:
        command["tab"] = payload["tab"]
    answer = browser(command)
    page = answer.get("page") or {}
    if not answer.get("ok") or page.get("url", "about:blank") == "about:blank":
        raise HTTPException(
            409, answer.get("error") or "No page is open in the Browser"
        )
    title = page.get("title") or page.get("url")
    body = f"# {title}\n\nAddress: {page.get('url')}\n\n{page.get('text', '')}\n"
    links = page.get("links") or []
    if links:
        body += "\n## Links\n\n" + "\n".join(
            f"- {l.get('text') or l.get('href')}: {l.get('href')}" for l in links
        )
    name = "page - " + re.sub(r"[^\w\- ]+", " ", str(title))[:60].strip() + ".md"
    path = conv.save_attachment(name, body.encode())
    return {
        "name": path.name,
        "path": str(path),
        "bytes": path.stat().st_size,
        "url": page.get("url"),
    }


@app.post("/api/open-link", dependencies=guarded)
def open_link(payload: dict):
    url = str(payload.get("url") or "")
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "Only web addresses open in the Browser")
    return browser({"op": "open", "url": url, "new_tab": True})


# --- web logins (shared/accounts.json) ------------------------------------------


@app.get("/api/web-accounts", dependencies=guarded)
def web_accounts():
    try:
        rows = forge_accounts.describe()
    except (OSError, ValueError, forge_accounts.AccountError) as e:
        raise HTTPException(500, f"accounts.json: {e}")
    return {
        "accounts": [
            {k: r.get(k) for k in ("id", "label", "kind", "url", "open")} for r in rows
        ]
    }


@app.post("/api/web-accounts/{account_id}/open", dependencies=guarded)
def open_web_account(account_id: str):
    try:
        return {"message": forge_accounts.open_account(account_id)}
    except forge_accounts.AccountError as e:
        raise HTTPException(400, str(e))


# --- personas, avatars and voice ------------------------------------------------


def avatar_call(fn, *args):
    try:
        return fn(*args)
    except avatars.AvatarError as e:
        raise HTTPException(400, str(e))


@app.get("/api/personas", dependencies=guarded)
def list_personas():
    return {"personas": cast.all(), "prefs": cast.prefs(), "moods": personas.MOODS}


@app.post("/api/personas/prefs", dependencies=guarded)
def persona_prefs(payload: dict):
    try:
        prefs = cast.save_prefs(payload)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"personas": cast.all(), "prefs": prefs}


@app.get("/api/avatars", dependencies=guarded)
def list_avatars():
    return {
        "models": avatars.list_models(),
        "puppets": avatars.list_puppets(),
        "recipes": avatars.load_recipes(),
        "puppet_fields": avatars.PUPPET_FIELDS,
        "puppet_colours": avatars.PUPPET_COLOURS,
        "puppet_numbers": avatars.PUPPET_NUMBERS,
    }


@app.get("/api/avatars/live2d/{model_id}/motions", dependencies=guarded)
def model_motions(model_id: str):
    """Writes any recipe motions this model is missing, then lists them."""
    return {"motions": avatar_call(avatars.ensure_motions, model_id)}


@app.post("/api/avatars/motions/improvise", dependencies=guarded)
def improvise_motion(payload: dict):
    seed = payload.get("seed")
    return avatars.improvise(
        int(seed) if seed not in (None, "") else None, str(payload.get("mood") or "")
    )


@app.post("/api/avatars/motions/describe", dependencies=guarded)
def describe_motion(payload: dict):
    """A motion from a sentence, made by this app's own Jan model."""
    text = str(payload.get("text") or "").strip()[:300]
    if not text:
        raise HTTPException(400, "Describe the motion first")
    model = jan.model_for("motions")
    if not model:
        raise HTTPException(503, "Jan has no models loaded or listed")
    try:
        with jan.using(model):
            reply = forge_jan.chat(
                model, avatars.JAN_MOTION_SYSTEM, text, temperature=0.6, max_tokens=700
            )
    except forge_jan.JanError as e:
        raise HTTPException(502, f"Jan: {e}")
    recipe = avatar_call(avatars.recipe_from_text, reply)
    recipe["label"] = recipe["label"] or text[:40]
    return recipe


@app.post("/api/avatars/motions", dependencies=guarded)
def save_motion(payload: dict):
    name = avatar_call(
        avatars.save_recipe, str(payload.get("name") or ""), payload.get("recipe")
    )
    return {"name": name, "recipes": avatars.load_recipes()}


@app.delete("/api/avatars/motions/{name}", dependencies=guarded)
def delete_motion(name: str):
    if not avatar_call(avatars.delete_recipe, name):
        raise HTTPException(404, "Only custom motions can be deleted")
    return {"recipes": avatars.load_recipes()}


@app.post("/api/avatars/puppets/random", dependencies=guarded)
def random_puppet(payload: dict):
    seed = payload.get("seed")
    return avatars.random_puppet(
        int(seed) if seed not in (None, "") else None,
        str(payload.get("body") or ""),
        str(payload.get("style") or ""),
    )


@app.post("/api/avatars/puppets", dependencies=guarded)
def save_puppet(payload: dict):
    slug = avatar_call(avatars.save_puppet, payload)
    return {"id": slug, "puppets": avatars.list_puppets()}


@app.delete("/api/avatars/puppets/{name}", dependencies=guarded)
def delete_puppet(name: str):
    if not avatar_call(avatars.delete_puppet, name):
        raise HTTPException(404, "No such puppet")
    return {"puppets": avatars.list_puppets()}


@app.post("/api/voice", dependencies=guarded)
def speak(payload: dict):
    text = str(payload.get("text") or "")
    chosen = re.sub(r"[^a-z_]", "", str(payload.get("voice") or "af_heart"))[:24]
    speed = float(payload.get("speed") or 1.0)
    # The Forge voice service first; this app's own Kokoro worker when it is down.
    wav = voice_mod.service_tts(text, chosen, speed)
    if wav is not None:
        return Response(wav, media_type="audio/wav")
    try:
        path = speaker.say(text, chosen, speed)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    return FileResponse(path, media_type="audio/wav")


@app.post("/api/voice/ask", dependencies=voice_guarded)
def voice_ask_route(payload: dict):
    """A spoken question for Claude: runs in the visible "Voice" conversation."""
    try:
        job_id = desk.ask(payload.get("text") or "", str(payload.get("source") or ""))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"id": job_id}


@app.get("/api/voice/reply", dependencies=voice_guarded)
def voice_reply_route(id: str, wait: float = 0):
    found = desk.reply(id, wait)
    if found is None:
        raise HTTPException(404, "No such voice turn")
    return found


@app.get("/api/avatars/chat/{persona_id}", dependencies=guarded)
def chat_history(persona_id: str):
    try:
        return {"history": chats.load(persona_id)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/avatars/chat/{persona_id}", dependencies=guarded)
def chat_clear(persona_id: str):
    try:
        chats.clear(persona_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"history": []}


@app.post("/api/avatars/chat/{persona_id}", dependencies=guarded)
def chat_with_avatar(persona_id: str, payload: dict):
    """A short in-character reply from this app's own Jan model (no Claude
    turn), with the reaction tag the stage plays."""
    persona = cast.all().get(persona_id)
    if not persona:
        raise HTTPException(404, "No such persona")
    text = str(payload.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "Say something first")
    # Prefer a model Jan already holds, so chatting never loads a second one
    # onto the shared iGPU (Emerson's local-compute rule).
    loaded = forge_jan.loaded_models()
    model = jan.model_for("chat", loaded[0] if loaded else "")
    if not model:
        raise HTTPException(503, "Jan has no models loaded or listed")
    msgs = avatar_chat.messages(persona, chats.load(persona_id), text)
    try:
        with jan.using(model):
            raw = forge_jan.chat(
                model,
                msgs[0]["content"],
                text,
                temperature=0.8,
                max_tokens=160,
                extra={"messages": msgs},
            )
    except forge_jan.JanError as e:
        raise HTTPException(502, f"Jan: {e}")
    reply, tag = avatar_chat.parse_reply(raw)
    history = chats.add(persona_id, text[: avatar_chat.MAX_TEXT], reply, tag)
    return {"reply": reply, "tag": tag, "model": model, "history": history}


# --- static -------------------------------------------------------------------

if SHARED_DIR.is_dir():
    app.mount("/shared", StaticFiles(directory=str(SHARED_DIR)), name="shared")


@app.get("/")
def index():
    target = STATIC_DIR / "index.html"
    if not target.is_file():
        return JSONResponse({"error": "static/index.html is missing"}, status_code=500)
    return FileResponse(target)


if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
