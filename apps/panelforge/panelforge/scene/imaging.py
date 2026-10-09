"""Classical image analysis for scene: no models needed.

Saliency (spectral residual), speed lines (Hough), colour features, hole
filling, GrabCut cutouts, a white-balloon finder for when bubbles.json is
missing, and simple heuristic depth. These are the fallbacks the model-based
steps drop back to, and the always-on rules around them.
"""

from __future__ import annotations

import math
from typing import Any

import cv2
import numpy as np

from . import geom

# ---------------------------------------------------------------- colour


def colour_hist(bgr: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    """22 bins: 18 hue bins weighted by saturation, plus 4 lightness bins for
    greys (black, dark, light, white hair and clothes). L1-normalised."""
    if bgr.size == 0:
        return np.full(22, 1 / 22)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h = hsv[..., 0].astype(np.float32).ravel()
    s = hsv[..., 1].astype(np.float32).ravel() / 255
    v = hsv[..., 2].astype(np.float32).ravel() / 255
    keep = np.ones_like(h, bool) if mask is None else (mask.ravel() > 127)
    h, s, v = h[keep], s[keep], v[keep]
    if h.size == 0:
        return np.full(22, 1 / 22)
    colourful = (s * v) > 0.18
    hue = np.bincount(
        (h[colourful] / 180 * 18).astype(int).clip(0, 17),
        weights=(s * v)[colourful],
        minlength=18,
    )
    grey = np.bincount((v[~colourful] * 4).astype(int).clip(0, 3), minlength=4).astype(
        np.float64
    )
    out = np.concatenate([hue, grey]).astype(np.float64)
    return out / max(out.sum(), 1e-9)


def lab_stats(bgr: np.ndarray) -> dict[str, float]:
    """Mean lightness, warmth and saturation (0..1-ish) for mood rules."""
    small = cv2.resize(bgr, (64, max(1, int(64 * bgr.shape[0] / bgr.shape[1]))))
    lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB).astype(np.float32)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV).astype(np.float32)
    return {
        "lightness": float(lab[..., 0].mean() / 255),
        # a* (green-red) and b* (blue-yellow) centred on 128
        "warmth": float(((lab[..., 1] - 128) + (lab[..., 2] - 128)).mean() / 64),
        "red": float((lab[..., 1] - 128).mean() / 64),
        "saturation": float(hsv[..., 1].mean() / 255),
        "contrast": float(lab[..., 0].std() / 128),
    }


