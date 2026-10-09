"""Where PrintForge looks for STL files, its settings, and the analysis cache.

Settings live in ~/.config/forge-printforge/settings.json and the per-file
analysis cache in ~/.cache/forge-printforge/info.json (both overridable with
PRINTFORGE_CONFIG_DIR / PRINTFORGE_CACHE_DIR, which the tests use). A file is
only ever served or analysed when it resolves inside one of the configured
roots and ends in .stl.
"""

from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path

import stl

SKIP_DIRS = {".venv", "node_modules", "__pycache__", ".git", "wineprefix"}
MAX_DEPTH = 8

DEFAULTS = {
    "roots": ["~/Models", "~/Downloads"],
    "advanced_mode": False,
    "bed": "filament 256 class",
    "beds": {
        "filament 256 class": [256, 256, 256],
        "filament 220 class": [220, 220, 250],
        "resin 218x123 class": [218, 123, 220],
        "resin 153x77 class": [153, 77, 165],
    },
    "color": "#c9c3b5",
    "light": 1.0,
}


def config_dir() -> Path:
    return Path(
        os.environ.get("PRINTFORGE_CONFIG_DIR") or "~/.config/forge-printforge"
    ).expanduser()


def cache_dir() -> Path:
    return Path(
        os.environ.get("PRINTFORGE_CACHE_DIR") or "~/.cache/forge-printforge"
    ).expanduser()


def _number(x, lo: float, hi: float) -> bool:
    return (
        isinstance(x, (int, float))
        and not isinstance(x, bool)
        and math.isfinite(x)
        and lo <= x <= hi
    )


def _bed_ok(size) -> bool:
    return (
        isinstance(size, list)
        and len(size) == 3
        and all(_number(v, 1, 5000) for v in size)
    )


def _expands(root: str) -> bool:
    """A root whose ~ can be expanded (~nosuchuser cannot, and would make
    every library read fail)."""
    try:
        Path(root).expanduser()
    except RuntimeError:
        return False
    return True


