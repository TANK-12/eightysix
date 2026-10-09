"""User music library: ~/PanelForgeData/library/music/*.{wav,ogg,mp3,...}.
Same decode-and-cache approach as panelforge/sfx/library.py."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .. import paths
from ..audio import dsp

EXTS = (".wav", ".ogg", ".mp3", ".flac", ".m4a")


def list_library() -> list[dict]:
    root = paths.LIBRARY_ROOT / "music"
    if not root.exists():
        return []
    return sorted(
        (
            {"id": p.stem, "file": str(p.relative_to(paths.DATA_ROOT))}
            for p in root.iterdir()
            if p.suffix.lower() in EXTS and not p.name.endswith(".48k.wav")
        ),
        key=lambda d: d["id"],
    )


def load(name: str):
    root = paths.LIBRARY_ROOT / "music"
    src = next(
        (
            p
            for p in root.glob(f"{name}.*")
            if p.suffix.lower() in EXTS and not p.name.endswith(".48k.wav")
        ),
        None,
    )
    if src is None:
        raise FileNotFoundError(f"no library track named {name!r} in {root}")
    cached = src.with_suffix(".48k.wav")
    if not cached.exists() or cached.stat().st_mtime < src.stat().st_mtime:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(src),
                "-ar",
                str(dsp.SR),
                "-ac",
                "2",
                str(cached),
            ],
            check=True,
            capture_output=True,
        )
    return dsp.read_wav(cached)
