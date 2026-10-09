"""User SFX library: ~/PanelForgeData/library/sfx/*.{wav,ogg,mp3}. Any format
ffmpeg reads is decoded to 48 kHz stereo wav on first use and cached
alongside the source file (<name>.48k.wav), so repeated placements don't
re-run ffmpeg."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .. import paths
from ..audio import dsp

EXTS = (".wav", ".ogg", ".mp3", ".flac", ".m4a")


def list_library() -> list[dict]:
    root = paths.LIBRARY_ROOT / "sfx"
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
    """Returns (stereo float32 samples, sr) for a library item by stem name."""
    root = paths.LIBRARY_ROOT / "sfx"
    src = next(
        (
            p
            for p in root.glob(f"{name}.*")
            if p.suffix.lower() in EXTS and not p.name.endswith(".48k.wav")
        ),
        None,
    )
    if src is None:
        raise FileNotFoundError(f"no library sfx named {name!r} in {root}")
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
