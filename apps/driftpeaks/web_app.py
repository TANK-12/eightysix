"""Drift Peaks - an endless low-poly snowboarding game.

The backend is thin. The terrain, the physics and all drawing run in the
browser (static/js/). This serves:

    /api/shapes          every low-poly shape the game draws, from the shared
                         Forge content store (~/ForgeGameData/shapes/driftpeaks-*)
    /api/shapes/{id}     PUT saves an edited shape; DELETE puts the shipped
                         original back
    /api/levels          the goal levels, data/levels.json
    /api/save            the save file: best runs, coins, level, settings
    /api/sounds          the driftpeaks-* sound recipes from the shared store

The art is data, not code: data/shapes/*.json are the shipped originals, and
on start each one is copied into the shared store if it is not there yet, so
the store copy is the one that gets edited (by the in-game Art editor or any
other Forge tool) and the game only ever reads the store. The sound recipes
work the same way from data/sounds.json.

Run standalone with:
    FORGE_SHARED_DIR=/home/ejb/Forge/shared \\
    .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8457
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
DATA_DIR = ROOT / "data"
SHIPPED_SHAPES = DATA_DIR / "shapes"
SHIPPED_SOUNDS = DATA_DIR / "sounds.json"
LEVELS_FILE = DATA_DIR / "levels.json"
# Background music: every audio file in this folder plays in name order. The
# files are hardlinks to the tracks in ~/Music/Alto, so they cost no extra disk.
MUSIC_DIR = Path(os.environ.get("DRIFTPEAKS_MUSIC", ROOT / "music"))
MUSIC_TYPES = {
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".m4a": "audio/mp4",
    ".flac": "audio/flac",
    ".wav": "audio/wav",
}
SHARED_DIR = Path(os.environ.get("FORGE_SHARED_DIR", ROOT.parent.parent / "shared"))
SAVE_DIR = Path(
    os.environ.get("DRIFTPEAKS_DATA", Path.home() / "ForgeGameData" / "driftpeaks")
)
PREFIX = "driftpeaks-"
SHAPE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
ROLE = re.compile(r"^[a-z][a-zA-Z0-9]{0,31}$")
MAX_PARTS = 64
MAX_POINTS = 64
MAX_SAVE_BYTES = 256_000
NO_STORE = {"Cache-Control": "no-store"}

if SHARED_DIR.is_dir() and str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))
forge_content: Any
try:
    import forge_content  # noqa: E402
except ImportError:  # running without the Forge shared kit: shipped art only
    forge_content = None

app = FastAPI(title="Drift Peaks")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def shape_problems(shape: Any) -> list[str]:
    """What is wrong with a shape, beyond the store's required fields. The
    game trusts every point it is handed, so the bounds are checked here."""
    if not isinstance(shape, dict):
        return ["a shape must be a JSON object"]
    problems = []
    parts = shape.get("parts")
    if not isinstance(parts, list) or not parts:
        return ["parts must be a non-empty list"]
    if len(parts) > MAX_PARTS:
        problems.append(f"at most {MAX_PARTS} parts")
    for n, part in enumerate(parts[:MAX_PARTS]):
        if not isinstance(part, dict):
            problems.append(f"part {n} is not an object")
            continue
        if not isinstance(part.get("role"), str) or not ROLE.match(part["role"]):
            problems.append(f"part {n}: role must be a short name like 'snow'")
        points = part.get("points")
        if not isinstance(points, list) or not 3 <= len(points) <= MAX_POINTS:
            problems.append(f"part {n}: points must be 3 to {MAX_POINTS} [x, y] pairs")
            continue
        for p in points:
            if (
                not isinstance(p, list)
                or len(p) != 2
                or not all(
                    isinstance(v, (int, float)) and not isinstance(v, bool) for v in p
                )
                or not all(-2000 <= v <= 2000 for v in p)
            ):
                problems.append(f"part {n}: every point is [x, y] within ±2000")
                break
    return problems


def shipped_shapes() -> dict[str, dict]:
    shapes = {}
    if SHIPPED_SHAPES.is_dir():
        for path in sorted(SHIPPED_SHAPES.glob("*.json")):
            data = _read_json(path)
            if isinstance(data, dict) and not shape_problems(data):
                data["id"] = path.stem
                shapes[path.stem] = data
    return shapes


def _store_entry(sid: str, shape: dict) -> dict:
    entry = dict(shape)
    entry["id"] = PREFIX + sid
    return entry


def seed_store() -> None:
    """Copy each shipped shape and sound into the shared store once. An entry
    already there is the user's (maybe edited) copy and is never overwritten."""
    if forge_content is None:
        return
    have = set(forge_content.list_ids("shapes"))
    for sid, shape in shipped_shapes().items():
        if PREFIX + sid not in have:
            forge_content.save("shapes", _store_entry(sid, shape), strict=False)
    sounds = _read_json(SHIPPED_SOUNDS)
    if isinstance(sounds, dict):
        have = set(forge_content.list_ids("sounds"))
        for sid, recipe in sounds.items():
            if PREFIX + sid not in have and isinstance(recipe, dict):
                forge_content.save(
                    "sounds", {**recipe, "id": PREFIX + sid}, strict=False
                )


