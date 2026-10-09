"""Crew Room -- Claude sessions, crew helpers and Jan models as a pixel room.

Everything it shows is read locally and read-only: ~/.claude session files and
transcripts, crew boards, agent definitions and /proc. The data sources are
discovered from sources/; rooms and sprites live in ~/ForgeArtData. The one
thing that writes is launching (launch.py): a terminal session or a background
task, only from this app's own page.
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(ROOT, "static")
SHARED_DIR = os.environ.get("FORGE_SHARED_DIR") or os.path.join(
    ROOT, "..", "..", "shared"
)
for path in (ROOT, SHARED_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from fastapi import Depends, FastAPI, HTTPException, Request  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

import art  # noqa: E402
import forge_attach  # noqa: E402
import forge_attach_api  # noqa: E402
import conversation  # noqa: E402
import launch  # noqa: E402
import sources  # noqa: E402
import where  # noqa: E402
from context import Context  # noqa: E402
from sources import sessions as session_source  # noqa: E402


@asynccontextmanager
async def lifespan(_app: FastAPI):
    art.ensure_seeded()
    yield


app = FastAPI(title="Crew Room", lifespan=lifespan)


@app.get("/api/room")
def room():
    data = sources.collect_all(Context.from_env())
    for session in data.get("sessions") or []:
        session.pop("transcript", None)
    return data


@app.get("/api/rooms")
def rooms():
    return {"rooms": art.list_rooms()}


@app.get("/api/rooms/{room_id}")
def room_layout(room_id: str):
    try:
        return art.load_room(room_id)
    except (OSError, ValueError) as exc:
        raise HTTPException(404, f"no room {room_id}: {exc}")


@app.get("/api/art/library")
def art_library():
    return art.library()


def _session_id(session_id: str) -> str:
    if not launch.SESSION_ID.match(session_id):
        raise HTTPException(400, "That is not a session id")
    return session_id


@app.get("/api/sessions/{session_id}/conversation")
def session_conversation(session_id: str, before: int | None = None):
    path = session_source.find_transcript(Context.from_env(), _session_id(session_id))
    if not path:
        raise HTTPException(404, "No transcript for that session")
    return conversation.page(path, before)


@app.get("/api/sessions/{session_id}/where")
def session_where(session_id: str):
    info = where.describe(Context.from_env(), _session_id(session_id))
    if info is None:
        raise HTTPException(404, "Nothing is known about that session")
    return info


# --- launching: the only endpoints that start anything --------------------------


class TerminalRequest(BaseModel):
    folder: str


class TaskRequest(BaseModel):
    prompt: str
    folder: str
    model: str = ""
    files: list[str] = []


def _same_site(request: Request) -> None:
    """A web page elsewhere could post to this port; browsers always send
    Origin on such a post, so refuse any that is not this app."""
    origin = request.headers.get("origin")
    if origin and urlparse(origin).netloc != request.headers.get("host"):
        raise HTTPException(403, "Only the Crew Room page can do that")


# Files and pictures for a background task (Relay task 118): saved in Crew
# Room's data folder and named in the prompt as "Attached files:" lines.
ATTACH = forge_attach_api.Attachments(
    lambda: launch.data_dir() / "attachments", what="task"
)
app.include_router(ATTACH.router(dependencies=[Depends(_same_site)]))


@app.get("/api/launch/options")
def launch_options():
    return launch.options(Context.from_env())


@app.post("/api/launch/terminal")
def launch_terminal(body: TerminalRequest, request: Request):
    _same_site(request)
    try:
        return launch.open_terminal(body.folder)
    except launch.LaunchError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/launch/task")
def launch_task(body: TaskRequest, request: Request):
    _same_site(request)
    try:
        prompt = forge_attach.with_note(body.prompt, ATTACH.paths(body.files))
        return launch.start_task(prompt, body.folder, body.model)
    except launch.LaunchError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/tasks")
def tasks():
    return {"tasks": launch.list_tasks(Context.from_env().proc_dir)}


if os.path.isdir(SHARED_DIR):
    app.mount("/shared", StaticFiles(directory=SHARED_DIR), name="shared")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
