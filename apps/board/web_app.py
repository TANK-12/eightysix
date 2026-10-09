"""Board -- the page for the crew message board (~/.claude/skills/crew/crew.py).

Claude sessions post notes and claim Jan models from the command line; this
page shows the same board to Emerson, lets him post and answer notes, and puts
the claims next to the models Jan actually has loaded, so "who is using the 4B"
has one answer. All board reads and writes go through crew.py itself, under its
lock, so the page and the sessions can never disagree about the file format.
"""

from __future__ import annotations

import glob
import json
import urllib.request
import urllib.parse
import os
import subprocess
import sys
import time

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(ROOT, "static")
SHARED_DIR = os.environ.get("FORGE_SHARED_DIR") or os.path.join(
    ROOT, "..", "..", "shared"
)
CREW_DIR = os.environ.get("CREW_SKILL_DIR") or os.path.expanduser(
    "~/.claude/skills/crew"
)
sys.path.insert(0, os.path.abspath(SHARED_DIR))
sys.path.insert(0, CREW_DIR)

import crew  # noqa: E402  # pyright: ignore[reportMissingImports]
import forge_attach  # noqa: E402
import forge_attach_api  # noqa: E402
import forge_jan  # noqa: E402
import forge_helper_files  # noqa: E402
import forge_session_names  # noqa: E402

AUTHOR = "Emerson"
DEFAULT_CREW = "jan"
PAGE_CREW = "forge"
SESSIONS_DIR = os.environ.get("CLAUDE_SESSIONS_DIR") or os.path.expanduser(
    "~/.claude/sessions"
)
BRIEFS_DIR = os.environ.get("FORGE_BRIEFS_DIR") or os.path.abspath(
    os.path.join(ROOT, "..", "..", "sessions")
)

app = FastAPI(title="Board")
# Files and pictures attached to a note (Relay task 118): saved here and named
# in the note as "Attached files:" lines the sessions open.
ATTACH = forge_attach_api.Attachments(
    lambda: os.environ.get("BOARD_ATTACH_DIR")
    or os.path.expanduser("~/.local/share/forge/board/attachments"),
    what="note",
)
app.include_router(ATTACH.router())
_last_ticks: dict[str, int] = {}


# Sizes are capped (422 beyond): every note is re-sent on each 3 s refresh,
# and a 200 kB recipient name once pushed the whole page off screen.
class Post(BaseModel):
    text: str = Field(max_length=20000)
    to: str | None = Field(None, max_length=80)
    re: int | None = None
    fyi: bool = False
    files: list[str] = Field(default_factory=list, max_length=20)


class Notice(BaseModel):
    title: str
    body: str = ""


class Ack(BaseModel):
    note: str = Field("", max_length=4000)
    close: bool = False


def _crew_names() -> list[str]:
    root = os.path.dirname(crew.crew_dir("x"))
    names = (
        sorted(n for n in os.listdir(root) if os.path.isdir(os.path.join(root, n)))
        if os.path.isdir(root)
        else []
    )
    return names if DEFAULT_CREW in names else [DEFAULT_CREW, *names]


def _check(name: str) -> str:
    if name not in _crew_names():
        raise HTTPException(404, f"no board called {name}")
    return name


def _run(name: str, *argv: str) -> dict:
    """Run one crew.py command against a board and return the board after it."""
    args = crew.parser().parse_args([argv[0], name, *argv[1:]])
    try:
        with crew.open_board(name) as board:
            crew.COMMANDS[args.cmd](board, args)
            return board
    except crew.CrewError as e:
        raise HTTPException(400, str(e))


def jan_status(proc_dir: str = "/proc") -> list[dict]:
    """Each loaded Jan model, and whether it used CPU since the last look."""
    ticks = forge_jan.cpu_ticks(proc_dir)
    out = []
    for model in forge_jan.loaded_models(proc_dir):
        before = _last_ticks.get(model)
        now = ticks.get(model)
        out.append({"model": model, "busy": None if before is None else now != before})
    _last_ticks.clear()
    _last_ticks.update(ticks)
    return out


def _alive(pid) -> bool:
    return isinstance(pid, int) and os.path.exists(f"/proc/{pid}")


