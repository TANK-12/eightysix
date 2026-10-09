"""Clouds -- a cloud bank drifting across a marked-off piece of sky."""

import numpy as np

from .. import imageops, overlay
from . import common

EFFECT = {
    "id": "sky_clouds",
    "label": "Clouds",
    "family": "light",
    "description": "Soft cloud shapes crossing the region and nothing else, so "
    "the sky moves while the rest of the picture holds still. "
    "The cloud field tiles exactly, so it never shows a seam "
    "where it wraps.",
    "params": [
        common.amount("amount", 0.45, "Amount", 1.0),
        common.amount("coverage", 0.5, "Coverage", 1.0),
        common.speed(0.25),
        common.direction(0),
        {"key": "tint", "label": "Tint", "type": "color", "default": "#dfe8ff"},
        {
            "key": "scale",
            "label": "Cloud size",
            "type": "range",
            "default": 0.5,
            "min": 0.05,
            "max": 1.0,
            "step": 0.01,
        },
        {
            "key": "mode",
            "label": "Blend",
            "type": "select",
            "default": "screen",
            "options": ["screen", "over", "shadow"],
        },
    ],
}

_FIELD_CACHE: dict = {}


def _field(bh, bw, scale, coverage, seed=11):
    """The finished cloud shapes, built once.

    Thresholding and blurring both commute with a whole-pixel roll of a field
    that tiles, so all of that shaping can happen here instead of on every
    frame -- per frame there is nothing left but the roll.
    """
    cells = max(1, int(round(6.0 * (1.05 - float(scale)))))
    key = (bh, bw, cells, round(float(coverage), 3), seed)
    f = _FIELD_CACHE.get(key)
    if f is None:
        f = imageops.periodic_noise(bh, bw, cells=cells, seed=seed, octaves=3)
        f = np.clip((f - (0.92 - 0.72 * float(coverage))) * 3.2, 0.0, 1.0)
        f = imageops.box_blur(f, max(1, int(0.02 * min(bh, bw))), passes=1)
        if len(_FIELD_CACHE) > 8:
            _FIELD_CACHE.clear()
        _FIELD_CACHE[key] = f
    return f


def apply(frame, mask, box, tl, p, ctx):
    y0, y1, x0, x1 = box
    bh, bw = y1 - y0, x1 - x0
    if bh < 2 or bw < 2:
        return frame

    field = _field(bh, bw, p["scale"], p["coverage"])
    period = common.period_from_speed(p["speed"], slowest=90.0, fastest=8.0)
    ux, uy = imageops.direction_vector(p["direction"])
    travel = tl.saw(period)
    # whole-pixel rolls of a field that tiles exactly -- no seam at the wrap
    ox = int(round(travel * bw * ux))
    oy = int(round(travel * bh * uy))
    f = np.roll(np.roll(field, -ox, axis=1), -oy, axis=0)

    a = (f * float(p["amount"]) * mask[y0:y1, x0:x1])[..., None]
    tint = np.array(overlay.hex_rgb(str(p["tint"])), dtype=np.float32)
    region = frame[y0:y1, x0:x1]
    mode = str(p["mode"])
    if mode == "over":
        region[...] = region * (1.0 - a) + tint * a
    elif mode == "shadow":
        region[...] = region * (1.0 - 0.75 * a)
    else:  # screen -- light laid over the picture, the usual look
        region[...] = 255.0 - (255.0 - region) * (1.0 - a * (tint / 255.0))
    return frame
