"""Bubbles -- rising and wobbling, for underwater scenes."""

import numpy as np

from . import common

EMITTER = {
    "id": "bubbles",
    "label": "Bubbles",
    "family": "particles",
    "description": "Rings of light rising and wobbling as they go. Pair it "
    "with a region mask so they stay in the water.",
    "params": [
        common.count(45, 300),
        common.speed(0.35),
        common.size(0.35),
        common.amount("wobble", 0.6, "Wobble", 1.0),
        common.color("#d6f4ff"),
        common.amount("opacity", 0.5, "Opacity", 1.0),
    ],
}


def draw(frame, tl, p, ctx, mask=None, offset=(0.0, 0.0)):
    h, w = frame.shape[:2]
    n = int(p["count"])
    period = common.period_from_speed(p["speed"], slowest=40.0, fastest=5.0)
    x, y, prog, tr = common.crossing_path(tl, n, tl.seed + 601, period, 90)

    x = x + tl.waves(period * 0.19, tr["lane"] * 4.0) * float(p["wobble"]) * 0.03
    px = x * w + offset[0]
    py = y * h + offset[1]

    im, d = common.canvas(h, w)
    rgb = tuple(int(str(p["color"]).lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    rad = np.maximum(1.5, float(p["size"]) * 0.02 * min(h, w) * (0.3 + tr["size"]))
    fade = np.clip(1.0 - prog * 0.4, 0.0, 1.0)  # thin out as they near the top
    for k in range(n):
        r = float(rad[k])
        a = int(255 * float(fade[k]))
        d.ellipse(
            [px[k] - r, py[k] - r, px[k] + r, py[k] + r],
            outline=(rgb[0], rgb[1], rgb[2], a),
            width=max(1, int(r * 0.28)),
        )
    return common.composite(frame, im, float(p["opacity"]), "screen", mask)