# Terminals whose tabs can be switched from outside. GNOME Terminal is what
# Emerson runs sessions in; another terminal is one more entry here.
TERMINALS = {
    "gnome-terminal-": {
        "dest": "org.gnome.Terminal",
        "window": "/org/gnome/Terminal/window/1",
        "app": "/org/gnome/Terminal",
    },
}


def _stat(pid: int, proc: str) -> tuple[int, str] | None:
    """(parent pid, command name) from /proc/<pid>/stat."""
    try:
        with open(os.path.join(proc, str(pid), "stat")) as f:
            raw = f.read()
    except OSError:
        return None
    comm = raw[raw.index("(") + 1 : raw.rindex(")")]
    return int(raw[raw.rindex(")") + 2 :].split()[1]), comm


def terminal_of(pid: int, proc: str = "/proc") -> dict | None:
    """The terminal tab a session runs in: the terminal server's pid and the
    tab's place, counted as that server's shells in the order they started
    (tabs open in that order, and a new tab goes on the end)."""
    child = pid
    while pid > 1:
        got = _stat(pid, proc)
        if not got:
            return None
        parent, comm = got
        if comm in TERMINALS:
            shells = sorted(
                int(p)
                for p in os.listdir(proc)
                if p.isdigit() and (_stat(int(p), proc) or (0, ""))[0] == pid
            )
            return {"server": pid, "tab": shells.index(child), "kind": comm}
        child, pid = pid, parent
    return None


def _gdbus(*args: str) -> bool:
    try:
        return (
            subprocess.run(
                ["gdbus", "call", "--session", *args], capture_output=True, timeout=5
            ).returncode
            == 0
        )
    except (OSError, subprocess.SubprocessError):
        return False


def _session_info(name: str) -> dict | None:
    for path in glob.glob(os.path.join(SESSIONS_DIR, "*.json")):
        try:
            with open(path) as f:
                info = json.load(f)
        except (OSError, ValueError):
            continue
        if info.get("name") == name and isinstance(info.get("pid"), int):
            return info
    return None


def _session_pid(name: str) -> int | None:
    info = _session_info(name)
    return info["pid"] if info else None


# Sessions started by the Claude app run in no terminal; that app shows them as
# tabs with human names. It is found by its manifest's role, not by name.
APPS_DIR = os.path.dirname(ROOT)


def _claude_app() -> dict | None:
    for path in sorted(glob.glob(os.path.join(APPS_DIR, "*", "forge_app.json"))):
        try:
            with open(path) as f:
                manifest = json.load(f)
        except (OSError, ValueError):
            continue
        if manifest.get("role") == "claude" and manifest.get("port"):
            return manifest
    return None


def _claude_call(path: str, method: str = "GET") -> dict | None:
    """The Claude app's JSON answer, or None when it is closed or says no."""
    app_info = _claude_app()
    if not app_info:
        return None
    req = urllib.request.Request(
        f"http://127.0.0.1:{app_info['port']}{path}",
        method=method,
        headers={"X-Forge": "1"},
        data=b"" if method == "POST" else None,
    )
    try:
        with urllib.request.urlopen(req, timeout=1.5) as reply:
            return json.load(reply)
    except (OSError, ValueError):
        return None


_names_cache: tuple[float, dict] = (0.0, {})


def claude_names() -> dict:
    """Claude Code session id -> its conversation in the Claude app (name,
    title). Asked at most every 10 seconds; empty while the app is closed."""
    global _names_cache
    if time.time() - _names_cache[0] > 10:
        got = _claude_call("/api/sessions") or {}
        _names_cache = (time.time(), got.get("sessions") or {})
    return _names_cache[1]


def _forge_show(app_name: str) -> bool:
    """Ask the running Forge window to show an app (shared/forge_open.py)."""
    import forge_open  # noqa: E402  # pyright: ignore[reportMissingImports]

    return forge_open.request_open(app_name) == "ok"


def brief_for(slot: str | None) -> dict | None:
    """The session brief for a slot (sessions/<date>-S2-*.md): title and State lines."""
    if not slot:
        return None
    paths = sorted(glob.glob(os.path.join(BRIEFS_DIR, f"*-{slot}-*.md")))
    if not paths:
        return None
    path = paths[-1]
    with open(path) as f:
        lines = f.read().splitlines()
    title = next((l.lstrip("# ").strip() for l in lines if l.startswith("# ")), "")
    state, inside = [], False
    for line in lines:
        if line.startswith("## "):
            inside = line.strip().lower() == "## state"
        elif inside and line.strip().startswith(("-", "*")):
            state.append(line.strip())
    return {
        "path": path,
        "file": os.path.basename(path),
        "title": title,
        "state": state[:12],
    }


