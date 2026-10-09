"""Files - a file manager inside Forge.

A thin FastAPI layer over `fsops.py`, which holds every rule (path guard,
trash-only removal, copy/move jobs, thumbnails). The page is `static/`.

Every /api route needs either the header `X-Forge: 1` or `?t=<token>`. A web
page open in the Forge Browser can reach 127.0.0.1, but it cannot send that
header cross-origin without a CORS preflight this app never grants, and it
cannot read the token. The token form exists only for `<img>`/`<video>` src
URLs, which cannot carry headers.

Run standalone with:
    .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8458
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import fsops

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
SHARED_DIR = Path(os.environ.get("FORGE_SHARED_DIR", ROOT.parent.parent / "shared"))
TOKEN = secrets.token_urlsafe(24)


def forge_only(
    x_forge: str | None = Header(default=None), t: str | None = Query(default=None)
) -> None:
    if x_forge != "1" and not (t and secrets.compare_digest(t, TOKEN)):
        raise HTTPException(403, "Send X-Forge: 1")


app = FastAPI(title="Forge Files")


@app.exception_handler(fsops.FsError)
async def fs_error(_req: Request, exc: fsops.FsError) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=400)


guard = [Depends(forge_only)]


@app.get("/api/session", dependencies=guard)
def session() -> dict:
    return {"token": TOKEN, "home": str(fsops.HOME), **fsops.places()}


@app.get("/api/list", dependencies=guard)
def list_dir(path: str, hidden: bool = False) -> dict:
    out = fsops.list_dir(path, hidden)
    try:
        out.update(fsops.folder_info(out["path"]))
    except OSError:
        pass
    return out


@app.get("/api/search", dependencies=guard)
def search(path: str, q: str, hidden: bool = False) -> dict:
    return fsops.search(path, q, hidden)


@app.get("/api/text", dependencies=guard)
def text(path: str) -> dict:
    return fsops.read_text(path)


@app.get("/api/raw", dependencies=guard)
def raw(path: str) -> FileResponse:
    p = fsops.resolve(path)
    if not p.is_file():
        raise HTTPException(404, "Not a file")
    # Starlette answers Range requests, so audio and video seek.
    return FileResponse(p)


@app.get("/api/thumb", dependencies=guard)
def thumb(path: str) -> FileResponse:
    p = fsops.thumbnail(path)
    if p is None:
        raise HTTPException(404, "No thumbnail")
    return FileResponse(p, headers={"Cache-Control": "private, max-age=3600"})


@app.post("/api/mkdir", dependencies=guard)
def mkdir(parent: str = Body(...), name: str = Body(...)) -> dict:
    return {"path": fsops.make_folder(parent, name)}


@app.post("/api/rename", dependencies=guard)
def rename(path: str = Body(...), name: str = Body(...)) -> dict:
    return {"path": fsops.rename(path, name)}


@app.post("/api/trash", dependencies=guard)
def trash(paths: list[str] = Body(..., embed=True)) -> dict:
    return fsops.trash(paths)


@app.post("/api/restore", dependencies=guard)
def restore(paths: list[str] = Body(..., embed=True)) -> dict:
    return fsops.restore(paths)


@app.post("/api/archive", dependencies=guard)
def archive(op: str = Body(...), paths: list[str] = Body(...)) -> dict:
    return fsops.start_archive(op, paths).public()


@app.post("/api/open", dependencies=guard)
def open_default(path: str = Body(..., embed=True)) -> dict:
    fsops.open_default(path)
    return {"ok": True}


@app.post("/api/transfer", dependencies=guard)
def transfer(
    op: str = Body(...), paths: list[str] = Body(...), dest: str = Body(...)
) -> dict:
    return fsops.start_transfer(op, paths, dest).public()


@app.get("/api/jobs/{job_id}", dependencies=guard)
def job(job_id: str) -> dict:
    j = fsops.JOBS.get(job_id)
    if j is None:
        raise HTTPException(404, "No such job")
    return j.public()


if SHARED_DIR.is_dir():
    app.mount("/shared", StaticFiles(directory=str(SHARED_DIR)), name="shared")
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
