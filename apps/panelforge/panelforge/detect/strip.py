"""The virtual strip: every page stacked top to bottom in reading order.

The strip is never materialised as one image (166 pages would be a
800 x 212000 array). StripReader loads only the pages a row range touches
and keeps a few decoded pages in a small cache.
"""

from collections import OrderedDict
from pathlib import Path

import cv2
import numpy as np

from .. import store


def build_strip(chapter_dir: Path) -> dict:
    """strip.json content from chapter.json. Pages of another width are scaled to the strip width."""
    chapter = store.read(chapter_dir / "chapter.json")
    if not chapter or not chapter.get("pages"):
        raise ValueError(f"no pages listed in {chapter_dir / 'chapter.json'}")
    pages = chapter["pages"]
    width = max(int(p["w"]) for p in pages)
    segments = []
    y = 0
    for p in pages:
        h = round(int(p["h"]) * width / int(p["w"]))
        segments.append({"page_idx": p["idx"], "strip_y": y, "h": h, "file": p["file"]})
        y += h
    return {"schema": 1, "width": width, "height": y, "segments": segments}


class StripReader:
    """Read rows [y0, y1) of the virtual strip as a BGR uint8 array."""

    def __init__(self, chapter_dir: Path, strip: dict, cache_pages: int = 8):
        self.dir = chapter_dir
        self.strip = strip
        self.width = int(strip["width"])
        self.height = int(strip["height"])
        self._starts = np.array([s["strip_y"] for s in strip["segments"]])
        self._cache: OrderedDict[int, np.ndarray] = OrderedDict()
        self._cache_pages = cache_pages

    def page(self, i: int) -> np.ndarray:
        if i in self._cache:
            self._cache.move_to_end(i)
            return self._cache[i]
        seg = self.strip["segments"][i]
        img = cv2.imread(str(self.dir / seg["file"]), cv2.IMREAD_COLOR)
        if img is None:
            raise OSError(f"cannot decode {seg['file']}")
        if img.shape[1] != self.width or img.shape[0] != seg["h"]:
            img = cv2.resize(img, (self.width, seg["h"]), interpolation=cv2.INTER_AREA)
        self._cache[i] = img
        while len(self._cache) > self._cache_pages:
            self._cache.popitem(last=False)
        return img

    def rows(self, y0: int, y1: int) -> np.ndarray:
        y0, y1 = max(0, int(y0)), min(self.height, int(y1))
        out = np.empty((max(0, y1 - y0), self.width, 3), np.uint8)
        if y1 <= y0:
            return out
        i = int(np.searchsorted(self._starts, y0, side="right")) - 1
        y = y0
        while y < y1:
            seg = self.strip["segments"][i]
            top = seg["strip_y"]
            a, b = y - top, min(seg["h"], y1 - top)
            out[y - y0 : y - y0 + (b - a)] = self.page(i)[a:b]
            y += b - a
            i += 1
        return out

    def crop(self, box: list[int]) -> np.ndarray:
        x, y, w, h = box
        return self.rows(y, y + h)[:, x : x + w]
