"""Gutters: the background between panels, found by row statistics.

All functions here are pure numpy/OpenCV on arrays, so they are easy to test on
synthetic strips.

A gutter is not assumed to be white. Each row gets a "flatness" score (the
share of its pixels close to the row's median colour). Rows that are almost
entirely one colour are seed rows; their colours are interpolated down the
strip, which tolerates vertical gradients such as a black-to-red fade. A pixel
belongs to the gutter when it is close to that colour field and is connected
to a seed row, so white areas inside a drawing that do not touch the gutter
stay part of the panel, and a slanted white gap between two panels is gutter
even though no single row is flat.
"""

import cv2
import numpy as np

# Colour distance (max over channels, 0..255) still counted as "the same".
TOL = 12
# A row is a seed when at least this share of it matches its median colour.
SEED_FLAT = 0.985


def row_stats(img: np.ndarray, tol: int = TOL) -> tuple[np.ndarray, np.ndarray]:
    """Per-row median colour (N x 3 float32) and flatness (N float32)."""
    im = img.astype(np.int16)
    med = np.median(im, axis=1).astype(np.int16)
    diff = np.abs(im - med[:, None, :]).max(axis=2)
    flat = (diff <= tol).mean(axis=1).astype(np.float32)
    return med.astype(np.float32), flat


def runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """[start, end) index pairs of the True runs of a 1-D boolean array."""
    m = np.concatenate([[False], np.asarray(mask, bool), [False]])
    d = np.flatnonzero(m[1:] != m[:-1])
    return [(int(a), int(b)) for a, b in zip(d[::2], d[1::2])]


def seed_rows(flat: np.ndarray, min_run: int = 2, thr: float = SEED_FLAT) -> np.ndarray:
    """Flat rows, keeping only runs of at least min_run rows (one flat row inside art is not a gutter)."""
    seed = flat >= thr
    out = np.zeros_like(seed)
    for a, b in runs(seed):
        if b - a >= min_run:
            out[a:b] = True
    return out


def color_field(med: np.ndarray, seed: np.ndarray) -> np.ndarray:
    """Gutter colour for every row: seed colours, linearly interpolated in between."""
    n = len(med)
    idx = np.flatnonzero(seed)
    if len(idx) == 0:
        return np.full((n, 3), -1000.0, np.float32)  # nothing matches: no gutter
    ys = np.arange(n)
    return np.stack([np.interp(ys, idx, med[idx, c]) for c in range(3)], axis=1).astype(
        np.float32
    )


def gutter_mask(
    img: np.ndarray,
    tol: int = TOL,
    seed_thr: float = SEED_FLAT,
    min_seed_run: int = 2,
) -> tuple[np.ndarray, np.ndarray]:
    """Boolean gutter mask (H x W) and the seed-row flags (H,) for an image.

    Pixels near the interpolated gutter colour of their row, 4-connected to a
    seed row. Also accepts pixels near the seed colour directly above or below
    when a gutter changes colour sharply (black band meeting a white band).
    """
    med, flat = row_stats(img, tol)
    seed = seed_rows(flat, min_seed_run, seed_thr)
    field = color_field(med, seed)
    im = img.astype(np.int16)
    cand = np.abs(im - field[:, None, :]).max(axis=2) <= tol
    idx = np.flatnonzero(seed)
    if len(idx):
        ys = np.arange(len(med))
        above = idx[
            np.clip(np.searchsorted(idx, ys, side="right") - 1, 0, len(idx) - 1)
        ]
        below = idx[np.clip(np.searchsorted(idx, ys, side="left"), 0, len(idx) - 1)]
        for src in (above, below):
            col = med[src].astype(np.int16)
            cand |= np.abs(im - col[:, None, :]).max(axis=2) <= tol
    cand[seed] = True
    n, labels = cv2.connectedComponents(cand.astype(np.uint8), connectivity=4)
    if n <= 1 or not seed.any():
        return np.zeros(cand.shape, bool), seed
    keep = np.zeros(n, bool)
    keep[np.unique(labels[seed])] = True
    keep[0] = False
    return keep[labels], seed


def cut_rows(seed: np.ndarray, min_gap: int) -> list[tuple[int, int]]:
    """Content sections between runs of at least min_gap seed rows."""
    content = np.ones(len(seed), bool)
    for a, b in runs(seed):
        if b - a >= min_gap:
            content[a:b] = False
    return runs(content)


def line_gutter_share(
    gutter: np.ndarray, y_left: float, y_right: float, band: int = 1
) -> float:
    """Share of the columns where the straight line from (0, y_left) to (W-1, y_right) is gutter.

    band > 1 requires a gutter pixel anywhere within +-band rows of the line.
    """
    h, w = gutter.shape
    xs = np.arange(w)
    ys = np.rint(y_left + (y_right - y_left) * xs / max(1, w - 1)).astype(int)
    hit = np.zeros(w, bool)
    for d in range(-band + 1, band):
        yy = ys + d
        ok = (yy >= 0) & (yy < h)
        hit[ok] |= gutter[yy[ok], xs[ok]]
    return float(hit.mean())


def best_slanted_cut(
    gutter: np.ndarray,
    min_share: float = 0.9,
    max_slope: float = 0.6,
    margin: int = 20,
    step: int = 2,
) -> tuple[float, float, float] | None:
    """Best straight cut across a region that runs through the gutter.

    Returns (y_left, y_right, share) for the line with the highest gutter share
    (ties broken toward the middle), or None when no line reaches min_share.
    Lines closer than `margin` rows to the top or bottom are ignored, so a cut
    always leaves something on both sides.
    """
    h, w = gutter.shape
    if h < 2 * margin + 2:
        return None
    max_dy = int(max_slope * w)
    # Shear trick: shifting column x by dy*x/w turns a slanted line into a row.
    best: tuple[tuple[float, float, float], tuple[float, float, float]] | None = None
    cols = np.arange(w)
    g = gutter.astype(np.float32)
    for dy in range(-max_dy, max_dy + 1, max(1, step)):
        shift = np.rint(dy * cols / max(1, w - 1)).astype(int)
        lo = max(margin, margin - dy)
        hi = min(h - margin, h - margin - dy)
        if hi <= lo:
            continue
        rows = np.arange(lo, hi)  # y_left of each candidate line
        share = g[rows[:, None] + shift[None, :], cols[None, :]].mean(axis=1)
        k = int(np.argmax(share))
        s = float(share[k])
        if s < min_share:
            continue
        # prefer: more gutter, then less slant, then nearer the middle
        yl = float(rows[k])
        centre = abs(yl + dy / 2 - h / 2) / h
        key = (round(s, 2), -abs(dy) / w, -centre)
        if best is None or key > best[0]:
            best = (key, (yl, yl + dy, s))
    return best[1] if best else None
