"""Wallpapers - browse the collection, star favourites, set one on the desktop and/or in Forge.

A thin API over `shared/forge_wallpapers.py` (the index, look-alike copies,
favourites, setting the desktop) and `shared/forge_theme.py` (Forge's own
wallpaper, thumbnails and the hub's theme.js). The index is brought up to date
in a background thread when the backend starts; the picker shows what is
already known at once and fills in as the thread works.

Run standalone with:
    FORGE_SHARED_DIR=/home/ejb/Forge/shared \\
    .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8442
"""

from __future__ import annotations

import os
import sys
import threading
import time
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
import forge_wallpapers as fw  # noqa: E402

index_state = {"running": False, "done": 0, "total": 0, "finished_at": 0.0}
_state_lock = threading.Lock()


def _run_index() -> None:
    def progress(done: int, total: int) -> None:
        index_state.update(done=done, total=total)

    try:
        fw.build_index(progress=progress)
    finally:
        index_state.update(running=False, finished_at=time.time())


def start_index() -> bool:
    """Start bringing the index up to date, unless it is already running."""
    with _state_lock:
        if index_state["running"]:
            return False
        index_state.update(running=True, done=0, total=0)
    threading.Thread(target=_run_index, daemon=True, name="wallpaper-index").start()
    return True


@asynccontextmanager
async def lifespan(_app: FastAPI):
    start_index()
    yield


app = FastAPI(title="Wallpapers", lifespan=lifespan)


def _relative(path: Path | None) -> str:
    """A path as a collection name, or "" when it lives outside the folder."""
    if path is None:
        return ""
    try:
        return (
            path.resolve().relative_to(forge_theme.WALLPAPER_DIR.resolve()).as_posix()
        )
    except (OSError, ValueError):
        return ""


def _source(name: str) -> Path:
    source = forge_theme.wallpaper_path(name)
    if source is None:
        raise HTTPException(404, "No wallpaper by that name")
    return source


@app.get("/api/wallpapers")
def wallpapers():
    rows, stale = fw.cached_index()
    settings = forge_theme.load()
    desktop = forge_theme.desktop_wallpaper()
    return {
        "folder": str(forge_theme.WALLPAPER_DIR),
        "wallpapers": fw.catalogue(rows),
        "index": dict(index_state, stale=stale),
        "forge": _relative(forge_theme.chosen_wallpaper(settings)),
        "forge_follows_desktop": not settings["wallpaper"],
        "desktop": _relative(desktop),
        "desktop_path": str(desktop) if desktop else "",
    }


@app.post("/api/reindex")
def reindex():
    return {"started": start_index(), "index": dict(index_state)}


@app.get("/api/thumb")
def thumb(name: str):
    source = _source(name)
    made = forge_theme.thumbnail(source)
    return FileResponse(made or source, headers={"Cache-Control": "max-age=604800"})


@app.get("/api/preview")
def preview(name: str):
    source = _source(name)
    made = fw.preview(source)
    return FileResponse(made or source, headers={"Cache-Control": "max-age=604800"})


@app.post("/api/favourite")
def favourite(payload: dict):
    name = str(payload.get("name", ""))
    _source(name)
    return {"favourites": fw.set_favourite(name, bool(payload.get("on", True)))}


@app.post("/api/apply")
def apply(payload: dict):
    """Set a wallpaper on the desktop, in Forge, or both.

    The answer carries Forge's new theme whenever Forge's look changed - also
    when only the desktop was set but Forge follows the desktop - so the page
    can hand it to the hub straight away.
    """
    name = str(payload.get("name", ""))
    to_desktop, to_forge = bool(payload.get("desktop")), bool(payload.get("forge"))
    if not (to_desktop or to_forge):
        raise HTTPException(400, "Choose the desktop, Forge, or both")
    source = _source(name)
    out: dict = {"desktop": None, "forge": None, "theme": None}

    if to_desktop:
        ok, message = fw.set_desktop(source)
        out["desktop"] = {"ok": ok, "message": message}
        if ok:
            # The shell records the new path itself, a moment later. Forge's
            # theme reads that record when it follows the desktop.
            deadline = time.time() + 2
            while time.time() < deadline and forge_theme.desktop_wallpaper() != source:
                time.sleep(0.1)

    settings = forge_theme.load()
    if to_forge:
        settings = forge_theme.save({"wallpaper": name})
        out["forge"] = {"ok": True, "message": "Forge wallpaper set"}
    if to_forge or (to_desktop and not settings["wallpaper"]):
        theme = forge_theme.theme(settings)
        forge_theme.write_theme_js(HUB_DIR, theme)
        out["theme"] = theme
    return out


@app.get("/api/particles")
def particles():
    """The particle kinds, and each wallpaper's own pick (keyed by file name,
    the way Forge's theme looks it up)."""
    return {
        "kinds": {k: v for k, v in forge_theme.PARTICLE_LABELS.items() if k != "auto"},
        "picks": forge_theme.wallpaper_particle_picks(),
    }


@app.post("/api/particles")
def set_particles(payload: dict):
    """Give one wallpaper its own particles: a kind, "off", or "" to match the
    picture automatically. When it is Forge's wallpaper the answer carries the
    new theme, so the hub shows the change at once."""
    source = _source(str(payload.get("name", "")))
    try:
        picks = forge_theme.set_wallpaper_particles(
            source.name, str(payload.get("kind", ""))
        )
    except ValueError as err:
        raise HTTPException(400, str(err)) from err
    settings = forge_theme.load()
    theme = None
    if forge_theme.chosen_wallpaper(settings) == source:
        theme = forge_theme.theme(settings)
        forge_theme.write_theme_js(HUB_DIR, theme)
    return {"picks": picks, "theme": theme}


@app.get("/api/desktop-particles")
def desktop_particles_state():
    return {"on": forge_theme.load().get("desktop_particles") is True}


@app.post("/api/desktop-particles")
def desktop_particles(payload: dict):
    """Particles on the normal desktop (B38). The GNOME extension watches the
    settings file and desktop/particles.py watches theme.js, so saving both is
    all it takes to start or stop them."""
    settings = forge_theme.save({"desktop_particles": bool(payload.get("on"))})
    theme = forge_theme.theme(settings)
    forge_theme.write_theme_js(HUB_DIR, theme)
    return {"on": settings["desktop_particles"] is True, "theme": theme}


# --- static -----------------------------------------------------------------

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
