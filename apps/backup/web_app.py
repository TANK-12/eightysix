"""Backup: the Forge hub page for the backup drive.

Four pages over the same drive backup.py writes: Code (the offline GitHub on
Vault/git), Snapshots (browse, compare, copy back), Status (what is on the
drive, Back up now, Eject) and Help (README.md and RESTORE.md). The logic is
in browse.py, which imports backup.py; this file is only the HTTP layer.

Every /api route needs `X-Forge: 1` and a Host of 127.0.0.1 or localhost:
the snapshots hold everything on the laptop, so no other page may read them.

    cd ~/Forge/apps/backup && FORGE_SHARED_DIR=~/Forge/shared \\
    .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8468
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import backup
import browse

HERE = Path(__file__).resolve().parent
STATIC_DIR = HERE / "static"
SHARED_DIR = Path(os.environ.get("FORGE_SHARED_DIR", HERE.parent.parent / "shared"))
PORT = 8468

app = FastAPI(title="Backup")


def local_only(request: Request) -> None:
    if request.headers.get("x-forge") != "1":
        raise HTTPException(403, "Send X-Forge: 1")
    ports = {PORT}
    server = request.scope.get("server")
    if server and server[1]:
        ports.add(int(server[1]))
    host = request.headers.get("host", "")
    if host not in {f"{h}:{p}" for h in ("127.0.0.1", "localhost") for p in ports}:
        raise HTTPException(403, "Wrong host")


api = APIRouter(prefix="/api", dependencies=[Depends(local_only)])

ERRORS = {
    browse.NoDrive: (503, "no_drive"),
    browse.NeedsAdmin: (403, "needs_admin"),
    browse.BadInput: (400, "bad_input"),
    browse.NotFound: (404, "not_found"),
    browse.Busy: (409, "busy"),
}


def make_handler(code: int, kind: str):
    async def handler(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse({"detail": str(exc), "kind": kind}, status_code=code)

    return handler


for exc_type, (code, kind) in ERRORS.items():
    app.add_exception_handler(exc_type, make_handler(code, kind))


def cfg() -> dict:
    return backup.load_config()


# ---------------------------------------------------------------- status


@api.get("/status")
def get_status():
    return browse.status(cfg())


@api.get("/progress")
def get_progress():
    return browse.progress(cfg())


class AreaIn(BaseModel):
    area: str


@api.post("/backup")
def post_backup(body: AreaIn):
    return {"unit": browse.start_backup(cfg(), body.area)}


@api.post("/eject")
def post_eject():
    return {"message": browse.eject(cfg())}


@api.get("/help")
def get_help():
    return browse.help_docs()


# ---------------------------------------------------------------- snapshots


@api.get("/snap/sets")
def snap_sets(area: str):
    return {"area": area, "sets": browse.list_sets(cfg(), area)}


@api.get("/snap/list")
def snap_list(area: str, set: str, snap: str, path: str = "", offset: int = 0):
    return browse.list_dir(cfg(), area, set, snap, path, offset)


@api.get("/snap/file")
def snap_file(area: str, set: str, snap: str, path: str):
    return browse.read_file(cfg(), area, set, snap, path)


@api.get("/snap/raw")
def snap_raw(area: str, set: str, snap: str, path: str):
    found = browse.raw_file(cfg(), area, set, snap, path)
    media = browse.IMAGE_TYPES.get(found.suffix.lower(), "application/octet-stream")
    return FileResponse(found, media_type=media)


@api.get("/snap/compare")
def snap_compare(area: str, set: str, snap: str, path: str):
    return browse.compare(cfg(), area, set, snap, path)


class RestoreIn(BaseModel):
    area: str
    set: str
    snap: str
    path: str


@api.post("/snap/restore")
def snap_restore(body: RestoreIn):
    return browse.restore(cfg(), body.area, body.set, body.snap, body.path)


@api.get("/jobs/{job_id}")
def get_job(job_id: str):
    return browse.get_job(job_id)


# ---------------------------------------------------------------- code


@api.get("/repos")
def get_repos():
    return {"repos": browse.repos(cfg())}


@api.get("/repos/{name}/refs")
def repo_refs(name: str):
    return browse.refs(browse.repo_path(cfg(), name))


@api.get("/repos/{name}/log")
def repo_log(name: str, rev: str = "", skip: int = 0, path: str = ""):
    return browse.log(browse.repo_path(cfg(), name), rev or None, skip, path)


@api.get("/repos/{name}/commit/{rev}")
def repo_commit(name: str, rev: str):
    return browse.commit(browse.repo_path(cfg(), name), rev)


@api.get("/repos/{name}/tree")
def repo_tree(name: str, rev: str = "", path: str = ""):
    return browse.tree(browse.repo_path(cfg(), name), rev or None, path)


@api.get("/repos/{name}/blob")
def repo_blob(name: str, path: str, rev: str = ""):
    return browse.blob(browse.repo_path(cfg(), name), rev or None, path)


@api.get("/repos/{name}/raw")
def repo_raw(name: str, path: str, rev: str = ""):
    data, media = browse.blob_raw(browse.repo_path(cfg(), name), rev or None, path)
    return Response(data, media_type=media)


app.include_router(api)

if SHARED_DIR.is_dir():
    app.mount("/shared", StaticFiles(directory=SHARED_DIR), name="shared")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
