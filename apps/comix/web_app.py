"""Comix - save comix.to series you read, chapter by chapter, as CBZ files.

This backend keeps the series/chapter/page records (comix/store.py), runs the
download worker (comix/downloader.py), borrows the login from the Forge
Browser (comix/session.py) and serves the reader.

Run standalone with:
    FORGE_SHARED_DIR=/home/ejb/Forge/shared \\
    .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8456
"""

from __future__ import annotations

import collections
import json
import os
import shutil
import sys
import threading
import time
import urllib.request
import uuid
import zipfile
import zlib
from contextlib import asynccontextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
SHARED_DIR = Path(os.environ.get("FORGE_SHARED_DIR", ROOT.parent.parent / "shared"))
sys.path.insert(0, str(SHARED_DIR))

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from comix import settings as settings_mod  # noqa: E402
from comix import library, sources  # noqa: E402
from comix.downloader import Worker  # noqa: E402
from comix.session import read_cookies, summary  # noqa: E402
from comix.store import GROUP_MODES, Store  # noqa: E402

BROWSER_AGENT = os.environ.get("COMIX_BROWSER_AGENT", "http://127.0.0.1:8444")

log_lines: collections.deque[str] = collections.deque(maxlen=300)


def log(msg: str) -> None:
    log_lines.append(time.strftime("%H:%M:%S ") + msg)


store = Store()
worker = Worker(store, log)
jobs: dict[str, dict] = {}
# listings share one Chrome profile, so they run one at a time
listing_lock = threading.Lock()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if os.environ.get("COMIX_NO_WORKER") != "1":
        worker.start()
    yield
    worker.stop()


app = FastAPI(title="Comix", lifespan=lifespan)


@app.exception_handler(OverflowError)
def _too_big(request: Request, exc: OverflowError):
    """An id past SQLite's 64-bit range can't name anything: 404, not a 500."""
    return JSONResponse({"detail": "no such item"}, status_code=404)


# --- background jobs (listing a series or the library takes a while) -------------


def run_job(kind: str, fn) -> str:
    jid = uuid.uuid4().hex[:12]
    job = {
        "id": jid,
        "kind": kind,
        "status": "running",
        "log": [],
        "result": None,
        "error": "",
    }
    jobs[jid] = job

    def say(msg: str) -> None:
        job["log"].append(msg)
        log(msg)

    def go() -> None:
        try:
            with listing_lock:
                job["result"] = fn(say)
            job["status"] = "done"
        except Exception as e:
            job["error"] = str(e)
            job["status"] = "error"
            log(f"{kind} failed: {e}")

    threading.Thread(target=go, daemon=True).start()
    return jid


@app.get("/api/jobs/{jid}")
def get_job(jid: str):
    if jid not in jobs:
        raise HTTPException(404, "no such job")
    return jobs[jid]


def _source_for(url: str):
    name = sources.find_for_url(url)
    if name is None:
        raise HTTPException(400, "That link is not from a site Comix knows (comix.to).")
    return name, sources.get(name)


# --- state and settings -----------------------------------------------------------


@app.get("/api/state")
def state():
    conf = settings_mod.load()
    folder = Path(conf["download_dir"]).expanduser()
    probe = folder if folder.exists() else Path.home()
    return {
        "settings": conf,
        "numbers": settings_mod.describe(),
        "counts": store.counts(),
        "current": list(worker.current.values()),
        "paused": worker.paused.is_set(),
        "free_gb": round(shutil.disk_usage(probe).free / 1e9, 1),
        "login": {
            s["name"]: summary(sources.get(s["name"]).DOMAIN)
            for s in sources.all_sources()
        },
        "sources": sources.all_sources(),
        "log": list(log_lines)[-60:],
    }


class SettingsIn(BaseModel):
    values: dict


@app.post("/api/settings")
def save_settings(body: SettingsIn):
    try:
        return settings_mod.save(body.values)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


# --- login ----------------------------------------------------------------------------


class UrlIn(BaseModel):
    url: str


@app.post("/api/login/open")
def login_open(body: UrlIn):
    """Ask the Forge Browser to open the site so Emerson can log in there.

    The page also asks the hub to switch to the Browser. The command waits in
    the Browser's queue until its page picks it up, so send it off-thread.
    """

    def send() -> None:
        req = urllib.request.Request(
            BROWSER_AGENT + "/api/agent/do",
            data=json.dumps({"op": "open", "url": body.url}).encode(),
            headers={"Content-Type": "application/json", "X-Forge": "1"},
        )
        try:
            urllib.request.urlopen(req, timeout=30).read()
        except Exception as e:
            log(f"could not reach the Forge Browser: {e}")

    threading.Thread(target=send, daemon=True).start()
    return {"ok": True}


# --- series ----------------------------------------------------------------------------


@app.post("/api/lookup")
def lookup(body: UrlIn):
    """List every chapter and scan group of a series (a job; poll /api/jobs)."""
    name, src = _source_for(body.url)

    def go(say):
        info = src.list_series(body.url, read_cookies(src.DOMAIN), say)
        counts = collections.Counter(r["group"] for r in info["rows"])
        info["group_counts"] = [
            {"group": g, "chapters": n} for g, n in counts.most_common()
        ]
        info["numbers"] = len({r["number"] for r in info["rows"]})
        info["url"] = body.url.split("?")[0]
        info["source"] = name
        say(f"{info['title']}: {info['numbers']} chapters, {len(counts)} group(s)")
        return info

    return {"job": run_job("lookup", go)}


class AddIn(BaseModel):
    job: str
    mode: str
    groups: list[str] = []


