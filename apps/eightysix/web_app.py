"""Eighty Six -- the Forge hub tile for the Juggernaut walker game.

The game itself lives in a separate repo (EIGHTYSIX_ROOT, default
~/Games/eightysix), built by lane A1 of the juggernaut-alpha wave. This
backend owns no game logic: it launches the game or its editor, and reads
the file contracts the game writes (test results, per-preset fps logs, check
images, the README) so Forge can show them without leaving the hub.

Run standalone with:
    FORGE_SHARED_DIR=~/Forge/shared .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8464
"""

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"

GRAPHICS_PRESETS = ["low", "medium", "high", "ultra"]

FORGE_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUTS_DIR = FORGE_ROOT / "outputs"
LAUNCH_LOG = OUTPUTS_DIR / "eightysix-launch.log"

_SHARED_DIR = os.environ.get("FORGE_SHARED_DIR") or str(FORGE_ROOT / "shared")


def game_root() -> Path:
    return Path(os.environ.get("EIGHTYSIX_ROOT", "~/Games/eightysix")).expanduser()


app = FastAPI(title="Eighty Six")

if os.path.isdir(_SHARED_DIR):
    app.mount("/shared", StaticFiles(directory=_SHARED_DIR), name="shared")


@app.get("/api/status")
def status():
    root = game_root()
    return {"ok": True, "root": str(root), "root_exists": root.is_dir()}


# The test run this backend started, so a second click cannot start another
# one on top of it (two runs would both write logs/tests-last.json). The run
# outlives a backend restart (its own session), so its pid is kept on disk too.
_tests_proc: Optional[subprocess.Popen] = None
TESTS_PID = OUTPUTS_DIR / "eightysix-tests.pid"


def _running(proc: Optional[subprocess.Popen]) -> bool:
    return proc is not None and proc.poll() is None


def _tests_running() -> bool:
    if _running(_tests_proc):
        return True
    try:
        pid = int(TESTS_PID.read_text().strip())
        os.kill(pid, 0)
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
    except (OSError, ValueError):
        return False
    return b"run_tests.sh" in cmdline


@app.get("/api/tests")
def tests_last():
    path = game_root() / "logs" / "tests-last.json"
    running = _tests_running()
    if not path.is_file():
        return {"available": False, "running": running}
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(500, f"tests-last.json is not readable: {exc}")
    if not isinstance(data, dict):
        raise HTTPException(500, "tests-last.json is not readable: not an object")
    data["available"] = True
    data["running"] = running
    return data


