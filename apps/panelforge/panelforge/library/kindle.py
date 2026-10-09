"""Export a chapter, a list of chapters or a whole series as one PDF.

Preset ``full``: pages go into the PDF unchanged, one PDF page per image.
Preset ``kindle``: a tall webtoon strip page is cut into Paperwhite-ish
pieces. The cut lands on a blank (low row-variance) gutter row nearest the
target height when one exists nearby, so it doesn't slice through art; if no
blank row is found nearby it falls back to a hard cut at the target height.

Chapter bookmarks are written via PyMuPDF's table of contents
(``doc.set_toc``), one entry per chapter at its first PDF page.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Optional

import pymupdf as fitz
import numpy as np
from PIL import Image

from .. import paths, store

# Kindle Paperwhite-ish page proportions (not the exact pixel count -- the
# reader rescales anyway -- just the aspect ratio so slices read as pages).
KINDLE_ASPECT = 1072 / 1448  # width / height ~= 0.740
GUTTER_SEARCH_FRAC = 0.15  # look this far above/below the target cut for a blank row
GUTTER_STDDEV_MAX = 6.0  # a row this uniform counts as "blank"


def find_cuts(height: int, width: int, row_stddev: np.ndarray) -> list[int]:
    """Row indices (0 < y < height) to cut a strip of this size at, closest
    to an even Kindle-aspect slice height, snapped to a nearby blank row."""
    target_h = max(1, round(width / KINDLE_ASPECT))
    if height <= target_h:
        return []
    cuts = []
    y = target_h
    while y < height - target_h * 0.3:
        window = max(1, round(target_h * GUTTER_SEARCH_FRAC))
        lo, hi = max(1, y - window), min(height - 1, y + window)
        seg = row_stddev[lo:hi]
        best_y = y
        if len(seg):
            local_min = int(np.argmin(seg))
            if seg[local_min] <= GUTTER_STDDEV_MAX:
                best_y = lo + local_min
        cuts.append(best_y)
        y = best_y + target_h
    return cuts


def _row_stddev(im: Image.Image) -> np.ndarray:
    arr = np.asarray(im.convert("L"), dtype=np.float32)
    return arr.std(axis=1)


def split_kindle(data: bytes) -> list[bytes]:
    """One webtoon page -> a list of PNG-encoded page-sized slices."""
    im = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = im.size
    stddev = _row_stddev(im)
    cuts = find_cuts(h, w, stddev)
    bounds = [0] + cuts + [h]
    out = []
    for top, bottom in zip(bounds, bounds[1:]):
        if bottom <= top:
            continue
        piece = im.crop((0, top, w, bottom))
        buf = io.BytesIO()
        piece.save(buf, format="PNG")
        out.append(buf.getvalue())
    return out or [data]


def _chapter_page_files(series: str, chapter: str) -> list[Path]:
    cdir = paths.chapter_dir(series, chapter)
    doc = store.read(cdir / "chapter.json", {})
    pages = sorted(doc.get("pages", []), key=lambda p: p["idx"])
    return [cdir / p["file"] for p in pages]


def _chapter_title(series: str, chapter: str) -> str:
    doc = store.read(paths.chapter_dir(series, chapter) / "chapter.json", {})
    return doc.get("title") or f"Chapter {chapter}"


def export_pdf(
    series: str, chapters: list[str], preset: str, out_path: Path, job=None
) -> Path:
    if preset not in ("kindle", "full"):
        raise ValueError(f"unknown preset: {preset}")
    pdf = fitz.open()
    toc = []
    for chapter in chapters:
        if job:
            job.log(f"kindle export: chapter {chapter} ({preset})")
        first_pdf_page = pdf.page_count
        for img_path in _chapter_page_files(series, chapter):
            data = img_path.read_bytes()
            pieces = split_kindle(data) if preset == "kindle" else [data]
            for piece in pieces:
                im = Image.open(io.BytesIO(piece))
                w, h = im.size
                page = pdf.new_page(width=w, height=h)
                page.insert_image(fitz.Rect(0, 0, w, h), stream=piece)
        toc.append([1, _chapter_title(series, chapter), first_pdf_page + 1])
    if toc:
        pdf.set_toc(toc)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.save(str(out_path))
    pdf.close()
    return out_path


def resolve_chapters(series: str, chapters: "list | str") -> list[str]:
    sdir = paths.series_dir(series) / "chapters"
    all_chapters = sorted(p.name for p in sdir.iterdir()) if sdir.is_dir() else []
    if chapters == "all":
        return all_chapters
    out = []
    for c in chapters:
        slug = c if isinstance(c, str) else paths.chapter_slug(float(c))
        if slug in all_chapters:
            out.append(slug)
    return out
