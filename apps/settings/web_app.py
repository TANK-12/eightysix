"""Settings - how Forge looks and behaves.

A thin API over `shared/forge_theme.py`, which owns every setting, the
wallpaper rendering and the colour extraction. This app only reads and saves
them, serves wallpaper thumbnails for its picker, and rewrites `hub/theme.js`
so the next launch opens with the same look. The live change is sent by the
page straight to the hub with postMessage, so nothing waits on a restart.

Run standalone with:
    FORGE_SHARED_DIR=/home/ejb/Forge/shared \\
    .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8441
"""

from __future__ import annotations

import os
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
SHARED_DIR = Path(os.environ.get("FORGE_SHARED_DIR", ROOT.parent.parent / "shared"))
HUB_DIR = SHARED_DIR.parent / "hub"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

import forge_theme  # noqa: E402
import forge_wallpapers  # noqa: E402


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Thumbnails are made ahead of time, niced, so the wallpaper picker is
    # already full by the time anyone opens it. Cached, so only the first
    # launch does real work.
    current = forge_theme.chosen_wallpaper(forge_theme.load())
    threading.Thread(
        target=forge_theme.warm_thumbnails,
        kwargs={"first": [current.name] if current else []},
        daemon=True,
        name="thumbnails",
    ).start()
    yield


app = FastAPI(title="Settings", lifespan=lifespan)


@app.get("/api/settings")
def get_settings():
    settings = forge_theme.load()
    desktop = forge_theme.desktop_wallpaper()
    return {
        "settings": settings,
        "fields": forge_theme.describe(),
        "theme": forge_theme.theme(settings),
        "config": str(forge_theme.CONFIG),
        "cache": str(forge_theme.CACHE),
        "wallpaper_dir": str(forge_theme.WALLPAPER_DIR),
        "desktop_wallpaper": desktop.name if desktop else "",
    }


@app.post("/api/settings")
def save_settings(payload: dict | None = None):
    """Save the changed settings and return the theme they produce.

    Also rewrites hub/theme.js, so the next launch opens with this look.
    """
    settings = forge_theme.save(payload or {})
    if "start_at_login" in (payload or {}):
        forge_theme.set_autostart(settings["start_at_login"])
    data = forge_theme.theme(settings)
    forge_theme.write_theme_js(HUB_DIR, data)
    return {"settings": settings, "theme": data}


@app.post("/api/settings/reset")
def reset_settings():
    defaults = {key: spec["default"] for key, spec in forge_theme.SETTINGS.items()}
    return save_settings(defaults)


@app.get("/api/wallpapers")
def wallpapers():
    return {
        "folder": str(forge_theme.WALLPAPER_DIR),
        "wallpapers": forge_theme.list_wallpapers(),
    }


@app.get("/api/favourites")
def favourite_wallpapers():
    """Wallpapers starred in the Wallpapers app, if they still exist."""
    known = {w["name"] for w in forge_theme.list_wallpapers()}
    return {"favourites": [n for n in forge_wallpapers.favourites() if n in known]}


# `:path` because a wallpaper in a sub-folder is named "anime/moon.png".
@app.get("/api/wallpapers/{name:path}/thumb")
def wallpaper_thumb(name: str):
    """A small preview. Only names the folder listing vouches for are served."""
    source = forge_theme.wallpaper_path(name)
    if source is None:
        raise HTTPException(404, "No wallpaper by that name")
    thumb = forge_theme.thumbnail(source)
    return FileResponse(thumb or source, headers={"Cache-Control": "max-age=604800"})


# --- static -----------------------------------------------------------------

if SHARED_DIR.is_dir():
    app.mount("/shared", StaticFiles(directory=str(SHARED_DIR)), name="shared")


@app.get("/")
def index():
    target = STATIC_DIR / "index.html"
    if not target.is_file():
        return JSONResponse({"error": "static/index.html is missing"}, status_code=500)
    return FileResponse(target)


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
