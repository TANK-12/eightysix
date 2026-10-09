"""Power -- Cool / Auto / Performance modes, auto-switching and login-autostart switches.

Mode files live in modes/; the root-only work is done by /usr/local/bin/forge-power
(a root-owned copy of helper/forge_power.py) through one NOPASSWD sudoers line.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import autostart
import autoswitch
import modes
import priority
import status
from history import History

ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(ROOT, "static")
SHARED_DIR = os.environ.get("FORGE_SHARED_DIR") or os.path.join(
    ROOT, "..", "..", "shared"
)
HUB_DIR = os.path.join(ROOT, "..", "..", "hub")
sys.path.insert(0, os.path.abspath(SHARED_DIR))
import forge_theme  # noqa: E402

SAMPLE_SECONDS = 5
HISTORY = History(max_points=120)


def _sample_forever(stop: threading.Event) -> None:
    while not stop.is_set():
        s = status.snapshot()
        battery = s["battery"] or {}
        HISTORY.add(
            {
                "t": round(time.time()),
                "temp_c": s["temp_c"],
                "avg_mhz": s["avg_mhz"],
                "draw_watts": None if s["on_ac"] else battery.get("draw_watts"),
                "mode": modes.current_mode(),
            }
        )
        stop.wait(SAMPLE_SECONDS)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    stop = threading.Event()
    threading.Thread(target=_sample_forever, args=(stop,), daemon=True).start()
    yield
    stop.set()


app = FastAPI(title="Power", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def bad_body(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """A 422 that names the bad field without echoing its value: FastAPI's
    own answer repeats the input, and a body of 1e999 or NaN cannot be
    written back as JSON, so it turned into a 500."""
    detail = [
        {"loc": list(e.get("loc", ())), "msg": e.get("msg", ""), "type": e.get("type")}
        for e in exc.errors()
    ]
    return JSONResponse({"detail": detail}, status_code=422)


class ToggleBody(BaseModel):
    enabled: bool


class AutoSwitchBody(BaseModel):
    enabled: bool
    battery: str
    ac: str


class FpsBody(BaseModel):
    max_fps: int | None = None
    battery_fps: int | None = None


class PriorityBody(BaseModel):
    nice: int
    background: list[str]
    protected: list[str]


@app.get("/api/modes")
def list_modes():
    try:
        loaded = modes.load_modes()
    except ValueError as exc:
        raise HTTPException(500, str(exc))
    return {
        "modes": [
            {k: m.get(k) for k in ("name", "label", "description", "order", "display")}
            for m in loaded
        ],
        "current": modes.current_mode(),
        "helper_installed": modes.helper_installed(),
    }


@app.post("/api/modes/{name}")
def apply_mode(name: str):
    try:
        return modes.apply_mode(name)
    except KeyError:
        raise HTTPException(404, f"no mode called {name}")
    except modes.HelperError as exc:
        raise HTTPException(502, f"the power helper refused: {exc}")


@app.get("/api/status")
def get_status():
    return {**status.snapshot(), "mode": modes.current_mode()}


@app.get("/api/history")
def get_history():
    return {"points": HISTORY.points(), "interval_s": SAMPLE_SECONDS}


@app.get("/api/watts")
def get_watts():
    try:
        return modes.measure_watts()
    except modes.HelperError as exc:
        raise HTTPException(502, str(exc))


@app.get("/api/processes")
def processes(limit: int = 8):
    # -1 used to list every process on the machine
    return {"processes": status.top_processes(max(1, min(limit, 100)))}


@app.get("/api/priority")
def get_priority():
    running = subprocess.run(
        ["systemctl", "--user", "is-active", "forge-power-priority.service"],
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()
    return {
        "config": priority.load_config(),
        "watcher": running or "unknown",
        "presets": priority.load_presets(),
    }


@app.post("/api/priority")
def set_priority(body: PriorityBody):
    try:
        priority.save_config(priority.CONFIG_PATH, body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    cfg = priority.load_config()
    applied = priority.apply(priority.plan(cfg, priority.all_processes()))
    return {**get_priority(), "applied": applied}


@app.get("/api/autoswitch")
def get_autoswitch():
    running = subprocess.run(
        ["systemctl", "--user", "is-active", "forge-power-watch.service"],
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()
    return {**autoswitch.load_config(), "watcher": running or "unknown"}


@app.post("/api/autoswitch")
def set_autoswitch(body: AutoSwitchBody):
    names = [m["name"] for m in modes.load_modes()]
    try:
        autoswitch.save_config(autoswitch.CONFIG_PATH, body.model_dump(), names)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return get_autoswitch()


@app.get("/api/fps")
def get_fps():
    """Forge's frame-rate caps (B39), plugged in and on battery: the same
    settings as Settings > Speed and detail."""
    spec = forge_theme.SETTINGS["max_fps"]
    saved = forge_theme.load()
    return {
        "max_fps": saved["max_fps"],
        "battery_fps": saved["battery_fps"],
        "min": spec["min"],
        "max": spec["max"],
    }


@app.post("/api/fps")
def set_fps(body: FpsBody):
    """Save the cap and rewrite hub/theme.js; the page then hands the new
    theme to the hub, which passes it on to every open app."""
    changes = {
        key: getattr(body, key)
        for key in ("max_fps", "battery_fps")
        if getattr(body, key) is not None
    }
    settings = forge_theme.save(changes)
    theme = forge_theme.theme(settings)
    forge_theme.write_theme_js(Path(HUB_DIR), theme)
    return {
        "max_fps": settings["max_fps"],
        "battery_fps": settings["battery_fps"],
        "theme": theme,
    }


@app.get("/api/autostart")
def list_autostart():
    return {"entries": autostart.list_entries()}


@app.post("/api/autostart/{filename}")
def toggle_autostart(filename: str, body: ToggleBody):
    try:
        autostart.set_enabled(autostart.AUTOSTART_DIR, filename, body.enabled)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except FileNotFoundError:
        raise HTTPException(404, f"no autostart entry {filename}")
    return {"ok": True, "entries": autostart.list_entries()}


@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(STATIC_DIR, "index.html"), encoding="utf-8") as handle:
        return handle.read()


if os.path.isdir(SHARED_DIR):
    app.mount("/shared", StaticFiles(directory=SHARED_DIR), name="shared")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
