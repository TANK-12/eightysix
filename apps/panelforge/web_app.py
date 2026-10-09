"""PanelForge: manga and webtoon chapters into voiced, animated movies.

This file only wires things together. The areas are separate modules listed
in panelforge/api_registry.py; see CONTRACTS.md for the data formats they
share and HANDOFF.md for status.
"""

import errno
import importlib
import json
import math
import os
import sys

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(ROOT, "static")
SHARED_DIR = os.environ.get("FORGE_SHARED_DIR") or os.path.join(
    ROOT, "..", "..", "shared"
)
sys.path.insert(0, os.path.abspath(SHARED_DIR))

from panelforge import jobs, paths  # noqa: E402
import forge_jan  # noqa: E402  (shared; each app has its own Jan model settings)
from panelforge.api_registry import API_MODULES  # noqa: E402


def _refuse(token: str):
    raise ValueError(token)


def _finite(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ValueError(text)
    return value


async def _finite_json(request: Request) -> None:
    """Refuse NaN, Infinity and 1e999 anywhere in a JSON body with a 422.
    Python's JSON reader takes them, Pydantic lets them through a plain dict,
    and once stored the document can no longer be sent back (a 500 on every
    later read)."""
    if "json" not in request.headers.get("content-type", ""):
        return
    body = await request.body()
    if not body:
        return
    try:
        json.loads(body, parse_constant=_refuse, parse_float=_finite)
    except json.JSONDecodeError:
        return  # malformed JSON is FastAPI's own 422, or ignored by the route
    except ValueError:
        raise HTTPException(422, "numbers must be finite (no NaN or Infinity)")


app = FastAPI(title="PanelForge", dependencies=[Depends(_finite_json)])
# PanelForge's own Jan model settings (GET/POST /api/jan/settings): role
# "script" reads the page for speakers, expressions and OCR fixes. Loaded on
# the first request, released when idle, never restarted.
jan = forge_jan.mount(app, "panelforge", roles=("script",))
paths.ensure_roots()


@app.exception_handler(RequestValidationError)
def _bad_request(_request: Request, exc: RequestValidationError):
    """A 422 naming each field and what is wrong with it. FastAPI's own reply
    echoes the rejected value back, which cannot be sent at all for a body
    of 1e999 (Infinity), so that became a 500 instead."""
    detail = [
        {
            "loc": list(e.get("loc", ())),
            "msg": str(e.get("msg", "")),
            "type": e.get("type"),
        }
        for e in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": detail})


@app.exception_handler(paths.BadId)
def _bad_id(_request: Request, exc: paths.BadId):
    """An id like '..' or 3000 characters names no series or chapter."""
    return JSONResponse(status_code=404, content={"detail": "no such item"})


@app.exception_handler(OSError)
def _os_error(_request: Request, exc: OSError):
    """A series, chapter or line id too long for a file name cannot exist, so
    it is a 404 like any other unknown id rather than a 500. Every other disk
    error still surfaces as a 500 with its traceback in the log."""
    if exc.errno == errno.ENAMETOOLONG:
        return JSONResponse(status_code=404, content={"detail": "no such item"})
    raise exc


_loaded: list[str] = []
_failed: dict[str, str] = {}
for _name in API_MODULES:
    try:
        app.include_router(importlib.import_module(_name).router)
        _loaded.append(_name)
    except Exception as e:  # shown at /api/health, not fatal
        _failed[_name] = f"{type(e).__name__}: {e}"


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "data_root": str(paths.DATA_ROOT),
        "modules": _loaded,
        "failed": _failed,
    }


@app.get("/api/jobs")
def list_jobs():
    return {"jobs": jobs.all_jobs()}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    return job.to_dict()


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    job.cancel()
    return {"ok": True}


if os.path.isdir(SHARED_DIR):
    app.mount("/shared", StaticFiles(directory=SHARED_DIR), name="shared")
app.mount("/data", StaticFiles(directory=str(paths.DATA_ROOT)), name="data")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
