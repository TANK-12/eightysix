"""Everything render reads about a chapter, with graceful fallbacks.

Inputs come from other areas and may not exist yet:
- panels.json, bubbles.json, strip.json (detect)
- scene.json, cast.json (scene)
- script.json (audio)

When panels.json is missing, a crude fixture cutter splits the stacked pages
at blank gutter rows and caches the result in work/render/fixture_panels.json.
It is only a stand-in so render can be built and checked before detect lands.
"""

import hashlib
import json
from collections import OrderedDict
from pathlib import Path

import cv2
import numpy as np

from .. import store
from ..camera import Character, Line, PanelInfo


class ChapterInputs:
    def __init__(self, chapter_dir: Path):
        self.dir = Path(chapter_dir)
        self._pages: OrderedDict[int, np.ndarray] = OrderedDict()
        self._panel_imgs: OrderedDict[str, np.ndarray] = OrderedDict()
        self.chapter = store.read(self.dir / "chapter.json", {}) or {}
        self.reading = self.chapter.get("reading", "ttb")
        self.strip = store.read(self.dir / "strip.json") or self._strip_from_pages()
        panels_doc = store.read(self.dir / "panels.json")
        self.panel_source = "panels.json"
        if not panels_doc or not panels_doc.get("panels"):
            panels_doc = self._fixture_panels()
            self.panel_source = "fixture"
        self.panels = sorted(
            panels_doc.get("panels", []), key=lambda p: p.get("order", 0)
        )
        self.by_id = {p["id"]: p for p in self.panels}
        bubbles = (store.read(self.dir / "bubbles.json") or {}).get("bubbles", [])
        self.bubbles: dict[str, list[dict]] = {}
        for b in sorted(bubbles, key=lambda b: b.get("order", 0)):
            self.bubbles.setdefault(b.get("panel_id"), []).append(b)
        self.scene = store.read(self.dir / "scene.json") or {}
        script = store.read(self.dir / "script.json") or {}
        self.lines = {ln["id"]: ln for ln in script.get("lines", [])}
        self.line_by_bubble = {
            ln.get("bubble_id"): ln for ln in script.get("lines", [])
        }
        self.script = script
        series_dir = self.dir.parent.parent
        self.cast = store.read(series_dir / "cast.json") or {}

    # ------------------------------------------------------------ strip

    def _strip_from_pages(self) -> dict:
        y, segs, width = 0, [], 0
        for pg in self.chapter.get("pages", []):
            segs.append({"page_idx": pg["idx"], "strip_y": y, "h": pg["h"]})
            y += pg["h"]
            width = max(width, pg.get("w", 0))
        return {"schema": 1, "width": width, "height": y, "segments": segs}

    def _page(self, idx: int) -> np.ndarray:
        if idx in self._pages:
            self._pages.move_to_end(idx)
            return self._pages[idx]
        pg = next(p for p in self.chapter["pages"] if p["idx"] == idx)
        img = cv2.imread(str(self.dir / pg["file"]), cv2.IMREAD_COLOR)
        if img is None:
            img = np.full((pg["h"], pg["w"], 3), 255, np.uint8)
        self._pages[idx] = img
        while len(self._pages) > 8:
            self._pages.popitem(last=False)
        return img

    def crop_strip(self, box) -> np.ndarray:
        """BGR crop of the stacked strip, reading only the pages it overlaps."""
        x, y, w, h = [int(round(v)) for v in box]
        width = self.strip.get("width") or 800
        out = np.full((max(1, h), max(1, w), 3), 255, np.uint8)
        for seg in self.strip.get("segments", []):
            sy, sh = seg["strip_y"], seg["h"]
            top, bot = max(y, sy), min(y + h, sy + sh)
            if top >= bot:
                continue
            page = self._page(seg["page_idx"])
            if page.shape[1] != width:
                page = cv2.resize(
                    page, (width, int(page.shape[0] * width / page.shape[1]))
                )
            part = page[top - sy : bot - sy, max(0, x) : x + w]
            out[
                top - y : top - y + part.shape[0],
                max(0, -x) : max(0, -x) + part.shape[1],
            ] = part
        return out

    # ------------------------------------------------------------ panels

    def _fixture_panels(self) -> dict:
        pages = self.chapter.get("pages", [])
        if not pages:
            return {"schema": 1, "panels": []}
        key = hashlib.sha1(
            json.dumps([(p.get("file"), p.get("sha1")) for p in pages]).encode()
        ).hexdigest()[:12]
        cache = self.dir / "work" / "render" / "fixture_panels.json"
        doc = store.read(cache)
        if doc and doc.get("key") == key:
            return doc
        panels = cut_fixture_panels(self)
        doc = {
            "schema": 1,
            "key": key,
            "source": "render fixture cutter",
            "panels": panels,
        }
        store.write(cache, doc)
        return doc

    def panel_image(self, pid: str) -> np.ndarray:
        """BGRA image of a panel (the detect crop when present, else from the strip)."""
        if pid in self._panel_imgs:
            self._panel_imgs.move_to_end(pid)
            return self._panel_imgs[pid]
        p = self.by_id[pid]
        img = None
        if p.get("image"):
            f = self.dir / p["image"]
            if f.exists():
                img = cv2.imread(str(f), cv2.IMREAD_UNCHANGED)
        if img is None:
            img = self.crop_strip(p["box"])
        if img.ndim == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
        elif img.shape[2] == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
        self._panel_imgs[pid] = img
        while len(self._panel_imgs) > 24:
            self._panel_imgs.popitem(last=False)
        return img

    def scene_panel(self, pid: str) -> dict:
        return (self.scene.get("panels") or {}).get(pid) or {}

    def panel_bubbles(self, pid: str) -> list[dict]:
        return self.bubbles.get(pid, [])

    def local_box(self, pid: str, box) -> list[float]:
        """Strip coordinates to panel coordinates."""
        px, py = self.by_id[pid]["box"][:2]
        return [box[0] - px, box[1] - py, box[2], box[3]]

    def panel_info(self, pid: str) -> PanelInfo:
        p = self.by_id[pid]
        w, h = int(p["box"][2]), int(p["box"][3])
        sc = self.scene_panel(pid)
        lines = []
        bubbles = self.panel_bubbles(pid)
        for b in bubbles:
            if b.get("kind") == "sfx":
                continue
            ln = self.line_by_bubble.get(b["id"]) or {}
            tail = b.get("tail")
            lines.append(
                Line(
                    line_id=ln.get("id") or f"b:{b['id']}",
                    bubble_id=b["id"],
                    box=self.local_box(pid, b["box"]),
                    text=ln.get("text") or b.get("text") or "",
                    kind=ln.get("kind") or b.get("kind") or "speech",
                    speaker=ln.get("speaker") or b.get("speaker"),
                    dur=ln.get("dur"),
                    pause_after=float(
                        (ln.get("emotion") or {}).get("pause_after", 0.25)
                    ),
                    tail=(
                        [tail[0] - p["box"][0], tail[1] - p["box"][1]] if tail else None
                    ),
                )
            )
        chars = [
            Character(
                box=list(c.get("box") or [0, 0, w, h]),
                face=c.get("face"),
                facing=c.get("facing"),
                cast_id=c.get("cast_id") or c.get("extra_id"),
            )
            for c in sc.get("characters", [])
        ]
        return PanelInfo(
            id=pid,
            w=w,
            h=h,
            kind=p.get("kind", "panel"),
            lines=lines,
            characters=chars,
            saliency=[list(s) for s in sc.get("saliency", [])],
            mood=sc.get("mood"),
            action=float(sc.get("action") or 0.0),
            scene_id=sc.get("scene_id"),
            location=sc.get("location"),
            # drawn lettering of any kind: balloons, captions, and the
            # sound words the scene analysis found (never mirrored, never
            # morphed through)
            has_text=bool(bubbles) or bool(sc.get("sfx_text")),
        )

    def stamp(self) -> str:
        """Changes whenever an input file render depends on changes."""
        parts = []
        for name in (
            "panels.json",
            "bubbles.json",
            "scene.json",
            "script.json",
            "strip.json",
        ):
            f = self.dir / name
            parts.append(f"{name}:{f.stat().st_mtime_ns if f.exists() else 0}")
        parts.append(self.panel_source)
        return hashlib.sha1("|".join(parts).encode()).hexdigest()[:12]


