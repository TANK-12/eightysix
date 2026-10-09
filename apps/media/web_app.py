"""Media -- play your music and videos, YouTube and Crunchyroll inside Forge,
download music with yt-dlp.

Run standalone with:
    FORGE_SHARED_DIR=/home/ejb/Forge/shared \\
    .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8450

The page does the playing (an HTML video element over /api/file, which
serves byte ranges so seeking works). The backend scans folders, keeps the
settings, serves files, and runs yt-dlp as jobs whose log streams to the
page over server-sent events, the same job shape MediaForge uses.
"""

from __future__ import annotations

import asyncio
import json
import os
import queue
import shutil
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

import media_lib as lib

ROOT = Path(__file__).resolve().parent
SHARED_DIR = Path(os.environ.get("FORGE_SHARED_DIR", ROOT.parent.parent / "shared"))

app = FastAPI(title="Forge Media")


@app.exception_handler(RequestValidationError)
async def _readable_validation_error(request: Request, exc: RequestValidationError):
    """A 422 whose detail is one line ("min_mb: Input should be a valid
    number"), so the page's toast can show it as is."""
    parts = []
    for e in exc.errors():
        where = [str(x) for x in e.get("loc", ()) if x not in ("body", "query", "path")]
        parts.append((where[-1] + ": " if where else "") + str(e.get("msg", "")))
    return JSONResponse(status_code=422, content={"detail": "; ".join(parts)})


# --------------------------------------------------------------------------
# jobs


class Job:
    def __init__(self, kind: str):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.status = "running"
        self.error: Optional[str] = None
        self.result: Optional[dict] = None
        self.events: queue.Queue = queue.Queue()
        self.stop_requested = threading.Event()
        self.proc: Optional[subprocess.Popen] = None

    def log(self, text: str) -> None:
        self.events.put({"type": "log", "text": text})

    def progress(self, frac: float) -> None:
        self.events.put({"type": "progress", "frac": max(0.0, min(1.0, frac))})

    def finish(self, status: str, error: Optional[str] = None) -> None:
        self.status, self.error = status, error
        self.events.put({"type": status, "error": error})

    def stop(self) -> None:
        self.stop_requested.set()
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()


JOBS: dict[str, Job] = {}