@app.post("/api/series")
def add_series(body: AddIn):
    job = jobs.get(body.job)
    if not job or job["status"] != "done" or job["kind"] != "lookup":
        raise HTTPException(400, "Look the series up first.")
    if body.mode not in GROUP_MODES:
        raise HTTPException(400, f"mode must be one of {GROUP_MODES}")
    info = job["result"]
    sid = store.save_series(
        info["url"], info["title"], info["source"], info["rows"], body.mode, body.groups
    )
    return store.series(sid)[0]


@app.get("/api/series")
def list_series():
    return store.series()


@app.get("/api/series/{sid}")
def series_detail(sid: int):
    rows = store.series(sid)
    if not rows:
        raise HTTPException(404, "no such series")
    chapters = store.chapters(sid)
    counts = collections.Counter(c["grp"] for c in chapters)
    return {
        **rows[0],
        "chapters": chapters,
        "group_counts": [{"group": g, "chapters": n} for g, n in counts.most_common()],
    }


class ChoiceIn(BaseModel):
    mode: str
    groups: list[str] = []


@app.post("/api/series/{sid}/choice")
def series_choice(sid: int, body: ChoiceIn):
    if body.mode not in GROUP_MODES:
        raise HTTPException(400, f"mode must be one of {GROUP_MODES}")
    if not store.series(sid):
        raise HTTPException(404, "no such series")
    return {"queued": store.apply_choice(sid, body.mode, body.groups)}


@app.post("/api/series/{sid}/refresh")
def series_refresh(sid: int):
    rows = store.series(sid)
    if not rows:
        raise HTTPException(404, "no such series")
    s = rows[0]
    src = sources.get(s["source"])

    def go(say):
        info = src.list_series(s["url"], read_cookies(src.DOMAIN), say)
        before = s["listed"]
        store.save_series(
            s["url"],
            info["title"],
            s["source"],
            info["rows"],
            s["group_mode"],
            s["groups"],
        )
        after = store.series(sid)[0]["listed"]
        say(f"{info['title']}: {after - before} new chapter row(s)")
        return {"new": after - before}

    return {"job": run_job("refresh", go)}


@app.delete("/api/series/{sid}")
def series_delete(sid: int):
    """Forget the series here. Downloaded CBZ files stay on disk."""
    store.delete_series(sid)
    return {"ok": True}


class WantIn(BaseModel):
    wanted: bool


@app.post("/api/chapters/{cid}/want")
def chapter_want(cid: int, body: WantIn):
    if not store.chapter(cid):
        raise HTTPException(404, "no such chapter")
    store.set_wanted(cid, body.wanted)
    return store.chapter(cid)


# --- library ------------------------------------------------------------------------


@app.post("/api/library/sync")
def library_sync():
    """Add every series on Emerson's library page (see comix.library.sync)."""
    page = settings_mod.load()["library_url"]
    if not page:
        raise HTTPException(
            400, "Paste your comix.to library or bookmarks page link in Settings first."
        )
    name, src = _source_for(page)

    def go(say):
        cookies = read_cookies(src.DOMAIN)
        if not cookies:
            say("no comix.to login found: log in through the Forge Browser first")
        return library.sync(store, src, name, page, cookies, say)

    return {"job": run_job("library", go)}


# --- queue ----------------------------------------------------------------------------


@app.get("/api/queue")
def queue():
    return store.queue()


class PauseIn(BaseModel):
    paused: bool


@app.post("/api/queue/pause")
def queue_pause(body: PauseIn):
    (worker.paused.set if body.paused else worker.paused.clear)()
    return {"paused": worker.paused.is_set()}


@app.post("/api/queue/retry")
def queue_retry():
    return {"requeued": store.retry_failed()}


# --- reader ---------------------------------------------------------------------------


def _cbz(cid: int) -> Path:
    ch = store.chapter(cid)
    if not ch or ch["state"] != "done" or not Path(ch["cbz"]).exists():
        raise HTTPException(404, "that chapter is not downloaded")
    return Path(ch["cbz"])


def _open_cbz(cid: int) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(_cbz(cid))
    except (zipfile.BadZipFile, OSError):
        raise HTTPException(404, "that chapter's file can't be read") from None


def _images(z: zipfile.ZipFile) -> list[str]:
    return sorted(
        n
        for n in z.namelist()
        if n.lower().rsplit(".", 1)[-1] in ("png", "jpg", "jpeg", "webp", "gif")
    )


@app.get("/api/read/{cid}")
def read_chapter(cid: int):
    ch = store.chapter(cid)
    with _open_cbz(cid) as z:
        pages = len(_images(z))
    done = (
        [c for c in store.chapters(ch["series_id"]) if c["state"] == "done"]
        if ch
        else []
    )
    ids = [c["id"] for c in done]
    at = ids.index(cid)
    return {
        "chapter": ch,
        "pages": pages,
        "prev": ids[at - 1] if at > 0 else None,
        "next": ids[at + 1] if at + 1 < len(ids) else None,
    }


@app.get("/api/read/{cid}/{n}")
def read_page(cid: int, n: int):
    with _open_cbz(cid) as z:
        names = _images(z)
        if not 1 <= n <= len(names):
            raise HTTPException(404, "no such page")
        try:
            data = z.read(names[n - 1])
        except (zipfile.BadZipFile, OSError, zlib.error):
            raise HTTPException(404, "that page can't be read") from None
    ext = names[n - 1].rsplit(".", 1)[-1].lower()
    kind = {"jpg": "jpeg"}.get(ext, ext)
    return Response(
        data, media_type=f"image/{kind}", headers={"Cache-Control": "max-age=86400"}
    )


# --- static -----------------------------------------------------------------------------

app.mount("/shared", StaticFiles(directory=SHARED_DIR), name="shared")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")
