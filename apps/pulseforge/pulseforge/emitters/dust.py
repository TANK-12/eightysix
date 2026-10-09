"""Dust -- motes hanging in a shaft of light, barely moving."""

import numpy as np

from . import common

EMITTER = {
    "id": "dust",
    "label": "Dust motes",
    "family": "particles",
    "description": "Tiny specks drifting almost imperceptibly, catching the "
    "light as they turn. The quietest way to stop a still image "
    "looking frozen.",
    "params": [
        common.count(90, 500),
        common.speed(0.12),
        common.direction(80),
        common.size(0.18),
        common.amount("wander", 0.7, "Wander", 1.0),
        common.amount("twinkle", 0.5, "Twinkle", 1.0),
        common.color("#ffe9c4"),
        common.amount("opacity", 0.5, "Opacity", 1.0),
    ],
}


def draw(frame, tl, p, ctx, mask=None, offset=(0.0, 0.0)):
    h, w = frame.shape[:2]
    n = int(p["count"])
    period = common.period_from_speed(p["speed"], slowest=120.0, fastest=20.0)
    x, y, prog, tr = common.crossing_path(tl, n, tl.seed + 401, period, p["direction"])

    wan = float(p["wander"])
    x = x + tl.waves(period * 0.17, tr["lane"] * 5.0) * wan * 0.05
    y = y + tl.waves(period * 0.23, tr["extra"] * 5.0) * wan * 0.04

    tw = float(p["twinkle"])
    shine = 1.0 - tw * 0.5 + tw * 0.5 * tl.waves(period * 0.09, tr["size"] * 7.0)
    px = x * w + offset[0]
    py = y * h + offset[1]
    rad = np.maximum(0.6, float(p["size"]) * 0.01 * min(h, w) * (0.4 + tr["size"]))
    rgb = tuple(int(str(p["color"]).lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    return common.glow(
        frame,
        px,
        py,
        rad * 3.0,
        rgb,
        float(p["opacity"]) * np.clip(shine, 0, 1) * 0.6,
        mask,
    )
