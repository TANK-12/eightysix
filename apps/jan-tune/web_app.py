"""Jan Tune -- pick a Jan model, let it measure settings, apply the winner.

All the tuning lives in tune.py (also usable from the command line); this is
the page and a background thread for one run at a time.
"""

from __future__ import annotations

import json
import os
import threading

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import tune

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

app = FastAPI(title="Jan Tune")
_run: dict = {"tuner": None, "thread": None}


class RunRequest(BaseModel):
    model: str = Field(min_length=1, max_length=200)
    repeats: int = Field(2, ge=1, le=10)
    interval: float = Field(10, ge=0, le=600)
    free_idle: bool = True
    knobs: dict[str, list] | None = None


def _safe_id(model_id: str) -> bool:
    """A model id names one folder: no path parts, no hidden names."""
    return bool(model_id) and "/" not in model_id and not model_id.startswith(".")


def _model(model_id: str) -> tune.Model:
    if not _safe_id(model_id):
        raise HTTPException(404, "no such model")
    try:
        return tune.find_model(model_id)
    except KeyError as e:
        raise HTTPException(404, str(e))


def _saved(model_id: str) -> dict | None:
    if not _safe_id(model_id):
        return None
    try:
        return json.loads((tune.DATA_DIR / "results" / f"{model_id}.json").read_text())
    except (OSError, ValueError):
        return None


def _running() -> tune.Tuner | None:
    t, th = _run["tuner"], _run["thread"]
    return t if th and th.is_alive() else None


@app.get("/api/models")
def models():
    out = []
    g = tune.jan_globals()
    for m in tune.discover_models():
        saved = _saved(m.id) or {}
        best = saved.get("best") or {}
        out.append(
            {
                "id": m.id,
                "name": m.name,
                "layers": m.layers,
                "moe": m.moe,
                "size_gb": round(m.size / 1024**3, 2),
                "current": tune.baseline(m, g),
                "best_gen": best.get("gen"),
                "status": saved.get("status"),
            }
        )
    return {"models": out, "jan": g}


@app.get("/api/knobs")
def knobs(model: str):
    m = _model(model)
    return [
        {"name": k.name, "values": k.values(m), "apply": k.apply}
        for k in tune.KNOBS
        if k.when(m)
    ]


@app.get("/api/status")
def status(model: str | None = None):
    t = _running()
    if t and (model is None or model == t.model.id):
        return {"running": True, **t.snapshot()}
    return {"running": bool(t), "running_model": t.model.id if t else None} | (
        _saved(model) or {} if model else {}
    )


def _checked_knobs(m: tune.Model, asked: dict[str, list] | None) -> dict | None:
    """Only this model's own knobs, each with values from its own list: they
    become llama-server flags, so nothing else may reach the command line."""
    if not asked:
        return None
    allowed = {k.name: k.values(m) for k in tune.KNOBS if k.when(m)}
    out = {}
    for name, values in asked.items():
        if name not in allowed:
            raise HTTPException(400, f"unknown setting: {name[:60]}")
        kinds = {type(a) for a in allowed[name]}
        bad = [v for v in values if v not in allowed[name] or type(v) not in kinds]
        if bad:
            raise HTTPException(400, f"{name} cannot be {str(bad[0])[:40]}")
        out[name] = values  # an empty list means every value of that knob
    return out or None


@app.post("/api/run")
def run(req: RunRequest):
    if _running():
        raise HTTPException(409, "a tuning run is already going")
    m = _model(req.model)
    t = tune.Tuner(
        m,
        repeats=req.repeats,
        interval=req.interval,
        knobs=_checked_knobs(m, req.knobs),
        free_idle=req.free_idle,
    )
    th = threading.Thread(target=t.run, daemon=True)
    _run.update(tuner=t, thread=th)
    th.start()
    return {"ok": True}


@app.post("/api/stop")
def stop():
    t = _running()
    if t:
        t.stop.set()
    return {"ok": True}


@app.post("/api/apply/{model_id}")
def apply(model_id: str):
    if (t := _running()) and t.model.id == model_id:
        raise HTTPException(409, "wait for the run to finish")
    best = (_saved(model_id) or {}).get("best") or {}
    if not best.get("gen"):
        raise HTTPException(400, "no finished result to apply")
    written = tune.apply(_model(model_id), best["config"])
    return {"written": written}


@app.on_event("shutdown")
def _shutdown():
    t = _running()
    if t:
        t.stop.set()
        if _run["thread"]:
            _run["thread"].join(timeout=30)


SHARED_DIR = str(tune.SHARED_DIR)
if os.path.isdir(SHARED_DIR):
    app.mount("/shared", StaticFiles(directory=SHARED_DIR), name="shared")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
