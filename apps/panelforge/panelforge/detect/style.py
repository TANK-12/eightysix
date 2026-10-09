"""Lettering style of a bubble: the visual cues that drive voice acting.

Measured on the prepared OCR image (letters scaled to a fixed height and
binarised), so every number is relative to letter size rather than pixels:

    stroke   letter thickness (4 x mean distance-to-edge over ink pixels)
    shear    slant of the ink, positive when leaning right (italic)
    rough    outline roughness of letters (perimeter over hull perimeter)

bubble_style() turns the per-word numbers plus the balloon kind and shape
features into the contract's `style` block (CONTRACTS.md, "Expression cues
for voice acting"). Everything is relative to the chapter's medians, which
detect computes once all bubbles are read.
"""

from __future__ import annotations

import numpy as np

import cv2

ITALIC_SHEAR = 0.12
WAVY_RESIDUAL = 0.12
TREMBLE_ROUGH = 1.22
TREMBLE_RATIO = 1.15  # over the chapter's median letter roughness
BOLD_RATIO = 1.3

OUTLINES = ("smooth", "jagged", "wobbly", "dashed", "cloud", "rect", "none")


def measure_word(binary: np.ndarray, box: tuple[int, int, int, int]) -> dict:
    """stroke, shear and rough for the ink inside box of a dark-on-white binary image."""
    x, y, w, h = box
    sub = binary[max(0, y) : y + h, max(0, x) : x + w]
    ink = sub < 128
    n = int(ink.sum())
    if n < 8:
        return {"stroke": 0.0, "shear": 0.0, "rough": 1.0, "ink": n}
    dist = cv2.distanceTransform(ink.astype(np.uint8), cv2.DIST_L2, 3)
    stroke = float(4.0 * dist[ink].mean())
    shear = _shear(ink.astype(np.uint8), min_h=max(6, int(0.5 * h)))
    rough = _roughness(ink.astype(np.uint8), min_h=max(6, int(0.5 * h)))
    return {
        "stroke": round(stroke, 3),
        "shear": round(shear, 3),
        "rough": round(rough, 3),
        "ink": n,
    }


_SHEARS = np.linspace(-0.45, 0.45, 31)


def _shear(mask: np.ndarray, min_h: int) -> float:
    """Slant of the letters: the de-shear that stacks each letter's ink into
    the fewest columns, median over letters, positive for a right lean."""
    n, labels, st, _c = cv2.connectedComponentsWithStats(mask, connectivity=8)
    best: list[tuple[int, float]] = []
    for k in range(1, n):
        if st[k, cv2.CC_STAT_HEIGHT] < min_h or st[k, cv2.CC_STAT_AREA] < 12:
            continue
        ys, xs = np.nonzero(labels == k)
        yc = ys.mean()
        scores = []
        for sh in _SHEARS:
            xp = np.round(xs + sh * (ys - yc)).astype(int)
            xp -= xp.min()
            counts = np.bincount(xp)
            scores.append(float((counts.astype(np.float64) ** 2).sum()))
        best.append((int(len(xs)), float(_SHEARS[int(np.argmax(scores))])))
    if not best:
        return 0.0
    ws = np.array([b[0] for b in best], float)
    vals = np.array([b[1] for b in best])
    order = np.argsort(vals)
    cum = np.cumsum(ws[order])
    return float(vals[order][int(np.searchsorted(cum, cum[-1] / 2))])


def _roughness(mask: np.ndarray, min_h: int) -> float:
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    vals = []
    for c in cnts:
        _x, _y, _w, ch = cv2.boundingRect(c)
        if ch < min_h or len(c) < 8:
            continue
        hull = cv2.convexHull(c)
        hp = cv2.arcLength(hull, True)
        if hp > 0:
            vals.append(cv2.arcLength(c, True) / hp)
    return float(np.median(vals)) if vals else 1.0


def line_waviness(lines) -> float:
    """Largest baseline wobble over the text lines, relative to letter height."""
    worst = 0.0
    for line in lines:
        comps = line.comps
        if len(comps) < 4:
            continue
        cx = np.array([c.cx for c in comps])
        cy = np.array([c.cy for c in comps])
        a, b = np.polyfit(cx, cy, 1)
        resid = cy - (a * cx + b)
        worst = max(worst, float(resid.std() / max(1.0, line.h)))
    return round(worst, 3)


def outline_for(kind: str, feats: dict, closed: bool) -> str:
    if not closed:
        return "none"
    if kind == "shout":
        return "jagged"
    if kind == "thought":
        return "cloud"
    if kind == "whisper":
        return "dashed"
    if kind == "caption" or feats.get("rect_fill", 0) >= 0.93:
        return "rect"
    if feats.get("roughness", 1.0) >= 1.10 or feats.get("defects", 0) >= 4:
        return "wobbly"
    return "smooth"


def ink_colour(crop: np.ndarray, polarity: str) -> str:
    g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    ink = g < 110 if polarity == "dark" else g > 150
    if ink.sum() < 8:
        return "#000000" if polarity == "dark" else "#ffffff"
    b, g_, r = np.median(crop[ink].reshape(-1, 3), axis=0)
    return "#%02x%02x%02x" % (int(r), int(g_), int(b))


def bubble_style(
    kind: str,
    feats: dict,
    closed: bool,
    words: list[dict],
    line_h: float,
    waviness: float,
    colour: str,
    median_line_h: float,
    median_stroke: float,
    median_rough: float = 1.0,
) -> dict:
    """The contract `style` block for one bubble."""
    inked = [w for w in words if w.get("ink", 0) >= 8]
    tot = float(sum(w["ink"] for w in inked)) or 1.0
    stroke = float(np.median([w["stroke"] for w in inked])) if inked else 0.0
    shear = sum(w["shear"] * w["ink"] for w in inked) / tot if inked else 0.0
    rough = sum(w["rough"] * w["ink"] for w in inked) / tot if inked else 1.0
    bold = []
    if len(inked) >= 3 and stroke > 0:
        bold = [w["text"] for w in inked if w["stroke"] > BOLD_RATIO * stroke]
    return {
        "outline": outline_for(kind, feats, closed),
        "text_scale": round(line_h / median_line_h, 3) if median_line_h > 0 else 1.0,
        "stroke_weight": (
            round(stroke / median_stroke, 3)
            if median_stroke > 0 and stroke > 0
            else 1.0
        ),
        "italic": shear > ITALIC_SHEAR,
        "wavy": waviness > WAVY_RESIDUAL,
        "trembling": rough > max(TREMBLE_ROUGH, TREMBLE_RATIO * median_rough),
        "color": colour,
        "bold_words": bold,
        "measured": {
            "stroke": round(stroke, 3),
            "shear": round(shear, 3),
            "rough": round(rough, 3),
            "wave": waviness,
        },
    }
