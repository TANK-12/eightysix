"""Cut the virtual strip into panels.

1. Row statistics per page at 1/SCALE size give seed rows (flat gutter rows).
2. Long seed runs split the strip into sections; each section is read,
   downscaled and turned into a gutter mask (gutters.gutter_mask).
3. Content = not gutter. A small morphological close joins fragments of one
   drawing (dark art touching a black gutter breaks into pieces otherwise).
4. Content groups are classed as art or as loose items (balloons, captions,
   sound words sitting in the gutter). Items near art are attached to it;
   items far from any art become caption-only panels.
5. Merged neighbours that are really two slanted panels are split along the
   straightest gutter line (gutters.best_slanted_cut).
6. Reading order: top to bottom, left to right inside a row (right to left
   for manga reading order).
"""

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from . import gutters as G
from .strip import StripReader

SCALE = 4


@dataclass
class Region:
    x: int  # overview (1/SCALE) coordinates while detecting
    y: int
    w: int
    h: int
    area: int
    art: bool
    mask: np.ndarray  # bool, h x w
    items: list["Region"] = field(default_factory=list)
    kind: str = "panel"

    @property
    def x1(self) -> int:
        return self.x + self.w

    @property
    def y1(self) -> int:
        return self.y + self.h


def page_row_stats(reader: StripReader, scale: int = SCALE, progress=None):
    """Median colour and flatness for every overview row, one page at a time."""
    w = reader.width // scale
    meds, flats = [], []
    segs = reader.strip["segments"]
    for i, seg in enumerate(segs):
        im = cv2.resize(
            reader.page(i), (w, max(1, seg["h"] // scale)), interpolation=cv2.INTER_AREA
        )
        m, f = G.row_stats(im)
        meds.append(m)
        flats.append(f)
        if progress:
            progress((i + 1) / len(segs))
    return np.concatenate(meds), np.concatenate(flats)


def sections(seed: np.ndarray, min_gap: int, pad: int = 3) -> list[tuple[int, int]]:
    """Row ranges of content between long seed runs, padded with a few seed rows."""
    out = []
    n = len(seed)
    for a, b in G.cut_rows(seed, min_gap):
        out.append((max(0, a - pad), min(n, b + pad)))
    return out


def textish_share(img: np.ndarray, mask: np.ndarray) -> float:
    """Share of masked pixels that are near-white or near-black and unsaturated.

    Balloons and caption boxes are two-tone; drawn art is not.
    """
    if not mask.any():
        return 1.0
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    s, v = hsv[..., 1][mask], hsv[..., 2][mask]
    two_tone = ((v >= 185) & (s <= 60)) | (v <= 70)
    return float(two_tone.mean())


LOOSE_TOL = 30


def background_like(
    img: np.ndarray, gut: np.ndarray, tol: int = LOOSE_TOL
) -> np.ndarray:
    """Pixels that could be background: the gutter itself, or close to a gutter colour.

    Used only to look for cut lines inside merged regions, where dark art
    fading into a black gutter is not connected to any flat row.
    """
    med, flat = G.row_stats(img, G.TOL)
    seed = G.seed_rows(flat, 2)
    out = gut.copy()
    im = img.astype(np.int16)
    if seed.any():
        field = G.color_field(med, seed)
        out |= np.abs(im - field[:, None, :]).max(axis=2) <= tol
    for ref in ((0, 0, 0), (255, 255, 255)):
        out |= np.abs(im - np.array(ref, np.int16)).max(axis=2) <= tol
    return out


def split_region(
    r: Region, img: np.ndarray, bg: np.ndarray, width_ov: int, depth: int = 0
) -> list[Region]:
    """Recursively cut a merged art region along straight background lines.

    bg is the background-like mask of the whole section (section coordinates).
    Inside the region's box, anything outside the region's own mask also counts
    as background.
    """
    if depth > 12 or r.h < 0.5 * width_ov:
        return [r]
    sub = bg[r.y : r.y1, r.x : r.x1] | ~r.mask
    # a cut must leave a real panel on both sides
    margin = int(0.18 * width_ov)
    cut = G.best_slanted_cut(sub, min_share=0.88, max_slope=0.45, margin=margin)
    if cut is None:
        return [r]
    yl, yr, _share = cut
    ys, xs = np.mgrid[0 : r.h, 0 : r.w]
    line_y = yl + (yr - yl) * xs / max(1, r.w - 1)
    parts = []
    ink = r.mask & ~bg[r.y : r.y1, r.x : r.x1]
    for side in (ys < line_y, ys >= line_y):
        m = r.mask & side
        # both sides need real drawing, not a near-black sliver or a balloon
        if (ink & side).sum() < 0.05 * width_ov * width_ov:
            return [r]
        yy, xx = np.nonzero(m)
        x0, y0, x1, y1 = xx.min(), yy.min(), xx.max() + 1, yy.max() + 1
        if y1 - y0 < 0.25 * width_ov:
            return [r]
        crop = img[r.y + y0 : r.y + y1, r.x + x0 : r.x + x1]
        if textish_share(crop, m[y0:y1, x0:x1]) >= 0.8:
            return [r]
        parts.append(
            Region(
                r.x + int(x0),
                r.y + int(y0),
                int(x1 - x0),
                int(y1 - y0),
                int(m.sum()),
                True,
                m[y0:y1, x0:x1],
            )
        )
    out = []
    for p in parts:
        out.extend(split_region(p, img, bg, width_ov, depth + 1))
    return out


def regions_in_section(img: np.ndarray, width_ov: int) -> list[Region]:
    """Content groups of one downscaled section (coordinates relative to the section)."""
    gut, _seed = G.gutter_mask(img)
    bg = background_like(img, gut)
    content = (~gut).astype(np.uint8)
    # drop specks and 1px speed lines, then join fragments of one drawing
    content = cv2.morphologyEx(content, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    joined = cv2.morphologyEx(
        content, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    )
    n, lab, stats, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
    out = []
    art_area = 0.06 * width_ov * width_ov
    for i in range(1, n):
        x, y, w, h, area = (int(v) for v in stats[i])
        if area < 12:
            continue
        m = (lab[y : y + h, x : x + w] == i) & (content[y : y + h, x : x + w] > 0)
        tt = textish_share(img[y : y + h, x : x + w], m)
        fill = m.sum() / max(1, w * h)
        lettering = fill < 0.45 and h <= 0.5 * width_ov  # colored caption text
        art = (
            area >= art_area
            and tt < 0.8
            and not lettering
            and min(w, h) >= 0.12 * width_ov
        )
        reg = Region(x, y, w, h, int(m.sum()), art, m)
        out.extend(split_region(reg, img, bg, width_ov) if art else [reg])
    return out


def _gap(a: Region, b: Region) -> float:
    dx = max(0, max(a.x, b.x) - min(a.x1, b.x1))
    dy = max(0, max(a.y, b.y) - min(a.y1, b.y1))
    return float(np.hypot(dx, dy))


def _union(regions: list[Region]) -> tuple[int, int, int, int]:
    x0 = min(r.x for r in regions)
    y0 = min(r.y for r in regions)
    x1 = max(r.x1 for r in regions)
    y1 = max(r.y1 for r in regions)
    return x0, y0, x1 - x0, y1 - y0


def group_regions(regs: list[Region], width_ov: int) -> list[Region]:
    """Attach loose items to nearby art; cluster the rest into caption-only panels."""
    arts = [r for r in regs if r.art]
    loose = [r for r in regs if not r.art]
    attach_dist = 0.2 * width_ov
    orphans = []
    for it in loose:
        best = min(arts, key=lambda a: _gap(a, it), default=None)
        if best is not None and _gap(best, it) <= attach_dist:
            best.items.append(it)
        else:
            orphans.append(it)
    # cluster orphans that sit close together
    orphans.sort(key=lambda r: r.y)
    clusters: list[list[Region]] = []
    for it in orphans:
        for c in clusters:
            if any(_gap(o, it) <= 0.12 * width_ov for o in c):
                c.append(it)
                break
        else:
            clusters.append([it])
    out = list(arts)
    for c in clusters:
        if sum(r.area for r in c) < 0.004 * width_ov * width_ov:
            continue  # stray specks
        x, y, w, h = _union(c)
        mask = np.zeros((h, w), bool)
        for r in c:
            mask[r.y - y : r.y1 - y, r.x - x : r.x1 - x] |= r.mask
        reg = Region(x, y, w, h, int(mask.sum()), False, mask, kind="caption-only")
        out.append(reg)
    return out


def order_boxes(boxes: list[list[int]], reading: str = "ttb") -> list[int]:
    """Indices of boxes in reading order: rows top to bottom, then across each row.

    Two boxes share a row when they overlap vertically by more than half of
    the shorter one. Across a row: left to right, or right to left for "rtl".
    """
    idx = sorted(range(len(boxes)), key=lambda i: (boxes[i][1], boxes[i][0]))
    rows: list[list[int]] = []
    for i in idx:
        x, y, w, h = boxes[i]
        for row in rows:
            j = row[0]
            _, yj, _, hj = boxes[j]
            overlap = min(y + h, yj + hj) - max(y, yj)
            if overlap > 0.5 * min(h, hj):
                row.append(i)
                break
        else:
            rows.append([i])
    out = []
    for row in rows:
        row.sort(key=lambda i: boxes[i][0], reverse=(reading == "rtl"))
        out.extend(row)
    return out


def shape_of(mask: np.ndarray) -> tuple[str, list[list[int]] | None]:
    """rect / slanted / borderless, plus a polygon (mask coordinates) when not a rectangle."""
    h, w = mask.shape
    fill = mask.sum() / max(1, h * w)
    if fill >= 0.9:
        return "rect", None
    cnts, _ = cv2.findContours(
        mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    if not cnts:
        return "rect", None
    pts = np.concatenate(cnts)
    hull = cv2.convexHull(pts)
    solidity = mask.sum() / max(1.0, cv2.contourArea(hull))
    approx = cv2.approxPolyDP(hull, 0.02 * cv2.arcLength(hull, True), True)
    poly = [[int(p[0][0]), int(p[0][1])] for p in approx]
    if len(poly) <= 6 and solidity >= 0.88:
        return "slanted", poly
    return "borderless", poly


def detect_regions(
    reader: StripReader, reading: str = "ttb", progress=None
) -> list[Region]:
    """All panels of the strip as Regions in overview coordinates, in reading order."""
    width_ov = reader.width // SCALE
    _med, flat = page_row_stats(reader, SCALE, lambda f: progress and progress(0.5 * f))
    seed = G.seed_rows(flat, 3)
    secs = sections(seed, min_gap=6)
    regs: list[Region] = []
    for k, (a, b) in enumerate(secs):
        img = reader.rows(a * SCALE, b * SCALE)
        small = cv2.resize(img, (width_ov, b - a), interpolation=cv2.INTER_AREA)
        for r in regions_in_section(small, width_ov):
            r.y += a
            regs.append(r)
        if progress:
            progress(0.5 + 0.5 * (k + 1) / max(1, len(secs)))
    grouped = group_regions(regs, width_ov)
    boxes = [[r.x, r.y, r.w, r.h] for r in grouped]
    return [grouped[i] for i in order_boxes(boxes, reading)]


def to_panel_dicts(regs: list[Region], strip: dict) -> list[dict]:
    """Contract panels (strip coordinates). art_box and items are contract additions."""
    W, H = int(strip["width"]), int(strip["height"])
    out = []

    def full(x, y, w, h):
        x0, y0 = max(0, x * SCALE), max(0, y * SCALE)
        x1, y1 = min(W, (x + w) * SCALE), min(H, (y + h) * SCALE)
        return [x0, y0, x1 - x0, y1 - y0]

    for n, r in enumerate(regs, 1):
        pid = f"p{n:04d}"
        members = [r] + r.items
        ux, uy, uw, uh = _union(members)
        art_box = full(r.x, r.y, r.w, r.h)
        box = full(ux, uy, uw, uh)
        if r.kind == "caption-only":
            kind, shape, poly = "caption-only", "rect", None
        else:
            shape, poly = shape_of(r.mask)
            kind = (
                "splash"
                if r.w >= 0.9 * (W // SCALE) and r.h >= 1.5 * (W // SCALE)
                else "panel"
            )
        polygon = (
            [
                [min(W, (r.x + px) * SCALE), min(H, (r.y + py) * SCALE)]
                for px, py in poly
            ]
            if poly
            else None
        )
        out.append(
            {
                "id": pid,
                "order": n,
                "box": box,
                "kind": kind,
                "shape": shape,
                "polygon": polygon,
                "image": f"work/detect/panels/{pid}.png",
                "edited": False,
                "art_box": art_box,
            }
        )
    return out


GROW_MAX_FRAC = 0.06  # of the panel's own width or height
GROW_MAX_PX = 48


def _sides(box):
    x, y, w, h = box
    return x, y, x + w, y + h


def grow_to_text(
    panels: list[dict],
    bubbles: list[dict],
    strip: dict,
    max_frac: float = GROW_MAX_FRAC,
    max_px: int = GROW_MAX_PX,
) -> list[str]:
    """Widen panel boxes so the lettering drawn on them is not cropped away.

    A balloon or caption often runs a few pixels past the edge the gutter
    finder settled on. Those pixels are lost when the panel is cropped, so the
    camera can never bring them back and the film shows a sliced word. Each
    panel therefore grows to cover the text assigned to it, by at most
    `max_frac` of its own size (and `max_px`), never outside the strip and
    never into a neighbouring panel's box. Returns the ids that changed.
    """
    W, H = int(strip["width"]), int(strip["height"])
    text_of: dict[str, list[list[float]]] = {}
    for b in bubbles:
        pid = b.get("panel_id")
        if pid and b.get("box"):
            text_of.setdefault(pid, []).append(list(b["box"]))
    others = [(p["id"], _sides(p["box"])) for p in panels]
    changed: list[str] = []
    for panel in panels:
        boxes = text_of.get(panel["id"])
        if not boxes or panel.get("edited"):  # never undo a hand edit
            continue
        x0, y0, x1, y1 = _sides(panel["box"])
        w, h = x1 - x0, y1 - y0
        room_x = min(max_px, max_frac * w)
        room_y = min(max_px, max_frac * h)
        nx0 = max(x0 - room_x, min(x0, min(b[0] for b in boxes)))
        ny0 = max(y0 - room_y, min(y0, min(b[1] for b in boxes)))
        nx1 = min(x1 + room_x, max(x1, max(b[0] + b[2] for b in boxes)))
        ny1 = min(y1 + room_y, max(y1, max(b[1] + b[3] for b in boxes)))
        nx0, ny0 = max(0.0, nx0), max(0.0, ny0)
        nx1, ny1 = min(float(W), nx1), min(float(H), ny1)
        for pid, (ox0, oy0, ox1, oy1) in others:
            if pid == panel["id"]:
                continue
            if oy0 < y1 and oy1 > y0:  # shares rows: stop sideways at its edge
                if ox1 <= x0:
                    nx0 = max(nx0, ox1)
                elif ox0 >= x1:
                    nx1 = min(nx1, ox0)
            if ox0 < x1 and ox1 > x0:  # shares columns: stop above and below
                if oy1 <= y0:
                    ny0 = max(ny0, oy1)
                elif oy0 >= y1:
                    ny1 = min(ny1, oy0)
        box = [round(nx0), round(ny0), round(nx1 - nx0), round(ny1 - ny0)]
        if box != [round(v) for v in panel["box"]]:
            panel["box"] = box
            changed.append(panel["id"])
    return changed


def save_crop(reader: StripReader, panel: dict, chapter_dir: Path) -> None:
    dest = chapter_dir / panel["image"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(dest), reader.crop(panel["box"]), [cv2.IMWRITE_PNG_COMPRESSION, 6])
