"""Fog -- a bank of mist sitting in the scene, not crossing in front of it."""

import numpy as np

from .. import imageops, overlay
from . import common

EFFECT = {
    "id": "fog",
    "label": "Fog",
    "family": "light",
    "description": "A low bank of mist that drifts and thins, denser toward one "
    "edge of the region. Different from Clouds: this sits inside "
    "the scene and washes out what is behind it, rather than "
    "passing across the sky.",
    "params": [
        common.amount("density", 0.45, "Density", 1.0),
        {
            "key": "height",
            "label": "Sits at",
            "type": "range",
            "default": 0.75,
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
            "help": "0 is the top of the region, 1 the bottom.",
        },
        {
            "key": "depth",
            "label": "Bank thickness",
            "type": "range",
            "default": 0.5,
            "min": 0.05,
            "max": 1.0,
            "step": 0.01,
        },
        common.speed(0.15),
        common.direction(0),
        {
            "key": "scale",
            "label": "Billow size",
            "type": "range",
            "default": 0.55,
            "min": 0.05,
            "max": 1.0,
            "step": 0.01,
        },
        {"key": "tint", "label": "Colour", "type": "color", "default": "#cdd6e4"},
        common.amount("wash", 0.5, "Washes out the picture", 1.0),
    ],
}

_FIELD_CACHE: dict = {}


def _field(bh, bw, scale, seed=23):
    cells = max(1, int(round(5.0 * (1.05 - float(scale)))))
    key = (bh, bw, cells, seed)
    f = _FIELD_CACHE.get(key)
    if f is None:
        f = imageops.periodic_noise(bh, bw, cells=cells, seed=seed, octaves=3)
        f = imageops.box_blur(f, max(1, int(0.03 * min(bh, bw))), passes=1)
        # Stretch it to fill 0..1. Smooth noise sits in a narrow band around its
        # mean, and blurring narrows it further, so the raw field peaks around
        # 0.7 and averages 0.44 -- which made the fog invisible at any sane
        # density until this was measured rather than eyeballed.
        lo, hi = float(f.min()), float(f.max())
        f = np.clip((f - lo) / max(1e-6, hi - lo), 0.0, 1.0)
        if len(_FIELD_CACHE) > 8:
            _FIELD_CACHE.clear()
        _FIELD_CACHE[key] = f
    return f


def apply(frame, mask, box, tl, p, ctx):
    y0, y1, x0, x1 = box
    bh, bw = y1 - y0, x1 - x0
    if bh < 2 or bw < 2:
        return frame

    field = _field(bh, bw, p["scale"])
    period = common.period_from_speed(p["speed"], slowest=120.0, fastest=15.0)
    ux, uy = imageops.direction_vector(p["direction"])
    travel = tl.saw(period)
    ox = int(round(travel * bw * ux))
    oy = int(round(travel * bh * uy))
    f = np.roll(np.roll(field, -ox, axis=1), -oy, axis=0)

    # a band rather than an even wash: that is what makes it read as a bank
    gy, _gx = imageops.grid(box)
    centre = float(p["height"])
    spread = max(0.05, float(p["depth"]))
    band = np.exp(-(((gy - centre) / spread) ** 2)).astype(np.float32)

    # thickens and thins as it drifts, so it never looks like a static gradient
    breathe = 0.8 + 0.2 * tl.wave(period * 0.37, offset=0.15)
    # 1.4 so the density slider can reach a genuine white-out at the top end
    a = (f * band * float(p["density"]) * 1.4 * breathe * mask[y0:y1, x0:x1])[..., None]
    a = np.clip(a, 0.0, 1.0)

    tint = np.array(overlay.hex_rgb(str(p["tint"])), dtype=np.float32)
    region = frame[y0:y1, x0:x1]
    wash = float(p["wash"])
    # fog both adds light and eats contrast; the second part is what sells depth
    region *= 1.0 - a * wash
    region += tint * (a * wash)
    region += (tint / 255.0) * (a * (1.0 - wash) * 60.0)
    np.clip(region, 0.0, 255.0, out=region)
    return frame
