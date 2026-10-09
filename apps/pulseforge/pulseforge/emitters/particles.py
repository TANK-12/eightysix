"""Particles -- the general-purpose one. Build your own drift out of it."""

import math

import numpy as np

from . import common

EMITTER = {
    "id": "particles",
    "label": "Particles",
    "family": "particles",
    "description": "Plain moving specks with every control exposed: how many, "
    "which way, how fast, how big, how much they wander and how "
    "much they glow. The others in this list are this one with "
    "opinions; start here when you want something specific.",
    "params": [
        common.count(80, 800),
        common.speed(0.3),
        common.direction(270),
        common.size(0.25),
        common.amount("size_variation", 0.5, "Size variation", 1.0),
        common.amount("wander", 0.3, "Wander", 1.0),
        common.amount("glow", 0.5, "Glow", 1.0),
        common.color("#ffffff"),
        common.amount("opacity", 0.7, "Opacity", 1.0),
        common.amount("spread", 1.0, "Spread across frame", 1.0),
    ],
}


def draw(frame, tl, p, ctx, mask=None, offset=(0.0, 0.0)):
    h, w = frame.shape[:2]
    n = int(p["count"])
    period = common.period_from_speed(p["speed"], slowest=60.0, fastest=4.0)
    x, y, prog, tr = common.crossing_path(
        tl, n, tl.seed + 101, period, p["direction"], spread=float(p["spread"])
    )

    wander = float(p["wander"])
    if wander > 0.001:
        sway = tl.waves(period * 0.31, tr["lane"] * 3.0)
        bob = tl.waves(period * 0.47, tr["extra"] * 3.0)
        x = x + sway * wander * 0.04
        y = y + bob * wander * 0.03

    px = np.clip(x * w + offset[0], -50, w + 50)
    py = np.clip(y * h + offset[1], -50, h + 50)

    base = float(p["size"]) * 0.012 * min(h, w)
    rad = np.maximum(
        0.6, base * (1.0 - float(p["size_variation"]) * 0.8 + tr["size"] * 1.6)
    )
    inten = (
        float(p["opacity"])
        * (0.45 + 0.55 * tr["size"])
        * (0.5 + 0.5 * float(p["glow"]))
    )
    rgb = tuple(int(str(p["color"]).lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    return common.glow(
        frame, px, py, rad * (1 + 2 * float(p["glow"])), rgb, inten, mask
    )
