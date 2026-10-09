"""Fireflies -- wandering lights that fade in and out."""

import numpy as np

from . import common

EMITTER = {
    "id": "fireflies",
    "label": "Fireflies",
    "family": "particles",
    "description": "Points of light that wander on their own paths and pulse "
    "on and off out of step with each other. Warm evenings, "
    "forests, anything that wants a bit of magic.",
    "params": [
        common.count(28, 200),
        common.speed(0.25),
        common.size(0.35),
        common.amount("wander", 0.6, "Wander", 1.0),
        common.amount("blink", 0.8, "Blink", 1.0),
        common.color("#c8ff9e"),
        common.amount("opacity", 0.9, "Opacity", 1.0),
    ],
}


def draw(frame, tl, p, ctx, mask=None, offset=(0.0, 0.0)):
    h, w = frame.shape[:2]
    n = int(p["count"])
    tr = common.traits(tl.seed + 503, n)
    period = common.period_from_speed(p["speed"], slowest=60.0, fastest=10.0)

    wan = float(p["wander"]) * 0.16
    x = tr["lane"] + tl.waves(period, tr["phase"] * 4.0) * wan
    y = tr["size"] + tl.waves(period * 0.61, tr["extra"] * 4.0) * wan * 0.8

    blink = float(p["blink"])
    pulse = 0.5 + 0.5 * tl.waves(period * 0.29, tr["rate"] * 6.0)
    level = (1.0 - blink) + blink * np.clip(pulse, 0, 1) ** 2

    px = np.clip(x, -0.05, 1.05) * w + offset[0]
    py = np.clip(y, -0.05, 1.05) * h + offset[1]
    rad = np.maximum(1.0, float(p["size"]) * 0.014 * min(h, w) * (0.5 + tr["size"]))
    rgb = tuple(int(str(p["color"]).lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    return common.glow(frame, px, py, rad * 3.5, rgb, float(p["opacity"]) * level, mask)