def load_shapes() -> tuple[dict[str, dict], list[str]]:
    """Every shape by its short id (no prefix): the store copy where there is
    one and it is sound, else the shipped original."""
    shapes = shipped_shapes()
    problems: list[str] = []
    if forge_content is None:
        return shapes, ["The Forge shared kit is missing; showing the shipped art."]
    seed_store()
    for full in forge_content.list_ids("shapes"):
        if not full.startswith(PREFIX):
            continue
        sid = full[len(PREFIX) :]
        try:
            entry = forge_content.load("shapes", full)
        except (OSError, ValueError, forge_content.ContentError) as exc:
            problems.append(f"shapes/{full}.json: {exc}")
            continue
        found = shape_problems(entry)
        if found:
            problems += [f"shapes/{full}.json: {p}" for p in found[:3]]
            continue
        entry["id"] = sid
        shapes[sid] = entry
    return shapes, problems


@app.get("/api/shapes")
def get_shapes():
    shapes, problems = load_shapes()
    return JSONResponse(
        {"shapes": shapes, "shipped": sorted(shipped_shapes()), "problems": problems},
        headers=NO_STORE,
    )


@app.put("/api/shapes/{sid}")
def put_shape(sid: str, shape: dict = Body(...)):
    if not SHAPE_ID.match(sid):
        raise HTTPException(400, "a shape id is lower-case letters, digits and dashes")
    if forge_content is None:
        raise HTTPException(
            503, "the Forge shared kit is missing, so there is no store"
        )
    problems = shape_problems(shape)
    if not isinstance(shape.get("label"), str) or not shape.get("label"):
        problems.append("label is required")
    if problems:
        raise HTTPException(422, "; ".join(problems[:5]))
    forge_content.save("shapes", _store_entry(sid, shape))
    return {"ok": True, "id": sid}


@app.delete("/api/shapes/{sid}")
def revert_shape(sid: str):
    """Put the shipped original back. A shape the game never shipped is
    removed from the store instead."""
    if not SHAPE_ID.match(sid):
        raise HTTPException(400, "bad shape id")
    if forge_content is None:
        raise HTTPException(503, "the Forge shared kit is missing")
    original = shipped_shapes().get(sid)
    if original:
        forge_content.save("shapes", _store_entry(sid, original))
        return {"ok": True, "reverted": True}
    try:
        removed = forge_content.SHARED.delete("shapes", PREFIX + sid)
    except OSError:
        removed = False
    if not removed:
        raise HTTPException(404, "no such shape")
    return {"ok": True, "reverted": False}


@app.get("/api/levels")
def get_levels():
    data = _read_json(LEVELS_FILE)
    if not isinstance(data, dict) or not isinstance(data.get("levels"), list):
        return JSONResponse(
            {"levels": [], "problems": ["data/levels.json is unreadable"]}
        )
    return data


def save_path() -> Path:
    return SAVE_DIR / "save.json"


@app.get("/api/save")
def get_save():
    data = _read_json(save_path())
    return JSONResponse(data if isinstance(data, dict) else {}, headers=NO_STORE)


@app.put("/api/save")
def put_save(data: dict = Body(...)):
    text = json.dumps(data, indent=1)
    if len(text) > MAX_SAVE_BYTES:
        raise HTTPException(413, "the save is too large")
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = save_path().with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(save_path())
    return {"ok": True}


@app.get("/api/sounds")
def get_sounds():
    """The driftpeaks-* recipes, keyed by event. Without the store the shipped
    recipes play as they are."""
    shipped = _read_json(SHIPPED_SOUNDS)
    shipped = shipped if isinstance(shipped, dict) else {}
    if forge_content is None:
        return {"sounds": [{**r, "id": PREFIX + k} for k, r in shipped.items()]}
    seed_store()
    rows = []
    for sid in forge_content.list_ids("sounds"):
        if not sid.startswith(PREFIX):
            continue
        try:
            entry = forge_content.load("sounds", sid)
        except (OSError, ValueError, forge_content.ContentError):
            continue
        if not forge_content.validate("sounds", entry):
            rows.append(entry)
    return {"sounds": rows}


def music_files() -> list[Path]:
    if not MUSIC_DIR.is_dir():
        return []
    return sorted(
        (
            f
            for f in MUSIC_DIR.iterdir()
            if f.is_file() and f.suffix.lower() in MUSIC_TYPES
        ),
        key=lambda f: f.name.lower(),
    )


@app.get("/api/music")
def get_music():
    return {
        "tracks": [
            {"name": f.stem, "url": "music/" + quote(f.name)} for f in music_files()
        ]
    }


@app.get("/music/{name}")
def get_track(name: str):
    """Only a file the list offers; nothing else in (or above) the folder."""
    for f in music_files():
        if f.name == name:
            return FileResponse(f, media_type=MUSIC_TYPES[f.suffix.lower()])
    raise HTTPException(404, "no such track")


if SHARED_DIR.is_dir():
    app.mount("/shared", StaticFiles(directory=str(SHARED_DIR)), name="shared")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
