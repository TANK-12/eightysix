"""Browser - real web pages inside Forge, with tabs, bookmarks, history and your Firefox data.

This backend keeps the records (bookmarks, history, tabs, preferences), reads
the Firefox profile on request, launches real Firefox, and queues commands from
the Claude panel for the page to carry out. The pages themselves are WebKit
views that forge.py lays over this app's workspace (forge_views.py); the page
in static/ drives them through the hub.

Anything that reads Firefox data, changes records or queues a command requires
the header `X-Forge: 1`. A web page open in the browser cannot send a custom
header to this port without a CORS preflight this app never grants, so it
cannot read your cookies or drive the browser.

Run standalone with:
    FORGE_SHARED_DIR=/home/ejb/Forge/shared \\
    .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8444
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

import agent
import firefox
import store

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
SHARED_DIR = Path(os.environ.get("FORGE_SHARED_DIR", ROOT.parent.parent / "shared"))

app = FastAPI(title="Browser")


@app.middleware("http")
async def revalidate(request, call_next):
    """Ask the hub's WebKit to check back before reusing a file. Without a
    header it guesses, and keeps a script last touched days ago for hours:
    after an update the page ran the old app.js (Relay task 122). The check is
    a cheap 304 when nothing changed."""
    response = await call_next(request)
    response.headers.setdefault("Cache-Control", "no-cache")
    return response


commands = agent.Queue()


def forge_only(x_forge: str | None = Header(default=None)) -> None:
    if x_forge != "1":
        raise HTTPException(403, "Send X-Forge: 1")


guarded = [Depends(forge_only)]


# --- records ------------------------------------------------------------------


@app.get("/api/state")
def state():
    return {
        "prefs": store.prefs(),
        "engines": sorted(store.ENGINES),
        "search": dict(store.ENGINES),
        "bookmarks": store.bookmarks(),
        "session": store.session(),
        "top": store.search_history("", 12),
        "home_dir": str(Path.home()),
    }


@app.get("/api/resolve")
def resolve(text: str):
    return {"url": store.resolve(text, store.prefs()["engine"])}


@app.post("/api/bookmarks", dependencies=guarded)
def add_bookmark(payload: dict):
    url = str(payload.get("url") or "")
    if not store.web(url):
        raise HTTPException(400, "Only web addresses can be bookmarked")
    if not store.keepable(url):
        raise HTTPException(400, "That address is too long to bookmark")
    title, folder = payload.get("title"), payload.get("folder")
    store.add_bookmark(
        url,
        title[:300] if isinstance(title, str) else "",
        folder[:100] if isinstance(folder, str) else "",
    )
    return {"bookmarks": store.bookmarks()}


@app.delete("/api/bookmarks", dependencies=guarded)
def remove_bookmark(url: str):
    store.remove_bookmark(url)
    return {"bookmarks": store.bookmarks()}


@app.get("/api/history", dependencies=guarded)
def history(q: str = "", limit: int = 50):
    rows = store.search_history(q, limit) if q else store.recent(limit)
    return {"history": rows}


@app.delete("/api/history", dependencies=guarded)
def clear_history():
    store.clear_history()
    return {"history": []}


@app.post("/api/visit", dependencies=guarded)
def visit(payload: dict):
    url = str(payload.get("url") or "")
    if store.keepable(url):
        store.record_visit(url, str(payload.get("title", ""))[:300])
    return {"ok": True}


@app.post("/api/session", dependencies=guarded)
def save_session(payload: dict):
    """Only web and local file tabs are kept, as {url, title}; the open tab stays the open one
    (or the nearest kept tab before it). Anything odd is dropped, never a 500."""
    raw = payload.get("tabs")
    active = payload.get("active")
    if not isinstance(active, int) or isinstance(active, bool):
        active = 0
    tabs: list[dict] = []
    at = 0
    for i, t in enumerate(raw if isinstance(raw, list) else []):
        url = t.get("url") if isinstance(t, dict) else None
        if len(tabs) < 100 and store.tab_url(url):
            if i <= active:
                at = len(tabs)
            tabs.append({"url": url, "title": str(t.get("title") or "")[:300]})
    return store.save_session(tabs, at)


@app.post("/api/prefs", dependencies=guarded)
def save_prefs(payload: dict):
    return store.save_prefs(payload)


# --- Firefox ---------------------------------------------------------------------


@app.get("/api/firefox", dependencies=guarded)
def firefox_status():
    profile = firefox.find_profile()
    return {
        "profile": str(profile) if profile else "",
        "installed": bool(shutil.which("firefox")),
    }


@app.post("/api/firefox/import", dependencies=guarded)
def firefox_import(payload: dict):
    """Bookmarks and history into this app's records. Returns counts. Cookies
    are fetched separately by the page, which hands them to forge.py."""
    profile = firefox.find_profile()
    if profile is None:
        raise HTTPException(404, "No Firefox profile found")
    counts = {"bookmarks": 0, "history": 0}
    if payload.get("bookmarks", True):
        for row in firefox.read_bookmarks(profile):
            store.add_bookmark(row["url"], row["title"], row["folder"])
            counts["bookmarks"] += 1
    if payload.get("history", True):
        for row in firefox.read_history(profile):
            store.record_visit(row["url"], row["title"], row["visits"], row["last"])
            counts["history"] += 1
    return counts


@app.get("/api/firefox/cookies", dependencies=guarded)
def firefox_cookies():
    profile = firefox.find_profile()
    if profile is None:
        raise HTTPException(404, "No Firefox profile found")
    return {"cookies": firefox.read_cookies(profile)}


@app.post("/api/open-firefox", dependencies=guarded)
def open_firefox(payload: dict):
    url = payload.get("url")
    if not shutil.which("firefox"):
        raise HTTPException(404, "Firefox is not installed")
    command = ["firefox", "--new-tab", url] if store.web(url) else ["firefox"]
    subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return {"ok": True}


# --- commands from outside (the Claude panel) --------------------------------------


@app.post("/api/agent/do", dependencies=guarded)
def agent_do(payload: dict):
    """Run one browser command and wait for the page's answer, e.g.
    {"op": "open", "url": "https://..."} or {"op": "read"}."""
    try:
        timeout = max(1.0, min(60.0, float(payload.pop("timeout", 20) or 20)))
    except (TypeError, ValueError):
        raise HTTPException(400, "timeout must be a number of seconds")
    return commands.submit(payload, timeout=timeout)


@app.get("/api/agent/next", dependencies=guarded)
def agent_next(wait: float = 25):
    command = commands.next(max(0.0, min(30.0, wait)))
    return command if command else Response(status_code=204)


@app.post("/api/agent/result/{cid}", dependencies=guarded)
def agent_result(cid: str, payload: dict):
    return {"ok": commands.resolve(cid, payload)}


# --- static -----------------------------------------------------------------------

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
