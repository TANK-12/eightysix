"""Bridge to MediaForge's Manga Downloader output.

MediaForge writes each series under `<out_dir>/<title>/`, with one raw page
folder per chapter plus, depending on its export options, a compiled
`<chapter>.pdf` and/or `<chapter>.cbz` at the series root. This module lists
that tree for the "browse MediaForge downloads" picker and imports a chosen
chapter folder/CBZ/PDF straight through the same `library.importers` code
path used for a manual import, so it gets the same verification and
`chapter.json`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from . import importers

DEFAULT_ROOT = Path.home() / "Downloads" / "MediaForge"


def _guess_number(name: str, fallback: int) -> float:
    import re

    m = re.search(r"(\d+(?:\.\d+)?)", name)
    return float(m.group(1)) if m else fallback


def list_downloads(root: Optional[str] = None) -> dict:
    base = Path(root).expanduser() if root else DEFAULT_ROOT
    if not base.is_dir():
        return {"root": str(base), "exists": False, "series": []}
    series = []
    for sdir in sorted(p for p in base.iterdir() if p.is_dir()):
        chapters = []
        for item in sorted(sdir.iterdir()):
            if item.is_dir():
                n_imgs = sum(
                    1 for f in item.iterdir() if f.suffix.lower() in importers.IMAGE_EXT
                )
                if n_imgs:
                    chapters.append(
                        {
                            "name": item.name,
                            "path": str(item),
                            "kind": "folder",
                            "count": n_imgs,
                        }
                    )
            elif item.suffix.lower() in (".pdf", ".cbz"):
                chapters.append(
                    {
                        "name": item.name,
                        "path": str(item),
                        "kind": item.suffix.lstrip("."),
                    }
                )
        if chapters:
            series.append({"title": sdir.name, "path": str(sdir), "chapters": chapters})
    return {"root": str(base), "exists": True, "series": series}


def import_from_mediaforge(
    path: str, series: Optional[str], number: Optional[float], job
) -> dict:
    p = Path(path).expanduser()
    if not p.exists():
        raise ValueError(f"no such MediaForge path: {path}")
    if number is None:
        number = _guess_number(p.stem, 1)
    if series is None:
        # series root is the download's parent folder for a chapter subfolder,
        # or the file's own parent for a compiled pdf/cbz.
        parent = p.parent if p.is_dir() else p.parent
        from .. import paths

        series = paths.slug(parent.name)
    job.log(f"importing from MediaForge downloads: {path}")
    return importers.import_path(str(p), series, number, job)
