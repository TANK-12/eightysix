"""Shimmer -- heat haze, glitter on water, sun on leaves, magic."""

import numpy as np

from .. import imageops
from . import common

EFFECT = {
    "id": "shimmer",
    "label": "Shimmer",
    "family": "light",
    "description": "A fine field of brightening and dimming that crawls across "
    "the region, optionally nudging the pixels with it. For heat "
    "haze, sun glitter on water and light through leaves.",
    "params": [
        common.strength(0.3),
        common.speed(0.4),
        common.radius(0.25, "Grain size"),
        common.amount("distort", 0.2, "Distortion", 1.0),
    ],
}

_CACHE: dict = {}


def _fields(bh, bw, cells):
    key = (bh, bw, cells)
    f = _CACHE.get(key)
    if f is None:
        f = (
            imageops.periodic_noise(bh, bw, cells=cells, seed=31, octaves=2),
            imageops.periodic_noise(bh, bw, cells=cells, seed=57, octaves=2),
        )
        if len(_CACHE) > 8:
            _CACHE.clear()
        _CACHE[key] = f
    return f


def apply(frame, mask, box, tl, p, ctx):
    y0, y1, x0, x1 = box
    bh, bw = y1 - y0, x1 - x0
    if bh < 2 or bw < 2:
        return frame

    cells = max(2, int(round(16.0 * (1.05 - float(p["radius"])))))
    fa, fb = _fields(bh, bw, cells)
    period = common.period_from_speed(p["speed"], slowest=12.0, fastest=1.0)

    # two fields sliding past each other -- interference reads as sparkle
    ax = int(round(tl.saw(period) * bw))
    bx = int(round(tl.saw(period * 1.31, offset=0.4) * bw))
    by = int(round(tl.saw(period * 2.1, offset=0.7) * bh))
    a = np.roll(fa, -ax, axis=1)
    b = np.roll(np.roll(fb, bx, axis=1), -by, axis=0)
    sparkle = (a * b) * 2.0 - 0.5

    dist = float(p["distort"])
    if dist > 0.001:
        amp = dist * 0.012 * min(bh, bw)
        imageops.displace(
            frame,
            dx=(sparkle * amp).astype(np.float32),
            dy=(np.roll(sparkle, 3, axis=0) * amp).astype(np.float32),
            mask=mask,
            box=box,
            fast=ctx.fast,
        )

    lift = (sparkle * float(p["strength"]) * 70.0 * mask[y0:y1, x0:x1])[..., None]
    region = frame[y0:y1, x0:x1]
    region[...] = np.clip(region + lift, 0.0, 255.0)
    return frame