def cut_fixture_panels(inp: ChapterInputs, min_h=90, gutter=14) -> list[dict]:
    """Split the strip at runs of flat (white or black) rows. Crude on purpose."""
    width = inp.strip.get("width") or 800
    flat_rows: list[bool] = []
    for seg in inp.strip["segments"]:
        img = cv2.cvtColor(inp._page(seg["page_idx"]), cv2.COLOR_BGR2GRAY)
        img = cv2.resize(img, (200, seg["h"]), interpolation=cv2.INTER_AREA)
        std = img.std(axis=1)
        mean = img.mean(axis=1)
        flat_rows.extend(((std < 3.0) & ((mean > 225) | (mean < 30))).tolist())
    flat = np.array(flat_rows, bool)
    panels, y, n = [], 0, len(flat)
    while y < n:
        if flat[y]:
            y += 1
            continue
        start = y
        while y < n:
            if flat[y]:
                run = y
                while run < n and flat[run]:
                    run += 1
                if run - y >= gutter or run >= n:
                    break
                y = run
            else:
                y += 1
        if y - start >= min_h:
            panels.append([start, y])
    out = []
    for i, (a, b) in enumerate(panels, 1):
        out.append(
            {
                "id": f"p{i:04d}",
                "order": i,
                "box": [0, int(a), int(width), int(b - a)],
                "kind": "panel",
                "shape": "rect",
                "polygon": None,
                "image": None,
                "edited": False,
            }
        )
    return out
