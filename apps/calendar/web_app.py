"""Calendar: a life log of what happened on this laptop, fed by Emerson, Claude
Code, Jan, Nyarch, apps opening and closing, and any script.

Store: store.py (SQLite). Feeders: sources/ (one file each). Background runs
and reminders: collector.py. Scripts log with `POST /api/events` or the
`forge-log` command next to this file.

Every /api route needs the header `X-Forge: 1`, as in the other Forge apps.

Run standalone with:
    FORGE_SHARED_DIR=/home/ejb/Forge/shared \\
    .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8453
"""

from __future__ import annotations

import os
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from collector import Collector
from store import KINDS, EventError, Store

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
SHARED_DIR = Path(os.environ.get("FORGE_SHARED_DIR", ROOT.parent.parent / "shared"))
DATA_DIR = Path(
    os.environ.get("FORGE_CALENDAR_DATA") or Path.home() / ".local/share/forge/calendar"
)
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

import forge_jan  # noqa: E402  (shared: this app's own Jan model settings)

store = Store(DATA_DIR / "events.db")
collector = Collector(store, DATA_DIR)
jan = forge_jan.AppJan("calendar", roles=("summary",))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if os.environ.get("FORGE_CALENDAR_NO_COLLECT") != "1":
        collector.start()
    yield
    collector.stop()
    jan.stop()


def forge_only(x_forge: str | None = Header(default=None)) -> None:
    if x_forge != "1":
        raise HTTPException(403, "Send X-Forge: 1")


app = FastAPI(title="Calendar", lifespan=lifespan)
guarded = [Depends(forge_only)]


def listed(value: str) -> list[str]:
    return [v for v in (value or "").split(",") if v]


@app.get("/api/events", dependencies=guarded)
def events(
    start: float | None = None,
    end: float | None = None,
    sources: str = "",
    kinds: str = "",
    q: str = "",
    limit: int = 2000,
):
    found = store.query(start, end, listed(sources), listed(kinds), q.strip(), limit)
    return {"events": found, "truncated": len(found) >= limit}


@app.post("/api/events", dependencies=guarded)
def add_event(payload: dict):
    """Log one event. Scripts send source "script:<name>"; the page sends
    "emerson". A repeated key is ignored and reported as a duplicate."""
    try:
        added = store.add(payload)
    except EventError as e:
        raise HTTPException(400, str(e))
    return {"event": added, "duplicate": added is None}


@app.patch("/api/events/{event_id}", dependencies=guarded)
def edit_event(event_id: int, payload: dict):
    try:
        updated = store.update(event_id, payload)
    except EventError as e:
        raise HTTPException(400, str(e))
    if updated is None:
        raise HTTPException(404, "No such event")
    return {"event": updated}


@app.delete("/api/events/{event_id}", dependencies=guarded)
def delete_event(event_id: int):
    if not store.delete(event_id):
        raise HTTPException(404, "No such event")
    return {"ok": True}


@app.get("/api/days", dependencies=guarded)
def days(start: float, end: float, offset: float = 0):
    """Counts per day and source, for the month view's dots. offset is the
    viewer's UTC offset in seconds."""
    return {"days": store.day_counts(start, end, offset)}


@app.get("/api/feeders", dependencies=guarded)
def feeders():
    s = collector.settings()
    return {"feeders": collector.describe(), "settings": s, "kinds": KINDS}


@app.post("/api/feeders/settings", dependencies=guarded)
def feeder_settings(payload: dict):
    try:
        s = collector.save_settings(payload)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"feeders": collector.describe(), "settings": s}


@app.post("/api/feeders/{name}/run", dependencies=guarded)
def run_feeder(name: str):
    if name not in collector.feeders:
        raise HTTPException(404, "No such feeder")
    return {"added": collector.run_feeder(name), "feeders": collector.describe()}


@app.post("/api/summary", dependencies=guarded)
def summary(payload: dict):
    """What happened on a day, summed up by this app's own Jan model. It loads
    on demand and is released when idle (forge_jan)."""
    try:
        start = float(payload["start"])
        end = float(payload.get("end") or start + 86400)
    except (KeyError, TypeError, ValueError):
        raise HTTPException(400, "Send the day's start time")
    day = store.query(start, end, limit=400)
    if not day:
        return {"summary": "Nothing was logged that day."}
    lines = [
        f"{datetime.fromtimestamp(e['ts']).strftime('%H:%M')} [{e['source']}] {e['title']}"
        for e in day
    ]
    text = "\n".join(lines)[-12000:]
    model = jan.model_for("summary")
    if not model:
        raise HTTPException(503, "Jan has no models listed")
    system = (
        "You summarise one day of a person's activity log for them. Write 4 to 8 short "
        "bullet points in plain words: what they worked on, what they asked for, which apps "
        "they used and roughly when. Do not invent anything that is not in the log."
    )
    try:
        with jan.using(model):
            reply = forge_jan.chat(model, system, text, temperature=0.3, max_tokens=500)
    except forge_jan.JanError as e:
        raise HTTPException(502, f"Jan: {e}")
    return {"summary": reply.strip(), "events": len(day)}


@app.get("/api/health")
def health():
    return {"ok": True, "time": time.time()}


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
