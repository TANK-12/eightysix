"""Leaves and petals -- tumbling as they fall."""

import numpy as np

from .. import artsource
from . import common

EMITTER = {
    "id": "leaves",
    "label": "Leaves / petals",
    "family": "particles",
    "description": "Falling shapes that tumble edge-on and flat as they go, "
    "which is what stops them reading as floating discs. Switch "
    "between a leaf and a blossom petal.",
    "params": [
        {
            "key": "shape",
            "label": "Shape",
            "type": "select",
            "default": "leaf",
            "options": ["leaf", "petal"],
        },
        common.count(30, 250),
        common.speed(0.3),
        common.direction(260),
        common.size(0.35),
        common.amount("tumble", 0.7, "Tumble", 1.0),
        common.amount("sway", 0.6, "Sway", 1.0),
        common.color("#e8a45c"),
        common.amount("opacity", 0.9, "Opacity", 1.0),
    ],
}


def draw(frame, tl, p, ctx, mask=None, offset=(0.0, 0.0)):
    h, w = frame.shape[:2]
    n = int(p["count"])
    period = common.period_from_speed(p["speed"], slowest=45.0, fastest=6.0)
    x, y, prog, tr = common.crossing_path(tl, n, tl.seed + 809, period, p["direction"])

    x = x + tl.waves(period * 0.21, tr["lane"] * 3.3) * float(p["sway"]) * 0.06
    spin = tl.saws(period * 0.13, tr["extra"])

    base = float(p["size"]) * 0.03 * min(h, w)
    rgb = tuple(int(str(p["color"]).lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    kind = str(p["shape"])
    tumble = float(p["tumble"])
    px = x * w + offset[0]
    py = y * h + offset[1]
    for k in range(n):
        s = max(2, int(base * (0.5 + tr["size"][k])))
        ph = float(spin[k]) * tumble
        sp = common.shape_sprite(kind, s, max(2, int(s * 0.7)), rgb, phase=ph)
        artsource.blit(
            frame,
            sp,
            px[k] - sp.shape[1] / 2,
            py[k] - sp.shape[0] / 2,
            opacity=float(p["opacity"]),
            mask=mask,
        )
    return frame
