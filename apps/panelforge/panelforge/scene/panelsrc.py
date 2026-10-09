"""Panel images and bubbles for scene, read from detect's output.

detect may be re-running while scene works, so panel pixels are cut straight
from the pages through strip.json instead of relying on detect's cached PNGs.
Without strip.json the strip is rebuilt from chapter.json the same way
(pages stacked, scaled to the widest page).
"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

import cv2
import numpy as np

from .. import store


def strip_for(chapter_dir: Path) -> dict:
    strip = store.read(chapter_dir / "strip.json")
    if strip and strip.get("segments"):
        return strip
    chapter = store.read(chapter_dir / "chapter.json") or {}
    pages = chapter.get("pages") or []
    if not pages:
        raise FileNotFoundError(f"no pages in {chapter_dir / 'chapter.json'}")
    width = max(int(p["w"]) for p in pages)
    y = 0
    segs = []
    for p in pages:
        h = round(int(p["h"]) * width / int(p["w"]))
        segs.append({"page_idx": p["idx"], "strip_y": y, "h": h, "file": p["file"]})
        y += h
    return {"schema": 1, "width": width, "height": y, "segments": segs}


class Strip:
    def __init__(self, chapter_dir: Path, strip: dict | None = None, cache: int = 6):
        self.dir = chapter_dir
        self.strip = strip or strip_for(chapter_dir)
        self.width = int(self.strip["width"])
        self._pages: OrderedDict[int, np.ndarray] = OrderedDict()
        self._cache = cache
        files = {}
        chapter = store.read(chapter_dir / "chapter.json") or {}
        for p in chapter.get("pages") or []:
            files[p["idx"]] = p["file"]
        self._files = files

    def _page(self, i: int) -> np.ndarray:
        if i in self._pages:
            self._pages.move_to_end(i)
            return self._pages[i]
        seg = self.strip["segments"][i]
        name = seg.get("file") or self._files.get(seg["page_idx"])
        img = cv2.imread(str(self.dir / str(name)), cv2.IMREAD_COLOR)
        if img is None:
            raise OSError(f"cannot decode page {name}")
        if img.shape[1] != self.width or img.shape[0] != seg["h"]:
            img = cv2.resize(
                img, (self.width, int(seg["h"])), interpolation=cv2.INTER_AREA
            )
        self._pages[i] = img
        while len(self._pages) > self._cache:
            self._pages.popitem(last=False)
        return img

    def crop(self, box: list[int]) -> np.ndarray:
        x, y, w, h = [int(v) for v in box]
        out = np.zeros((h, w, 3), np.uint8)
        for i, seg in enumerate(self.strip["segments"]):
            s0, s1 = int(seg["strip_y"]), int(seg["strip_y"]) + int(seg["h"])
            a, b = max(y, s0), min(y + h, s1)
            if a >= b:
                continue
            page = self._page(i)
            out[a - y : b - y] = page[a - s0 : b - s0, x : x + w]
        return out


def load(chapter_dir: Path) -> tuple[list[dict], list[dict]]:
    """(panels, bubbles) in reading order; empty lists when detect has not run."""
    panels = (store.read(chapter_dir / "panels.json") or {}).get("panels") or []
    bubbles = (store.read(chapter_dir / "bubbles.json") or {}).get("bubbles") or []
    panels = sorted(panels, key=lambda p: (p.get("order", 0), p["id"]))
    return panels, bubbles


def bubbles_by_panel(bubbles: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for b in bubbles:
        out.setdefault(b.get("panel_id") or "", []).append(b)
    return out
