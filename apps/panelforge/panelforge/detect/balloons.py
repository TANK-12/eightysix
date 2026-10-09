"""The balloon around a text block: its outline, its kind and its tail.

Balloon interior: starting from the text block, flood the pixels that match
the block's background colour. If the flood stays inside a window around the
block, the text sits in a closed balloon or box; if it runs out of the window
the text is written on open background (gutter or drawing).

Kind comes from the outline geometry (classify_shape, pure and testable):
    caption  rectangle-like box
    speech   smooth ellipse-like outline
    thought  cloud: a regular run of round bumps
    shout    jagged spikes, on the outline itself or radiating around it
    whisper  dashed outline
Text with no balloon is a caption when it sits on flat background, and sfx
when it is drawn over art.
"""

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class Balloon:
    mask: np.ndarray  # filled interior, window coordinates
    ox: int  # window origin in the source image
    oy: int
    box: tuple[int, int, int, int]  # source coordinates
    closed: bool


def background_colour(crop: np.ndarray, polarity: str) -> np.ndarray:
    g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    sel = g >= np.percentile(g, 60) if polarity == "dark" else g <= np.percentile(g, 40)
    return (
        np.median(crop[sel], axis=0)
        if sel.any()
        else np.median(crop.reshape(-1, 3), axis=0)
    )


def find_balloon(img: np.ndarray, box, polarity: str, tol: int = 48) -> Balloon:
    """Enclosing balloon of a text block box (x, y, w, h) in img."""
    x, y, w, h = box
    H, W = img.shape[:2]
    pad = int(max(w, h) * 0.9) + 40
    ox, oy = max(0, x - pad), max(0, y - pad)
    x1, y1 = min(W, x + w + pad), min(H, y + h + pad)
    win = img[oy:y1, ox:x1]
    bgc = background_colour(img[y : y + h, x : x + w], polarity)
    sim = np.abs(win.astype(np.int16) - bgc.astype(np.int16)).max(axis=2) <= tol
    # the letters themselves belong to the interior
    bx, by = x - ox, y - oy
    sim[by : by + h, bx : bx + w] = True
    n, lab = cv2.connectedComponents(sim.astype(np.uint8), connectivity=4)
    core = lab[by : by + h, bx : bx + w]
    ids, counts = np.unique(core[core > 0], return_counts=True)
    if len(ids) == 0:
        return Balloon(np.zeros(sim.shape, bool), ox, oy, tuple(box), False)
    interior = lab == ids[np.argmax(counts)]
    wh, ww = interior.shape
    edge = (
        interior[0, :].any()
        and oy > 0
        or interior[-1, :].any()
        and y1 < H
        or interior[:, 0].any()
        and ox > 0
        or interior[:, -1].any()
        and x1 < W
    )
    # touching the page side is fine for boxes cut by the image edge, but a
    # region reaching the window edge in the middle of the strip is open ground
    reach = interior.sum() / max(1, wh * ww)
    closed = not edge and reach < 0.85
    filled = _fill_holes(interior)
    ys, xs = np.nonzero(filled)
    bb = (
        int(xs.min()) + ox,
        int(ys.min()) + oy,
        int(np.ptp(xs)) + 1,
        int(np.ptp(ys)) + 1,
    )
    return Balloon(filled, ox, oy, bb, closed)


def _fill_holes(mask: np.ndarray) -> np.ndarray:
    m = np.pad(mask.astype(np.uint8), 1)
    ff = m.copy()
    cv2.floodFill(ff, None, (0, 0), 1)
    holes = ff == 0
    return (m.astype(bool) | holes)[1:-1, 1:-1]


def _radial_profile(
    img_gray: np.ndarray, mask: np.ndarray, d0: int, d1: int, n: int = 360
):
    """Darkness sampled around the outline: for each angle, min grey between distances d0..d1 outside."""
    ys, xs = np.nonzero(mask)
    cy, cx = ys.mean(), xs.mean()
    dist = cv2.distanceTransform((~mask).astype(np.uint8), cv2.DIST_L2, 3)
    ring = (dist >= d0) & (dist <= d1)
    ry, rx = np.nonzero(ring)
    if len(ry) == 0:
        return np.full(n, 255.0)
    ang = ((np.arctan2(ry - cy, rx - cx) + np.pi) / (2 * np.pi) * n).astype(int) % n
    vals = img_gray[ry, rx].astype(float)
    prof = np.full(n, 255.0)
    np.minimum.at(prof, ang, vals)
    return prof