# A session that has written nothing for this long is not active, whatever
# its file says (Emerson, 2026-09-30: "none active for the past 5 mins").
ACTIVE_SECONDS = 300
AGENTS_SHOWN_FOR = 3600  # finished agents stay on the card this long


def _mtime(path: str) -> float:
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def session_dirs(session_id: str) -> tuple[list[str], list[str]]:
    """The transcript files of a session and its agents' meta files, from
    projects/*/ next to the sessions folder."""
    projects = os.path.join(os.path.dirname(SESSIONS_DIR), "projects")
    sid = glob.escape(session_id)
    return (
        glob.glob(os.path.join(projects, "*", f"{sid}.jsonl")),
        [
            meta
            for folder in glob.glob(os.path.join(projects, "*", sid, "subagents"))
            for meta in forge_helper_files.metas(folder)
        ],
    )


def agents_of(metas: list[str], now: float) -> list[dict]:
    """The agents (subagents) a session launched, newest first: what each is
    for, its type and model, and whether it is still writing."""
    out = []
    for meta in metas:
        try:
            with open(meta) as f:
                info = json.load(f)
        except (OSError, ValueError):
            continue
        last = max(_mtime(meta), _mtime(meta[: -len(".meta.json")] + ".jsonl"))
        if now - last > AGENTS_SHOWN_FOR:
            continue
        out.append(
            {
                "description": str(info.get("description") or "agent"),
                "type": str(info.get("agentType") or ""),
                "model": str(info.get("model") or ""),
                "background": info.get("requestShape") == "background",
                "since": _mtime(meta),
                "last": last,
                "running": now - last < ACTIVE_SECONDS,
            }
        )
    out.sort(key=lambda a: a["since"], reverse=True)
    return out


def live_sessions(board_data: dict) -> list[dict]:
    """Every running Claude session, with its slot and brief when it joined the board."""
    members = board_data.get("members", {})
    # one rule for every Forge page: the Claude app's tab name, else the name
    # any crew board gave the session (shared/forge_session_names.py)
    names = forge_session_names.labels(
        os.path.normpath(crew.crew_dir("")),
        app_names={
            sid: str(c.get("name") or "")
            for sid, c in claude_names().items()
            if isinstance(c, dict)
        },
    )
    out = []
    for path in glob.glob(os.path.join(SESSIONS_DIR, "*.json")):
        try:
            with open(path) as f:
                info = json.load(f)
        except (OSError, ValueError):
            continue
        if not _alive(info.get("pid")):
            continue
        name = info.get("name") or "?"
        member = members.get(name, {})
        slot = member.get("slot")
        session_id = info.get("sessionId") or ""
        conv = claude_names().get(session_id) or {}
        now = time.time()
        transcripts, metas = session_dirs(session_id) if session_id else ([], [])
        agents = agents_of(metas, now)
        last_active = max(
            [(info.get(k) or 0) / 1000 for k in ("startedAt", "updatedAt")]
            + [_mtime(t) for t in transcripts]
            + [a["last"] for a in agents]
        )
        active = now - last_active < ACTIVE_SECONDS
        status = info.get("status", "")
        if status == "busy" and not active:
            status = "idle"
        out.append(
            {
                "name": name,
                "label": names.get(session_id) or member.get("persona", ""),
                "topic": conv.get("title", ""),
                "status": status,
                "active": active,
                "last_active": last_active,
                "agents": agents,
                "kind": info.get("kind", ""),
                "since": (info.get("startedAt") or 0) / 1000,
                "on_board": name in members,
                "slot": slot,
                "last_seen": member.get("last_seen"),
                "brief": brief_for(slot),
            }
        )
    out.sort(key=lambda s: (s["slot"] or "~", s["name"]))
    return out


@app.get("/api/boards")
def boards():
    names = _crew_names()
    return {
        "boards": names,
        "default": PAGE_CREW if PAGE_CREW in names else DEFAULT_CREW,
    }


