"""Rain -- slanted streaks, from drizzle to downpour."""

import math

import numpy as np

from . import common

EMITTER = {
    "id": "rain",
    "label": "Rain",
    "family": "particles",
    "description": "Falling streaks, angled and length-scaled so the near ones "
    "read faster than the far ones.",
    "params": [
        common.count(220, 900),
        common.speed(0.6),
        common.direction(285),
        common.amount("length", 0.35, "Streak length", 1.0),
        common.amount("thickness", 0.25, "Thickness", 1.0),
        common.color("#c9d8ff"),
        common.amount("opacity", 0.35, "Opacity", 1.0),
    ],
}


def draw(frame, tl, p, ctx, mask=None, offset=(0.0, 0.0)):
    h, w = frame.shape[:2]
    n = int(p["count"])
    period = common.period_from_speed(p["speed"], slowest=14.0, fastest=1.0)
    x, y, prog, tr = common.crossing_path(
        tl, n, tl.seed + 211, period, p["direction"], margin=0.25
    )

    ang = math.radians(float(p["direction"]))
    ln = float(p["length"]) * 0.22 * h * (0.5 + tr["size"])
    dx = -math.cos(ang) * ln
    dy = -math.sin(ang) * ln

    im, d = common.canvas(h, w)
    rgb = tuple(int(str(p["color"]).lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    px = x * w + offset[0]
    py = y * h + offset[1]
    near = 0.4 + 0.6 * tr["size"]
    tw = max(1.0, float(p["thickness"]) * 0.004 * min(h, w))
    for k in range(n):
        a = int(255 * min(1.0, near[k]))
        d.line(
            [(px[k], py[k]), (px[k] + dx[k], py[k] + dy[k])],
            fill=(rgb[0], rgb[1], rgb[2], a),
            width=max(1, int(round(tw * near[k]))),
        )
    return common.composite(frame, im, float(p["opacity"]), "screen", mask)