def _alternations(profile: np.ndarray, thr: float = 110) -> int:
    dark = profile < thr
    return int(np.count_nonzero(dark != np.roll(dark, 1)))


def classify_shape(
    mask: np.ndarray, gray: np.ndarray | None = None
) -> tuple[str, dict]:
    """Kind of a closed balloon from its filled mask (and the surrounding grey image).

    Returns (kind, features). gray, when given, must be aligned with mask and
    is used to see spikes or dashes drawn around the outline.
    """
    m = mask.astype(np.uint8)
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(cnts, key=cv2.contourArea)
    area = cv2.contourArea(c)
    perim = cv2.arcLength(c, True)
    hull = cv2.convexHull(c)
    hull_area = max(1.0, cv2.contourArea(hull))
    hull_perim = max(1.0, cv2.arcLength(hull, True))
    solidity = area / hull_area
    roughness = perim / hull_perim
    rect = cv2.minAreaRect(c)
    rect_fill = area / max(1.0, rect[1][0] * rect[1][1])
    ellipse_fill = 0.0
    if len(c) >= 5:
        (_, _), (ea, eb), _ = cv2.fitEllipse(c)
        ellipse_fill = area / max(1.0, np.pi * ea * eb / 4)
    # bumps: convexity defects deeper than a few pixels, relative to size
    size = np.sqrt(area)
    defects = 0
    hull_idx = cv2.convexHull(c, returnPoints=False)
    if hull_idx is not None and len(hull_idx) > 3:
        try:
            d = cv2.convexityDefects(c, hull_idx)
        except cv2.error:
            d = None
        if d is not None:
            depth = np.asarray(d).reshape(-1, 4)[:, 3] / 256.0
            defects = int(np.count_nonzero(depth > max(2.5, 0.02 * size)))
    feats = {
        "solidity": round(float(solidity), 3),
        "roughness": round(float(roughness), 3),
        "rect_fill": round(float(rect_fill), 3),
        "ellipse_fill": round(float(ellipse_fill), 3),
        "defects": defects,
    }
    spikes = dashes = 0
    if gray is not None:
        outer = _radial_profile(gray, mask, 6, max(10, int(0.12 * size)))
        near = _radial_profile(gray, mask, 1, 4)
        spikes = _alternations(outer)
        dashes = _alternations(near)
        feats["spikes"] = spikes
        feats["dashes"] = dashes
    if defects >= 10 and roughness >= 1.12 and solidity < 0.9:
        return "shout", feats
    if spikes >= 40:
        return "shout", feats
    if rect_fill >= 0.93 and defects <= 2:
        return "caption", feats
    if defects >= 5 and solidity < 0.95:
        return "thought", feats
    if dashes >= 16 and spikes < 16:
        return "whisper", feats
    return "speech", feats


def find_tail(mask: np.ndarray) -> tuple[int, int] | None:
    """Tip of the balloon's tail in mask coordinates, or None when there is no tail.

    The body is what survives a large opening; the tail is the biggest thin
    leftover attached to it, and its tip is the leftover pixel furthest from
    the body centre.
    """
    m = mask.astype(np.uint8)
    ys, xs = np.nonzero(m)
    if len(ys) == 0:
        return None
    r = int(max(3, 0.18 * min(np.ptp(ys) + 1, np.ptp(xs) + 1)))
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    body = cv2.morphologyEx(m, cv2.MORPH_OPEN, k)
    rest = (m > 0) & (body == 0)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(
        rest.astype(np.uint8), connectivity=8
    )
    if n <= 1:
        return None
    by, bx = np.nonzero(body)
    if len(by) == 0:
        return None
    cy, cx = by.mean(), bx.mean()
    radius = np.sqrt(len(by) / np.pi)
    best = None
    for i in range(1, n):
        py, px = np.nonzero(lab == i)
        d = np.hypot(py - cy, px - cx)
        j = int(np.argmax(d))
        reach = d[j] - radius
        # a tail sticks out well past the body, a corner nub does not
        if reach < 0.35 * radius or stats[i][4] < 12:
            continue
        if best is None or reach > best[0]:
            best = (reach, (int(px[j]), int(py[j])))
    return best[1] if best else None