@app.get("/api/board/{name}")
def board(name: str):
    b = _run(_check(name), "dump")
    stale = {c["path"] for c in b["claims"] if crew.is_stale(b, c)}
    for c in b["claims"]:
        c["stale"] = c["path"] in stale
    jan_board = b if name == DEFAULT_CREW else _run(DEFAULT_CREW, "dump")
    jan_claims = [
        {**c, "stale": crew.is_stale(jan_board, c)}
        for c in jan_board["claims"]
        if c["path"].startswith("jan:")
    ]
    sessions = live_sessions(b)
    # a live session's Claude-app tab name wins on the notes too, so the
    # Board never shows a name the tab does not
    for x in sessions:
        member = b["members"].get(x["name"])
        if member is not None and x["label"]:
            member["persona"] = x["label"]
    return {
        "board": b,
        "jan": jan_status(),
        "jan_claims": jan_claims,
        "sessions": sessions,
        "me": AUTHOR,
        "now": time.time(),
    }


@app.post("/api/board/{name}/post")
def post(name: str, body: Post):
    text = forge_attach.with_note(body.text.strip(), ATTACH.paths(body.files))
    if not text:
        raise HTTPException(400, "empty note")
    # Options as --opt=value and the words after "--", so a note or a name
    # that starts with a dash ("--help", "-x") is kept as typed, not parsed.
    argv = ["post"] + ([f"--to={body.to}"] if body.to else [])
    argv += [f"--re={body.re}"] if body.re else []
    argv += ["--fyi"] if body.fyi else []
    _run(_check(name), *argv, "--", AUTHOR, text)
    return {"ok": True}


@app.post("/api/notify")
def notify(body: Notice):
    """A desktop notification for a new note to Emerson, sent by the page while
    it is out of sight, so he doesn't have to keep the Board open."""
    title = body.title.strip()
    if not title:
        raise HTTPException(400, "empty notification")
    subprocess.Popen(
        ["notify-send", "-a", "Board", "-i", "mail-unread", title, body.body[:300]],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return {"ok": True}


@app.post("/api/board/{name}/ack/{note_id}")
def ack(name: str, note_id: int, body: Ack):
    argv = ["ack"] + ([f"--note={body.note}"] if body.note else [])
    argv += ["--close"] if body.close else []
    _run(_check(name), *argv, "--", AUTHOR, str(note_id))
    return {"ok": True}


def _go_to_claude_app(info: dict) -> dict:
    """A session with no terminal: open its tab in the Claude app and bring
    that app up in Forge."""
    session_id = urllib.parse.quote(info.get("sessionId") or "-", safe="")
    conv = _claude_call(
        f"/api/sessions/{session_id}/focus?pid={info['pid']}", method="POST"
    )
    app_info = _claude_app()
    if not conv or not app_info:
        # Relay sessions run headless: there is no window to go to, so the
        # caller can show the conversation itself (Mission Control does)
        return {
            "ok": False,
            "nowhere": True,
            "reason": "that session is not in a terminal or in the Claude app",
        }
    shown = _forge_show(app_info["name"])
    return {
        "ok": True,
        "app": app_info["name"],
        "conversation": conv.get("name", ""),
        "reason": "" if shown else "Forge did not answer; open the Claude app",
    }


@app.post("/api/session/{name}/go")
def go_to_session(name: str):
    """Bring up the terminal tab a session runs in (the Board's "Go to it")."""
    info = _session_info(name)
    if info is None:
        raise HTTPException(404, f"no running session called {name}")
    pid = info["pid"]
    where = terminal_of(pid)
    if not where:
        return _go_to_claude_app(info)
    term = TERMINALS.get(
        where.get("kind", "gnome-terminal-"), TERMINALS["gnome-terminal-"]
    )
    ok = _gdbus(
        "--dest",
        term["dest"],
        "--object-path",
        term["window"],
        "--method",
        "org.gtk.Actions.Activate",
        "active-tab",
        f"[<{where['tab']}>]",
        "{}",
    )
    # Present the window too; GNOME may show "is ready" rather than raise it.
    _gdbus(
        "--dest",
        term["dest"],
        "--object-path",
        term["app"],
        "--method",
        "org.freedesktop.Application.Activate",
        "{}",
    )
    return {"ok": ok, "tab": where["tab"]}


if os.path.isdir(SHARED_DIR):
    app.mount("/shared", StaticFiles(directory=SHARED_DIR), name="shared")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