@app.post("/api/tests/run")
def tests_run():
    global _tests_proc
    script = game_root() / "tools" / "run_tests.sh"
    if not script.is_file() or not os.access(script, os.X_OK):
        return {"started": False, "reason": "tools/run_tests.sh does not exist yet"}
    if _tests_running():
        return {"started": False, "reason": "The tests are already running"}
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(LAUNCH_LOG, "a") as log:
        _tests_proc = subprocess.Popen(
            [str(script)],
            cwd=str(game_root()),
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    TESTS_PID.write_text(str(_tests_proc.pid))
    return {"started": True}


@app.get("/api/fps")
def fps_latest():
    fps_dir = game_root() / "logs" / "fps"
    latest: dict[str, Optional[dict]] = {preset: None for preset in GRAPHICS_PRESETS}
    if fps_dir.is_dir():
        for path in fps_dir.glob("*.json"):
            try:
                record = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            preset = record.get("preset")
            if preset not in latest:
                continue
            current = latest[preset]
            if current is None or record.get("when", "") > current.get("when", ""):
                latest[preset] = record
    results = []
    for preset in GRAPHICS_PRESETS:
        record = latest[preset]
        met, met_by = (None, None) if record is None else target_met(record)
        results.append(
            {"preset": preset, "record": record, "met_target": met, "met_by": met_by}
        )
    return {"presets": results}


def target_met(record: dict) -> tuple[Optional[bool], Optional[str]]:
    """Whether a preset met its fps target, and judged from what.

    Off-screen runs are held to the compositor's refresh (vsync_cap_hz, 60) so the measured
    average cannot pass it; when that cap sits at or near the target, the record's uncapped
    estimate (from GPU and CPU frame times) decides and is labelled "estimate".
    """
    # a hand-edited or half-written log may hold anything: only numbers count
    target, cap, estimate, avg = (
        v if isinstance(v, (int, float)) and not isinstance(v, bool) else None
        for v in (
            record.get(k)
            for k in ("target_fps", "vsync_cap_hz", "est_uncapped_fps", "avg_fps")
        )
    )
    if target is None:
        return None, None
    if cap and estimate is not None and target >= cap * 0.95:
        return estimate >= target, "estimate"
    return (avg or 0) >= target, "measured"


IMAGE_FOLDER_RE = re.compile(r"^(\d{3})-")


def _sorted_image_folders(images_dir: Path) -> list[str]:
    folders = (
        [p for p in images_dir.iterdir() if p.is_dir()] if images_dir.is_dir() else []
    )

    def sort_key(p: Path):
        match = IMAGE_FOLDER_RE.match(p.name)
        return (int(match.group(1)) if match else -1, p.stat().st_mtime)

    folders.sort(key=sort_key, reverse=True)
    return [p.name for p in folders]


@app.get("/api/images")
def images_index():
    images_dir = game_root() / "images"
    folders = _sorted_image_folders(images_dir)
    return {"folders": folders, "newest": folders[0] if folders else None}


def _safe_image_folder(folder: str) -> Path:
    images_dir = (game_root() / "images").resolve()
    candidate = (images_dir / folder).resolve()
    if images_dir not in candidate.parents and candidate != images_dir:
        raise HTTPException(400, "bad folder")
    if not candidate.is_dir():
        raise HTTPException(404, "no such folder")
    return candidate


@app.get("/api/images/{folder}")
def images_folder(folder: str):
    path = _safe_image_folder(folder)
    files = sorted(p.name for p in path.iterdir() if p.suffix.lower() == ".png")
    report = None
    report_path = path / "report.json"
    if report_path.is_file():
        try:
            report = json.loads(report_path.read_text())
        except (json.JSONDecodeError, OSError):
            report = None
    return {"folder": folder, "files": files, "report": report}


@app.get("/api/images/{folder}/{filename}")
def image_file(folder: str, filename: str):
    path = _safe_image_folder(folder)
    target = (path / filename).resolve()
    if path not in target.parents or target.suffix.lower() != ".png":
        raise HTTPException(400, "bad file")
    if not target.is_file():
        raise HTTPException(404, "no such image")
    return FileResponse(target)


def _parse_readme(text: str) -> dict:
    current_state = ""
    state_match = re.search(
        r"^## Current state\s*\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL
    )
    if state_match:
        current_state = state_match.group(1).strip()

    newest_log_entry = ""
    entries = re.findall(r"^### .*?(?=^### |\Z)", text, re.MULTILINE | re.DOTALL)
    if entries:
        newest_log_entry = entries[-1].strip()

    return {"current_state": current_state, "newest_log_entry": newest_log_entry}


@app.get("/api/readme")
def readme():
    path = game_root() / "README.md"
    if not path.is_file():
        return {"available": False}
    parsed = _parse_readme(path.read_text())
    parsed["available"] = True
    return parsed


# When each command was last launched: the same launch again within
# LAUNCH_COOLDOWN seconds is a double click, not a wish for two game windows.
LAUNCH_COOLDOWN = 5.0
_recent_launches: dict[str, float] = {}


def _launch_detached(args: list[str]):
    key = "\0".join(args)
    now = time.monotonic()
    if now - _recent_launches.get(key, -LAUNCH_COOLDOWN) < LAUNCH_COOLDOWN:
        raise HTTPException(409, "Already starting; give it a few seconds.")
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(LAUNCH_LOG, "a") as log:
        subprocess.Popen(
            args,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    # only a launch that started counts: a failed one may be tried again at once
    _recent_launches[key] = now


class PlayRequest(BaseModel):
    version: Optional[str] = None


@app.post("/api/play")
def play(req: Optional[PlayRequest] = None):
    """Runs the game through its own tools/play.sh (rebuilds when the source changed, saves the
    build as a version); a version number plays that saved version instead."""
    root = game_root()
    launcher = root / "tools" / "play.sh"
    version = req.version if req else None
    if version is not None and not re.fullmatch(r"\d{1,3}|latest|previous", version):
        raise HTTPException(400, "version must be a number, latest or previous")
    if version is not None and version.isdigit():
        version = str(int(version))  # 7 and 007 are one version (and one cooldown)
    if launcher.is_file() and os.access(launcher, os.X_OK):
        args = [str(launcher)] + (["--version", version] if version else [])
        _launch_detached(args)
        return {
            "launched": True,
            "mode": "version" if version else "auto",
            "command": " ".join(args),
        }
    build = root / "build" / "linux" / "eightysix.x86_64"
    if build.is_file() and os.access(build, os.X_OK):
        _launch_detached([str(build)])
        return {"launched": True, "mode": "build", "command": str(build)}
    args = ["godot", "--path", str(root)]
    _launch_detached(args)
    return {"launched": True, "mode": "editor-run", "command": " ".join(args)}


@app.get("/api/versions")
def versions_list():
    """Saved builds from <root>/build/versions/NNN-*/VERSION.json, newest first, with share zips."""
    base = game_root() / "build" / "versions"
    found = []
    if base.is_dir():
        for d in base.iterdir():
            info_file = d / "VERSION.json"
            if not (
                d.is_dir() and re.match(r"^\d{3}-", d.name) and info_file.is_file()
            ):
                continue
            try:
                info = json.loads(info_file.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            share = d / "share"
            info["dir"] = str(d)
            info["share"] = (
                sorted(str(z) for z in share.glob("*.zip")) if share.is_dir() else []
            )
            found.append(info)
    found.sort(key=lambda v: v.get("number", 0), reverse=True)
    return {"available": bool(found), "versions": found}


_share_proc: Optional[subprocess.Popen] = None


@app.get("/api/share")
def share_state():
    """The share zips on disk (only the newest version's are kept, in <root>/build/share/), whether a
    share run is going, and the last line of its log."""
    root = game_root()
    zips = sorted((root / "build" / "share").glob("*.zip"))
    log = root / "logs" / "share.log"
    last = ""
    if log.is_file():
        lines = [line for line in log.read_text().splitlines() if line.strip()]
        last = lines[-1] if lines else ""
    return {
        "running": _running(_share_proc),
        "zips": [
            {"path": str(z), "name": z.name, "mb": round(z.stat().st_size / 1e6)}
            for z in zips
        ],
        "folder": str(root / "build" / "share"),
        "last_log": last,
    }


@app.post("/api/share")
def share_build():
    """Starts tools/builds.py share: Windows, Linux and macOS zips of the newest saved version, each with
    an install script; the older zips are deleted once the new ones are made."""
    global _share_proc
    root = game_root()
    tool = root / "tools" / "builds.py"
    if not tool.is_file():
        return {"started": False, "reason": "tools/builds.py not found in the game"}
    if _share_proc is not None and _share_proc.poll() is None:
        return {"started": False, "reason": "Share zips are already being made"}
    (root / "logs").mkdir(parents=True, exist_ok=True)
    with open(root / "logs" / "share.log", "a") as log:
        _share_proc = subprocess.Popen(
            ["python3", str(tool), "share"],
            cwd=str(root),
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    return {"started": True}


@app.post("/api/share/clear")
def share_clear():
    """Deletes every share zip (tools/builds.py clear-shares); saved versions are kept."""
    root = game_root()
    tool = root / "tools" / "builds.py"
    if not tool.is_file():
        return {"cleared": False, "reason": "tools/builds.py not found in the game"}
    if _share_proc is not None and _share_proc.poll() is None:
        return {
            "cleared": False,
            "reason": "Share zips are being made; wait for it to finish",
        }
    done = subprocess.run(
        ["python3", str(tool), "clear-shares"],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    if done.returncode != 0:
        return {"cleared": False, "reason": (done.stderr or done.stdout).strip()}
    return {"cleared": True, "message": done.stdout.strip()}


@app.post("/api/play/editor")
def play_editor():
    root = game_root()
    args = ["godot", "-e", "--path", str(root)]
    _launch_detached(args)
    return {"launched": True, "mode": "editor", "command": " ".join(args)}


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