def layout_feature(bgr: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    """Background signature: a Lab colour histogram plus a 4x4 colour layout.
    Masked-out pixels (characters, bubbles) do not count."""
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    m = None if mask is None else (mask < 128).astype(np.uint8)
    hist = cv2.calcHist([lab], [0, 1, 2], m, [6, 6, 6], [0, 256, 0, 256, 0, 256])
    hist = hist.ravel().astype(np.float64)
    hist /= max(hist.sum(), 1e-9)
    grid = cv2.resize(lab, (4, 4), interpolation=cv2.INTER_AREA)
    return np.concatenate([hist, grid.ravel().astype(np.float64) / 255 / 48])


# ---------------------------------------------------------------- saliency


def spectral_residual(bgr: np.ndarray, width: int = 64) -> np.ndarray:
    """Hou & Zhang 2007 saliency map, float 0..1 at the panel's size."""
    h, w = bgr.shape[:2]
    sw = width
    sh = max(8, int(round(width * h / max(w, 1))))
    grey = cv2.cvtColor(cv2.resize(bgr, (sw, sh)), cv2.COLOR_BGR2GRAY)
    f = np.fft.fft2(grey.astype(np.float64))
    log_amp = np.log(np.abs(f) + 1e-9)
    phase = np.angle(f)
    residual = log_amp - cv2.blur(log_amp, (3, 3))
    sal = np.abs(np.fft.ifft2(np.exp(residual + 1j * phase))) ** 2
    sal = cv2.GaussianBlur(sal, (0, 0), 2.5)
    sal = (sal - sal.min()) / max(float(sal.max() - sal.min()), 1e-9)
    return cv2.resize(sal.astype(np.float32), (w, h))


def saliency_points(
    bgr: np.ndarray, faces: list[list[int]], top: int = 5
) -> list[list[float]]:
    """[[x, y, weight]]: faces first (weight 1.0 scaled by size), then the
    strongest spectral-residual peaks spaced apart."""
    h, w = bgr.shape[:2]
    pts: list[list[float]] = []
    biggest = max((f[2] * f[3] for f in faces), default=1)
    for f in faces:
        cx, cy = geom.center(f)
        pts.append(
            [int(cx), int(cy), round(0.6 + 0.4 * f[2] * f[3] / max(biggest, 1), 3)]
        )
    sal = spectral_residual(bgr)
    small = cv2.resize(sal, (32, max(4, int(32 * h / max(w, 1)))))
    dil = cv2.dilate(small, np.ones((5, 5), np.uint8))
    ys, xs = np.where((small >= dil) & (small > 0.35))
    peaks = sorted(zip(small[ys, xs], xs, ys), reverse=True)
    sx, sy = w / small.shape[1], h / small.shape[0]
    min_gap = 0.15 * math.hypot(w, h)
    for val, x, y in peaks:
        px, py = (x + 0.5) * sx, (y + 0.5) * sy
        if all(math.hypot(px - p[0], py - p[1]) > min_gap for p in pts):
            pts.append([int(px), int(py), round(float(val) * 0.8, 3)])
        if len(pts) >= top:
            break
    return pts


# ---------------------------------------------------------------- speed lines


def speed_lines(bgr: np.ndarray) -> dict[str, Any] | None:
    """Detect drawn motion lines.

    Parallel lines: many long straight segments sharing one angle.
    Focus lines: many long segments whose extensions meet near one point.
    Returns {"present", "angle_deg", "kind", "strength"[, "focus"]} or None.
    """
    h, w = bgr.shape[:2]
    scale = 480 / max(h, w)
    small = cv2.resize(bgr, (max(8, int(w * scale)), max(8, int(h * scale))))
    grey = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(grey, 60, 160)
    sh, sw = grey.shape
    min_len = 0.22 * min(sh, sw) + 12
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180, threshold=40, minLineLength=min_len, maxLineGap=3
    )
    if lines is None or len(lines) < 10:
        return None
    segs = np.asarray(lines).reshape(-1, 4).astype(np.float64)  # OpenCV 4 and 5 shapes
    ang = np.degrees(np.arctan2(segs[:, 3] - segs[:, 1], segs[:, 2] - segs[:, 0]))
    ang = np.mod(ang, 180)
    lengths = np.hypot(segs[:, 2] - segs[:, 0], segs[:, 3] - segs[:, 1])
    # Panel borders and horizon lines are exactly 0/90 degrees; ignore them.
    diagonal = np.minimum(np.abs(ang - 90), np.minimum(ang, 180 - ang)) > 3
    hist = np.bincount((ang // 10).astype(int) % 18, weights=lengths, minlength=18)
    ring = hist + np.roll(hist, 1) + np.roll(hist, -1)
    peak = int(np.argmax(ring))
    share = float(ring[peak] / max(hist.sum(), 1e-9))
    n = len(segs)
    if share >= 0.55 and n >= 14 and diagonal.mean() > 0.3:
        sel = (np.abs(((ang - (peak * 10 + 5)) + 90) % 180 - 90)) <= 15
        mean = float(np.degrees(np.arctan2(*_mean_axis(ang[sel])[::-1])))
        return {
            "present": True,
            "angle_deg": int(round(mean % 180)),
            "kind": "parallel",
            "strength": round(min(1.0, n / 60) * share, 3),
        }
    focus = _radial_focus(segs, sw, sh)
    if focus is not None and n >= 16:
        fx, fy, frac = focus
        return {
            "present": True,
            "angle_deg": None,
            "kind": "radial",
            "focus": [int(fx / scale), int(fy / scale)],
            "strength": round(min(1.0, n / 60) * frac, 3),
        }
    return None


def _mean_axis(angles_deg: np.ndarray) -> tuple[float, float]:
    """Mean direction of undirected angles (doubled-angle trick)."""
    r = np.radians(angles_deg * 2)
    c, s = float(np.cos(r).mean()), float(np.sin(r).mean())
    a = math.atan2(s, c) / 2
    return math.cos(a), math.sin(a)


def _radial_focus(segs: np.ndarray, w: int, h: int):
    """Least-squares point closest to all line extensions, and the share of
    lines passing near it."""
    p = segs[:, :2]
    d = segs[:, 2:] - segs[:, :2]
    d /= np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
    nrm = np.stack([-d[:, 1], d[:, 0]], axis=1)
    a = nrm
    b = (nrm * p).sum(axis=1)
    try:
        x, *_ = np.linalg.lstsq(a, b, rcond=None)
    except np.linalg.LinAlgError:
        return None
    if not (-0.25 * w <= x[0] <= 1.25 * w and -0.25 * h <= x[1] <= 1.25 * h):
        return None
    dist = np.abs(a @ x - b)
    frac = float((dist < 0.06 * math.hypot(w, h)).mean())
    return (float(x[0]), float(x[1]), frac) if frac >= 0.6 else None


# ---------------------------------------------------------------- masks


def grabcut_mask(bgr: np.ndarray, box: list[int], iters: int = 3) -> np.ndarray:
    """Foreground mask (uint8 0/255, panel size) for a character box."""
    h, w = bgr.shape[:2]
    x, y, bw, bh = geom.clip(box, w, h)
    out = np.zeros((h, w), np.uint8)
    if bw < 8 or bh < 8:
        return out
    # Work on a padded, downscaled crop: GrabCut is slow on big panels.
    pad = geom.clip(geom.expand([x, y, bw, bh], 0.1, 0.05, 0.1, 0.05), w, h)
    crop = bgr[pad[1] : pad[1] + pad[3], pad[0] : pad[0] + pad[2]]
    s = min(1.0, 320 / max(crop.shape[:2]))
    small = cv2.resize(
        crop, (max(8, int(crop.shape[1] * s)), max(8, int(crop.shape[0] * s)))
    )
    rect = (
        max(1, int((x - pad[0]) * s)),
        max(1, int((y - pad[1]) * s)),
        max(4, int(bw * s) - 2),
        max(4, int(bh * s) - 2),
    )
    m = np.zeros(small.shape[:2], np.uint8)
    try:
        cv2.grabCut(
            small,
            m,
            rect,
            np.zeros((1, 65)),
            np.zeros((1, 65)),
            iters,
            cv2.GC_INIT_WITH_RECT,
        )
    except cv2.error:
        return out
    fg = np.where((m == cv2.GC_FGD) | (m == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    fg = cv2.resize(fg, (pad[2], pad[3]), interpolation=cv2.INTER_LINEAR)
    out[pad[1] : pad[1] + pad[3], pad[0] : pad[0] + pad[2]] = fg
    return out


def find_balloons(bgr: np.ndarray) -> list[list[int]]:
    """Fallback text-box finder, used only when bubbles.json has nothing for a
    panel: clusters of letter-sized strokes sitting on a flat light (speech
    balloon) or flat dark (caption box) area. Returns boxes covering the
    balloon, or the text plus a margin when the balloon merges into a gutter."""
    h, w = bgr.shape[:2]
    grey = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    boxes: list[list[int]] = []
    for paper, ink in ((grey > 215, grey < 120), (grey < 40, grey > 180)):
        paper_u8 = cv2.morphologyEx(
            paper.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)
        )
        n, lab, stats, _ = cv2.connectedComponentsWithStats(ink.astype(np.uint8), 8)
        letters = np.zeros((h, w), np.uint8)
        for i in range(1, n):
            x, y, bw, bh, a = stats[i]
            if not (5 <= bh <= 48 and bw <= 60 and 6 <= a <= 900):
                continue
            ring = paper_u8[max(0, y - 3) : y + bh + 3, max(0, x - 3) : x + bw + 3]
            if ring.mean() < 0.45:
                continue
            letters[lab == i] = 255
        if not letters.any():
            continue
        groups = cv2.dilate(letters, np.ones((9, 17), np.uint8))
        gn, glab, gstats, _ = cv2.connectedComponentsWithStats(groups, 8)
        pn, plab, pstats, _ = cv2.connectedComponentsWithStats(paper_u8, 8)
        for g in range(1, gn):
            x, y, bw, bh, _a = gstats[g]
            count = (
                cv2.connectedComponentsWithStats(letters[y : y + bh, x : x + bw])[0] - 1
            )
            if count < 4 or bw < 24:
                continue
            region = plab[y : y + bh, x : x + bw][glab[y : y + bh, x : x + bw] == g]
            region = region[region > 0]
            box = [x - 0.15 * bw - 10, y - 0.3 * bh - 10, bw * 1.3 + 20, bh * 1.6 + 20]
            if region.size:
                pid = int(np.bincount(region).argmax())
                px, py, pw, ph, pa = pstats[pid]
                edges = (px <= 1) + (py <= 1) + (px + pw >= w - 1) + (py + ph >= h - 1)
                compact = pa / float(pw * ph) > 0.45 and pw < 0.9 * w and ph < 0.8 * h
                if edges < 2 and compact:
                    box = [px - 2, py - 2, pw + 4, ph + 4]
            boxes.append(geom.clip(box, w, h))
    return [b for b in boxes if b[2] > 0 and b[3] > 0]


def inpaint(bgr: np.ndarray, hole: np.ndarray) -> np.ndarray:
    """Fill hole pixels (uint8 255 = fill). Large holes are filled at low
    resolution first so the fill carries colour from far away, then detail
    near the edges is refined at full size."""
    if not hole.any():
        return bgr.copy()
    h, w = bgr.shape[:2]
    s = min(1.0, 200 / max(h, w))
    small = cv2.resize(
        bgr, (max(4, int(w * s)), max(4, int(h * s))), interpolation=cv2.INTER_AREA
    )
    small_hole = cv2.resize(
        hole, (small.shape[1], small.shape[0]), interpolation=cv2.INTER_NEAREST
    )
    small_hole = cv2.dilate(small_hole, np.ones((3, 3), np.uint8))
    coarse = cv2.inpaint(small, small_hole, 5, cv2.INPAINT_TELEA)
    coarse = cv2.resize(coarse, (w, h), interpolation=cv2.INTER_CUBIC)
    coarse = cv2.GaussianBlur(coarse, (0, 0), 3)
    out = bgr.copy()
    hard = hole > 127
    out[hard] = coarse[hard]
    # Refine a thin ring along the hole edge at full resolution.
    ring = cv2.dilate(hole, np.ones((5, 5), np.uint8)) & ~cv2.erode(
        hole, np.ones((9, 9), np.uint8)
    )
    return cv2.inpaint(out, ring, 3, cv2.INPAINT_TELEA)


def heuristic_depth(h: int, w: int, char_masks: list[np.ndarray]) -> np.ndarray:
    """Float 0..1, near = 1: a floor-like vertical gradient with characters
    pulled forward (bigger character = nearer)."""
    grad = np.linspace(0.15, 0.45, h, dtype=np.float32)[:, None].repeat(w, axis=1)
    order = sorted(char_masks, key=lambda m: int((m > 127).sum()))
    total = float(h * w)
    for m in order:
        frac = (m > 127).sum() / total
        near = 0.6 + 0.4 * min(1.0, frac * 3)
        soft = cv2.GaussianBlur((m > 127).astype(np.float32), (0, 0), 3)
        grad = np.maximum(grad, soft * near)
    return grad


def to_depth16(depth: np.ndarray) -> np.ndarray:
    d = depth.astype(np.float64)
    lo, hi = np.percentile(d, 1), np.percentile(d, 99)
    d = np.clip((d - lo) / max(hi - lo, 1e-9), 0, 1)
    return (d * 65535).astype(np.uint16)
