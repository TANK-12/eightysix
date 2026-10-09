"""Sway -- hair, grass, leaves, curtains, hanging fabric, branches."""

import numpy as np

from .. import imageops
from . import common

EFFECT = {
    "id": "sway",
    "label": "Sway",
    "family": "geometry",
    "description": "A soft bend that grows with distance from whichever edge "
    "the thing is attached to, so it hinges instead of sliding. "
    "Two breezes at different rates plus a slow gust keep it "
    "from feeling metronomic. For hair, grass, trees and curtains.",
    "params": [
        common.strength(0.3),
        common.speed(0.3),
        common.direction(0),
        {
            "key": "anchor",
            "label": "Attached at",
            "type": "select",
            "default": "bottom",
            "options": ["bottom", "top", "left", "right", "none"],
        },
        {
            "key": "stiffness",
            "label": "Stiffness",
            "type": "range",
            "default": 1.6,
            "min": 0.4,
            "max": 4.0,
            "step": 0.1,
            "help": "Higher bends mostly at the far tip; lower bends all over.",
        },
        common.amount("gust", 0.4, "Gust", 1.0),
    ],
}

_LEVER = {
    "bottom": lambda gy, gx: 1.0 - gy,
    "top": lambda gy, gx: gy,
    "left": lambda gy, gx: gx,
    "right": lambda gy, gx: 1.0 - gx,
    "none": lambda gy, gx: np.float32(1.0),
}


def apply(frame, mask, box, tl, p, ctx):
    y0, y1, x0, x1 = box
    bh, bw = y1 - y0, x1 - x0
    gy, gx = imageops.grid(box)

    lever = _LEVER.get(str(p["anchor"]), _LEVER["bottom"])(gy, gx)
    lever = np.clip(np.asarray(lever, dtype=np.float32), 0.0, 1.0) ** float(
        p["stiffness"]
    )

    period = common.period_from_speed(p["speed"], slowest=14.0, fastest=1.8)
    breeze = 0.72 * tl.wave(period) + 0.28 * tl.wave(period * 0.41, offset=0.2)
    gust = 1.0 - float(p["gust"]) * (0.5 - 0.5 * tl.wave(period * 3.7, offset=0.13))
    push = breeze * gust

    ux, uy = imageops.direction_vector(p["direction"])
    amp = float(p["strength"]) * 0.05 * max(bh, bw)
    dx = amp * lever * push * ux
    dy = amp * lever * push * uy * 0.35
    return imageops.displace(frame, dx=dx, dy=dy, mask=mask, box=box, fast=ctx.fast)
