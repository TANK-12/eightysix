"""Media: the parts that need no server -- settings, the library scan,
yt-dlp command lines and its output.

Kept apart from web_app.py so tests can run them without FastAPI or the
network. yt-dlp is the system one (/usr/bin/yt-dlp); ffmpeg turns audio into
mp3. Nothing here shells out except `list_remote` and `download`, and both
take the command runner as an argument so tests can hand in a fake.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterable, Optional

SHARED_DIR = Path(
    os.environ.get("FORGE_SHARED_DIR", Path(__file__).resolve().parents[2] / "shared")
)
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

# the command lines live in shared/, so the hub's background music uses the
# same downloader; re-exported here for the routes and the tests
from forge_ytdlp import download_command, progress_of, ytdlp  # noqa: E402,F401

HOME = Path.home()
DATA_DIR = Path(os.environ.get("FORGE_MEDIA_DATA", HOME / ".local/share/forge/media"))
SETTINGS_FILE = DATA_DIR / "settings.json"

AUDIO = {".mp3", ".m4a", ".flac", ".ogg", ".opus", ".wav", ".aac", ".wma"}
VIDEO = {".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi"}
MAX_FILES = 5000
MAX_DEPTH = 4

DEFAULTS = {
    "folders": ["~/Music", "~/Videos", "~/Downloads/MediaForge/Music"],
    "download_folder": "~/Music/Forge",
    "volume": 80,
    "advanced_mode": False,
}

_URL_RE = re.compile(r"^https?://", re.I)


# --------------------------------------------------------------------------
# settings


def load_settings(path: Path = SETTINGS_FILE) -> dict:
    data = dict(DEFAULTS)
    try:
        saved = json.loads(path.read_text())
        if isinstance(saved, dict):
            data.update({k: v for k, v in saved.items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    if not isinstance(data["folders"], list):
        data["folders"] = list(DEFAULTS["folders"])
    data["folders"] = [str(f) for f in data["folders"] if str(f).strip()]
    # a hand-edited file must not take every route down with it
    if (
        not isinstance(data["download_folder"], str)
        or not data["download_folder"].strip()
    ):
        data["download_folder"] = DEFAULTS["download_folder"]
    try:
        data["volume"] = max(0, min(100, int(data.get("volume") or 0)))
    except (TypeError, ValueError, OverflowError):
        data["volume"] = DEFAULTS["volume"]
    data["advanced_mode"] = bool(data["advanced_mode"])
    return data


def save_settings(changes: dict, path: Path = SETTINGS_FILE) -> dict:
    data = load_settings(path)
    data.update({k: v for k, v in changes.items() if k in DEFAULTS})
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)
    return load_settings(path)


def expand(folder: str) -> Path:
    return Path(os.path.expanduser(folder)).resolve()


# --------------------------------------------------------------------------
# library


def kind_of(path: Path) -> Optional[str]:
    ext = path.suffix.lower()
    if ext in AUDIO:
        return "audio"
    if ext in VIDEO:
        return "video"
    return None


def scan(folders: Iterable[str], limit: int = MAX_FILES) -> list[dict]:
    """Every audio and video file under the folders, a few levels deep.
    Hidden folders and anything past `limit` are skipped: a whole home
    directory is not a library, and the page cannot show 50,000 rows."""
    out: list[dict] = []
    seen: set[str] = set()
    for folder in folders:
        try:
            root = expand(folder)
            if not root.is_dir():
                continue
        except (OSError, ValueError):  # unreadable, or a NUL byte saved earlier
            continue
        base_depth = len(root.parts)
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            if len(Path(dirpath).parts) - base_depth >= MAX_DEPTH:
                dirnames[:] = []
            for name in sorted(filenames):
                p = Path(dirpath) / name
                kind = kind_of(p)
                if not kind or str(p) in seen:
                    continue
                try:
                    st = p.stat()
                except OSError:
                    continue
                seen.add(str(p))
                out.append(
                    {
                        "path": str(p),
                        "name": p.stem,
                        "folder": (
                            str(Path(dirpath).relative_to(root))
                            if dirpath != str(root)
                            else ""
                        ),
                        "library": str(root),
                        "kind": kind,
                        "ext": p.suffix.lower().lstrip("."),
                        "size": st.st_size,
                        "mtime": int(st.st_mtime),
                    }
                )
                if len(out) >= limit:
                    return out
    return out


def inside(path: str, folders: Iterable[str]) -> Optional[Path]:
    """The resolved file if it lives under one of the library folders, else
    None. The file route serves nothing outside them."""
    try:
        target = Path(path).expanduser().resolve()
    except (OSError, ValueError):  # ValueError: a NUL byte in the path
        return None
    for folder in folders:
        try:
            root = expand(folder)
            target.relative_to(root)
        except (OSError, ValueError):
            continue
        if target.is_file():
            return target
    return None


# --------------------------------------------------------------------------
# yt-dlp


def list_target(text: str, limit: int = 60) -> str:
    """What to hand yt-dlp for a listing: a link as it is (a channel link
    gets its /videos tab so the uploads come back, not the channel's tabs),
    or a search for a typed name."""
    text = text.strip()
    if not text:
        raise ValueError("paste a link or type a name")
    if _URL_RE.match(text):
        if re.search(r"youtube\.com/(channel/|c/|user/|@)[^/?#]+/?$", text):
            return text.rstrip("/") + "/videos"
        return text
    return f"ytsearch{limit}:{text}"


def list_command(target: str, limit: int = 60) -> list[str]:
    exe = ytdlp() or "yt-dlp"
    return [
        exe,
        "--flat-playlist",
        "--playlist-end",
        str(limit),
        "--no-warnings",
        "-J",
        target,
    ]


def parse_listing(raw: str) -> dict:
    """The -J JSON of a playlist, channel, search or single video into rows
    the page can show: {title, entries: [{id, title, url, duration,
    uploader, channel_url}]}."""
    data = json.loads(raw or "{}")
    entries = data.get("entries")
    if entries is None:
        entries = [data] if data.get("id") else []
    rows = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        vid = e.get("id") or ""
        url = e.get("webpage_url") or e.get("url") or ""
        if url and not _URL_RE.match(url) and vid:
            url = f"https://www.youtube.com/watch?v={vid}"
        rows.append(
            {
                "id": vid,
                "title": e.get("title") or vid,
                "url": url,
                "duration": int(e.get("duration") or 0),
                "uploader": e.get("uploader") or e.get("channel") or "",
                "channel_url": e.get("channel_url") or e.get("uploader_url") or "",
            }
        )
    return {
        "title": data.get("title") or data.get("uploader") or "",
        "uploader": data.get("uploader") or data.get("channel") or "",
        "channel_url": data.get("channel_url") or data.get("uploader_url") or "",
        "entries": rows,
    }


Runner = Callable[[list[str]], subprocess.CompletedProcess]


def list_remote(text: str, run: Runner = subprocess.run, limit: int = 60) -> dict:
    target = list_target(text, limit)
    proc = run(list_command(target, limit))
    if proc.returncode != 0:
        err = (proc.stderr or "").strip().splitlines()
        raise RuntimeError(err[-1] if err else f"yt-dlp failed ({proc.returncode})")
    listing = parse_listing(proc.stdout)
    listing["target"] = target
    return listing