def _start(job: Job, work) -> dict:
    def run():
        try:
            work(job)
            job.finish("done")
        except Exception as e:  # the page shows the message
            job.finish("error", str(e))

    JOBS[job.id] = job
    finished = [j for j in JOBS.values() if j.status != "running"]
    for old in finished[:-20]:
        JOBS.pop(old.id, None)
    threading.Thread(target=run, daemon=True).start()
    return {"job_id": job.id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    return {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "error": job.error,
        "result": job.result,
    }


@app.post("/api/jobs/{job_id}/stop")
def stop_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    job.stop()
    return {"ok": True}


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")

    async def gen():
        while True:
            try:
                e = job.events.get_nowait()
            except queue.Empty:
                if job.status != "running" and job.events.empty():
                    yield f"data: {json.dumps({'type': job.status, 'error': job.error})}\n\n"
                    return
                await asyncio.sleep(0.15)
                continue
            yield f"data: {json.dumps(e)}\n\n"
            if e["type"] in ("done", "error"):
                return

    return StreamingResponse(gen(), media_type="text/event-stream")


# --------------------------------------------------------------------------
# settings and library


class Settings(BaseModel):
    folders: Optional[list[str]] = Field(None, max_length=500)
    # a folder name is a path: long ones exist, but not megabytes, and a NUL
    # byte makes every later scan and file lookup fail
    download_folder: Optional[str] = Field(
        None, min_length=1, max_length=4096, pattern=r"^[^\x00]*$"
    )
    volume: Optional[int] = Field(None, ge=0, le=100)
    advanced_mode: Optional[bool] = None

    @field_validator("folders")
    @classmethod
    def _folders_are_paths(cls, v):
        if v is not None:
            for f in v:
                if len(f) > 4096 or "\x00" in f:
                    raise ValueError("a folder name is too long or holds a NUL byte")
        return v

    @field_validator("download_folder")
    @classmethod
    def _download_folder_not_blank(cls, v):
        if v is not None and not v.strip():
            raise ValueError("the download folder cannot be empty")
        return v


@app.get("/api/settings")
def get_settings():
    s = lib.load_settings()
    return {
        **s,
        "ytdlp": bool(lib.ytdlp()),
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "firefox": bool(shutil.which("firefox")),
    }


@app.post("/api/settings")
def set_settings(req: Settings):
    changes = {k: v for k, v in req.model_dump().items() if v is not None}
    return lib.save_settings(changes)


def _all_folders() -> list[str]:
    s = lib.load_settings()
    return list(s["folders"]) + [s["download_folder"]]


@app.get("/api/library")
def library():
    return {"files": lib.scan(_all_folders())}


@app.get("/api/file")
def file(path: str):
    target = lib.inside(path, _all_folders())
    if target is None:
        raise HTTPException(404, "not in a library folder")
    return FileResponse(str(target))


# --------------------------------------------------------------------------
# YouTube: listing and downloading with yt-dlp


class ListRequest(BaseModel):
    text: str = Field(max_length=2000)
    limit: int = Field(60, ge=1, le=500)


@app.post("/api/yt/list")
def yt_list(req: ListRequest):
    if not lib.ytdlp():
        raise HTTPException(409, "yt-dlp is not installed (pacman -S yt-dlp)")
    try:
        target = lib.list_target(req.text, req.limit)
    except ValueError as e:
        raise HTTPException(400, str(e))

    def work(job: Job):
        job.log(f"asking YouTube about {target} ...")
        job.proc = subprocess.Popen(
            lib.list_command(target, req.limit),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        out, err = job.proc.communicate()
        if job.proc.returncode != 0:
            lines = err.strip().splitlines()
            raise RuntimeError(lines[-1] if lines else "yt-dlp failed")
        listing = lib.parse_listing(out)
        listing["target"] = target
        job.log(f"{len(listing['entries'])} item(s)")
        job.result = listing

    return _start(Job("yt-list"), work)


class DownloadRequest(BaseModel):
    urls: list[str] = Field(max_length=500)
    kind: Literal["audio", "video"] = "audio"  # audio -> mp3, video -> mp4
    folder: Optional[str] = Field(None, max_length=4096, pattern=r"^[^\x00]*$")


@app.post("/api/yt/download")
def yt_download(req: DownloadRequest):
    if not lib.ytdlp():
        raise HTTPException(409, "yt-dlp is not installed (pacman -S yt-dlp)")
    if req.kind == "audio" and not shutil.which("ffmpeg"):
        raise HTTPException(409, "ffmpeg is needed to make mp3s")
    urls = [
        u for u in req.urls if u.startswith(("http://", "https://")) and len(u) <= 4096
    ]
    if not urls:
        raise HTTPException(400, "nothing to download")
    folder = lib.expand(req.folder or lib.load_settings()["download_folder"])

    def work(job: Job):
        folder.mkdir(parents=True, exist_ok=True)
        job.log(
            f"{len(urls)} item(s) -> {folder} as {'mp3' if req.kind != 'video' else 'mp4'}"
        )
        # one yt-dlp per video, so a failure or a stop only loses that one and
        # the progress bar means "videos done" rather than "bytes of this file"
        done = failed = 0
        for i, url in enumerate(urls):
            if job.stop_requested.is_set():
                job.log("stopped")
                break
            job.proc = subprocess.Popen(
                lib.download_command([url], folder, req.kind),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            assert job.proc.stdout is not None
            last = ""
            for line in job.proc.stdout:
                line = line.rstrip()
                if not line:
                    continue
                frac = lib.progress_of(line)
                if frac is not None:
                    job.progress((i + frac) / len(urls))
                    continue  # the percentage lines are noise in a log
                last = line
                job.log(line)
            code = job.proc.wait()
            if code == 0:
                done += 1
            else:
                failed += 1
                job.log(f"failed ({code}): {last}")
            job.progress((i + 1) / len(urls))
        job.log(f"finished: {done} saved, {failed} failed")
        job.result = {"done": done, "failed": failed, "folder": str(folder)}

    return _start(Job("yt-download"), work)


# --------------------------------------------------------------------------
# hand-offs


class OpenRequest(BaseModel):
    url: str = Field(max_length=8192)


@app.post("/api/open-firefox")
def open_firefox(req: OpenRequest):
    """Crunchyroll's player needs Widevine, which WebKitGTK does not have;
    Firefox has it and the login. Same for anything else that will not play."""
    if not req.url.startswith(("http://", "https://")):
        raise HTTPException(400, "not a web address")
    exe = shutil.which("firefox")
    if not exe:
        raise HTTPException(409, "Firefox is not installed")
    subprocess.Popen(
        [exe, req.url],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return {"ok": True}


if SHARED_DIR.is_dir():
    app.mount("/shared", StaticFiles(directory=str(SHARED_DIR)), name="shared")
app.mount("/", StaticFiles(directory=str(ROOT / "static"), html=True), name="static")