# Why a stored or posted value is refused, per setting (None when it is fine).
CHECKS = {
    "roots": lambda v: (
        None
        if isinstance(v, list)
        and len(v) <= 64
        and all(
            isinstance(r, str) and 0 < len(r) <= 4096 and "\0" not in r and _expands(r)
            for r in v
        )
        else "roots must be a list of folder paths"
    ),
    "advanced_mode": lambda v: (
        None if isinstance(v, bool) else "mode must be true or false"
    ),
    "bed": lambda v: (
        None if isinstance(v, str) and 0 < len(v) <= 80 else "bed must be a bed name"
    ),
    "beds": lambda v: (
        None
        if isinstance(v, dict)
        and 0 < len(v) <= 32
        and all(
            isinstance(k, str) and 0 < len(k) <= 80 and _bed_ok(b) for k, b in v.items()
        )
        else "beds must map names to [width, depth, height] in mm (1 to 5000)"
    ),
    "color": lambda v: (
        None
        if isinstance(v, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", v)
        else "colour must look like #c9c3b5"
    ),
    "light": lambda v: (
        None if _number(v, 0.05, 5) else "light must be a number from 0.05 to 5"
    ),
}


def _settled(cur: dict) -> dict:
    """A bed that is not in the bed list falls back to the first bed."""
    if cur["bed"] not in cur["beds"]:
        cur["bed"] = next(iter(cur["beds"]))
    return cur


def load_settings() -> dict:
    """Stored settings over the defaults; a stored value that fails its check is ignored."""
    out = json.loads(json.dumps(DEFAULTS))
    p = config_dir() / "settings.json"
    if p.exists():
        try:
            stored = json.loads(p.read_text())
        except (OSError, ValueError):
            stored = {}
        if isinstance(stored, dict):
            for k, check in CHECKS.items():
                if k in stored and check(stored[k]) is None:
                    out[k] = stored[k]
    return _settled(out)


def save_settings(values: dict) -> dict:
    """Merge the known keys of `values` into the stored settings (ValueError if one is bad)."""
    cur = load_settings()
    for k, check in CHECKS.items():
        if k in values:
            why = check(values[k])
            if why:
                raise ValueError(why)
            cur[k] = values[k]
    _settled(cur)
    config_dir().mkdir(parents=True, exist_ok=True)
    (config_dir() / "settings.json").write_text(json.dumps(cur, indent=1))
    return cur


def roots(settings: dict | None = None) -> list[Path]:
    s = settings or load_settings()
    out = []
    for r in s["roots"]:
        try:
            out.append(Path(r).expanduser().resolve())
        except (OSError, RuntimeError):
            continue  # an unexpandable ~user or a link loop: skip that root
    return out


def allowed(path: str, settings: dict | None = None) -> Path:
    """The resolved path if it is an .stl inside a root, else ValueError."""
    p = Path(path).expanduser().resolve()
    if p.suffix.lower() != ".stl" or not p.is_file():
        raise ValueError("not an STL file")
    for r in roots(settings):
        if p.is_relative_to(r):
            return p
    raise ValueError("outside the PrintForge folders")


def scale_of(path: Path) -> str | None:
    """A print scale written in the folder names, such as 1-35 or 1_35 -> '1:35'."""
    for part in reversed(path.parts[:-1]):
        m = re.fullmatch(r"1[-_:](\d{1,4})", part)
        if m:
            return f"1:{m.group(1)}"
    return None


def scan(settings: dict | None = None) -> list[dict]:
    """Every STL under the roots, grouped by project (first folder under the root)."""
    out = []
    seen = set()
    for root in roots(settings):
        if not root.is_dir():
            continue
        base_depth = len(root.parts)
        for dirpath, dirnames, filenames in os.walk(root):
            d = Path(dirpath)
            dirnames[:] = [
                n
                for n in dirnames
                if not n.startswith(".")
                and n not in SKIP_DIRS
                and len(d.parts) - base_depth < MAX_DEPTH
            ]
            for name in filenames:
                if not name.lower().endswith(".stl"):
                    continue
                # a link out of the root, a broken link, a FIFO or a file
                # gone mid-scan skips that one entry, not the whole library
                try:
                    p = (d / name).resolve()
                    if p in seen or not p.is_file():
                        continue
                    rel = p.relative_to(root)
                    st = p.stat()
                except (OSError, RuntimeError, ValueError):
                    continue
                seen.add(p)
                out.append(
                    {
                        "path": str(p),
                        "name": p.stem,
                        "project": rel.parts[0] if len(rel.parts) > 1 else root.name,
                        "folder": (
                            str(Path(*rel.parts[1:-1])) if len(rel.parts) > 2 else ""
                        ),
                        "root": str(root),
                        "bytes": st.st_size,
                        "mtime": int(st.st_mtime),
                        "triangles": stl.triangle_count(p),
                        "scale": scale_of(p),
                    }
                )
    out.sort(key=lambda f: (f["project"].lower(), f["folder"], f["name"].lower()))
    return out


def _cache() -> dict:
    p = cache_dir() / "info.json"
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return {}


def info(path: Path) -> dict:
    """Cached analysis of one STL; recomputed when its size or time changes."""
    st = path.stat()
    stamp = [st.st_size, int(st.st_mtime)]
    cache = _cache()
    hit = cache.get(str(path))
    if hit and hit.get("stamp") == stamp:
        return hit["info"]
    result = stl.analyse(stl.read_triangles(path))
    cache[str(path)] = {"stamp": stamp, "info": result}
    cache_dir().mkdir(parents=True, exist_ok=True)
    tmp = cache_dir() / "info.json.tmp"
    tmp.write_text(json.dumps(cache))
    tmp.replace(cache_dir() / "info.json")
    return result
