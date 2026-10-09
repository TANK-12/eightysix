"""Reflection -- what is above the waterline, mirrored into it."""

import numpy as np

from .. import imageops
from . import common

EFFECT = {
    "id": "reflection",
    "label": "Reflection",
    "family": "geometry",
    "description": "Mirrors whatever sits above the region down into it, "
    "broken up by a ripple and fading with distance. For water, "
    "wet streets and polished floors -- the thing a still image "
    "of a lake is usually missing.",
    "params": [
        common.strength(0.55, "How visible"),
        common.amount("ripple", 0.4, "Ripple", 1.0),
        common.length(70.0, "Ripple length", 8.0, 400.0),
        common.speed(0.25),
        common.amount("fade", 0.6, "Fade with distance", 1.0),
        common.amount("darken", 0.25, "Darken", 1.0),
        common.amount("blur", 0.2, "Softness", 1.0),
    ],
}


def apply(frame, mask, box, tl, p, ctx):
    y0, y1, x0, x1 = box
    bh, bw = y1 - y0, x1 - x0
    if bh < 4 or bw < 4 or y0 < 2:
        return frame  # nothing above the region to reflect

    gy, _gx = imageops.grid(box)
    rows = np.arange(y0, y1, dtype=np.float32)[:, None]

    # mirror about the region's top edge: row y reads from row 2*y0 - y
    mirror = (2.0 * y0 - 2.0 * rows).astype(np.float32)

    period = common.period_from_speed(p["speed"], slowest=18.0, fastest=2.0)
    wl = max(8.0, float(p["wave_length"]))
    xs = np.arange(x0, x1, dtype=np.float32)[None, :]
    ph = tl.phase(period)
    ph2 = tl.phase(period * 0.57, offset=0.3)
    # ripples grow toward the near edge, the way a real reflection breaks up
    near = (0.25 + 0.75 * gy).astype(np.float32)
    wave = np.sin(2 * np.pi * (rows / wl + xs / (wl * 2.4) + ph))
    wave = wave + 0.5 * np.sin(2 * np.pi * (rows / (wl * 0.6) - ph2))
    amp = float(p["ripple"]) * 0.04 * bh

    dy = mirror + (wave * amp * near).astype(np.float32)
    dx = (wave * amp * near * 0.5).astype(np.float32)

    block = imageops.sample(frame, dx, dy, box, fast=ctx.fast)

    blur = float(p["blur"])
    if blur > 0.01:
        block = imageops.box_blur(block, max(1, int(blur * 0.02 * bh)), passes=1)

    darken = float(p["darken"])
    if darken > 0.001:
        block = block * (1.0 - darken * 0.6)

    # weaker the further from the waterline, which is what sells it as a surface
    fade = float(p["fade"])
    weight = (1.0 - fade * gy) * float(p["strength"])
    a = (np.clip(weight, 0.0, 1.0) * mask[y0:y1, x0:x1])[..., None]
    region = frame[y0:y1, x0:x1]
    region *= 1.0 - a
    region += block * a
    return frame
