"""Voice: the one Forge process that loads speech models (STT and TTS).

Other apps call it over HTTP (shared/forge_voice.py, shared/forge_voice.js);
the hotkey drives push-to-talk through /api/ptt/*. Every route except
GET /, GET /api/status and static files needs the header `X-Forge: 1` and a
Host of 127.0.0.1:<port> or localhost:<port>; CORS allows only local origins.

    cd ~/Forge/apps/voice && \\
    FORGE_SHARED_DIR=/home/ejb/Forge/shared \\
    .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8467
"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

import service
from service import BadInput, VoiceError

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
PORT = int(os.environ.get("FORGE_VOICE_PORT", "8467"))


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    voice.models.unload()  # stops engine servers (breeze-server) with the app


app = FastAPI(title="Voice", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(127\.0\.0\.1|localhost)(:\d+)?",
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["X-Forge", "Content-Type"],
    expose_headers=[
        "X-Voice-Model",
        "X-Voice-Seconds",
        "X-Voice-Voice",
        "X-Voice-Fell-Back",
    ],
)
voice = service.Voice()


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


guarded = [Depends(local_only)]


@app.exception_handler(BadInput)
def _bad(_req, e: BadInput):
    return JSONResponse({"detail": str(e)}, status_code=400)


@app.exception_handler(VoiceError)
def _fail(_req, e: VoiceError):
    return JSONResponse({"detail": str(e)}, status_code=503)


@app.get("/api/status")
def status():
    return voice.status()


@app.get("/api/registry", dependencies=guarded)
def registry():
    reg = service.load_registry()
    keep = (
        "id",
        "kind",
        "label",
        "tier",
        "engine",
        "size_mb",
        "voices",
        "default_voice",
    )
    models = []
    for row in reg["models"]:
        m = {k: row.get(k) for k in keep}
        m["voices"] = service.row_voices(row)
        m["expressive"] = bool(row.get("expressive"))
        m["present"] = service.model_present(row)
        models.append(m)
    home = service.models_home()
    free = shutil.disk_usage(home if home.exists() else Path.home()).free
    return {
        "models": models,
        "defaults": reg["defaults"],
        "disk_free_gb": round(free / 1e9, 1),
        "source": str(service.registry_path()),
    }


@app.get("/api/settings", dependencies=guarded)
def get_settings():
    return voice.settings()


@app.post("/api/settings", dependencies=guarded)
async def post_settings(request: Request):
    try:
        patch = await request.json()
    except ValueError:
        raise BadInput("send a JSON object")
    return service.save_settings(patch, service.load_registry())


@app.get("/api/apps", dependencies=guarded)
def apps():
    return {"apps": service.discover_apps(voice.settings(), service.load_registry())}


@app.post("/api/stt", dependencies=guarded)
async def stt(request: Request, app: str | None = None, model: str | None = None):
    body = b""
    async for part in request.stream():
        body += part
        if len(body) > service.MAX_BYTES:
            raise BadInput("audio is over 20 MB")
    audio = service.decode(body)
    return await run_in_threadpool(voice.transcribe, audio, app, model)


async def _json(request: Request) -> dict:
    try:
        d = await request.json()
    except ValueError:
        raise BadInput("send a JSON object")
    if not isinstance(d, dict) or not isinstance(d.get("text"), str):
        raise BadInput("text is required")
    return d


def header_text(s, limit: int = 200) -> str:
    """One header-safe line: control characters (a newline in a header value
    makes the server drop the connection) become spaces, non-ASCII becomes
    '?', and it is cut to `limit` characters."""
    s = " ".join(re.sub(r"[\x00-\x1f\x7f]", " ", str(s)).split())
    return s.encode("ascii", "replace").decode()[:limit]


def _tts_args(d: dict) -> dict:
    speed = d.get("speed")
    if speed is not None:
        service._num(speed, 0.5, 2.0, "speed")
    return {k: d.get(k) for k in ("app", "model", "voice", "speed")}


@app.post("/api/tts", dependencies=guarded)
async def tts(request: Request):
    d = await _json(request)
    r = await run_in_threadpool(voice.synthesize, d["text"], **_tts_args(d))
    headers = {
        "X-Voice-Model": header_text(r["model"]),
        "X-Voice-Voice": header_text(r["voice"]),
        "X-Voice-Seconds": str(r["seconds"]),
    }
    if r.get("fell_back"):  # a heavy model could not run; the default spoke
        headers["X-Voice-Fell-Back"] = header_text(r["fell_back"])
    return Response(r["wav"], media_type="audio/wav", headers=headers)


@app.post("/api/say", dependencies=guarded)
async def say(request: Request):
    d = await _json(request)
    r = await run_in_threadpool(voice.say_report, d["text"], **_tts_args(d))
    return dict(r, ok=True)


@app.post("/api/hush", dependencies=guarded)
def hush():
    return {"ok": True, "state": voice.hush()}


@app.post("/api/ptt/{event}", dependencies=guarded)
def ptt(event: str, target: str = "auto"):
    if event not in ("down", "up", "tap", "cancel"):
        raise HTTPException(404, "unknown push-to-talk event")
    if target not in service.TARGETS:
        raise BadInput(f"target must be one of {', '.join(service.TARGETS)}")
    return {"state": voice.press(event, target)}


@app.get("/api/history", dependencies=guarded)
def history():
    return {"history": list(voice.history)}


@app.post("/api/unload", dependencies=guarded)
def unload():
    return {"unloaded": voice.models.unload()}


if service.SHARED_DIR.is_dir():
    app.mount("/shared", StaticFiles(directory=service.SHARED_DIR), name="shared")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
