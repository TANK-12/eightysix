"""Fish -- swimming back and forth inside a region."""

import numpy as np

from .. import artsource
from . import common

EMITTER = {
    "id": "fish",
    "label": "Fish",
    "family": "creatures",
    "description": "Shapes with a wagging tail that cross a region and come "
    "back. Give it the water mask so they stay in the pond.",
    "params": [
        common.count(9, 80),
        common.speed(0.25),
        common.direction(0),
        common.size(0.3),
        common.amount("wag", 0.7, "Tail wag", 1.0),
        common.amount("depth_fade", 0.5, "Distance fade", 1.0),
        common.color("#e6873c"),
        common.amount("opacity", 0.8, "Opacity", 1.0),
        common.amount("band", 0.9, "Spread", 1.0),
    ],
}


def draw(frame, tl, p, ctx, mask=None, offset=(0.0, 0.0)):
    h, w = frame.shape[:2]
    n = int(p["count"])
    period = common.period_from_speed(p["speed"], slowest=80.0, fastest=12.0)
    x, y, prog, tr = common.crossing_path(
        tl, n, tl.seed + 1013, period, p["direction"], spread=float(p["band"])
    )

    y = y + tl.waves(period * 0.17, tr["extra"] * 3.0) * 0.03
    near = 0.4 + 0.6 * tr["size"]
    wagph = tl.saws(period * 0.04, tr["phase"])

    base = float(p["size"]) * 0.05 * min(h, w)
    rgb = tuple(int(str(p["color"]).lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    fade = float(p["depth_fade"])
    px = x * w + offset[0]
    py = y * h + offset[1]
    for k in range(n):
        s = max(3, int(base * near[k]))
        sp = common.shape_sprite(
            "fish",
            s,
            max(2, int(s * 0.5)),
            rgb,
            phase=float(wagph[k]) * float(p["wag"]),
        )
        artsource.blit(
            frame,
            sp,
            px[k] - sp.shape[1] / 2,
            py[k] - sp.shape[0] / 2,
            opacity=float(p["opacity"]) * (1.0 - fade + fade * float(near[k])),
            mask=mask,
        )
    return frame
