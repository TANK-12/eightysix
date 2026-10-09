"""Snow -- soft flakes that drift sideways as they fall."""

import numpy as np

from . import common

EMITTER = {
    "id": "snow",
    "label": "Snow",
    "family": "particles",
    "description": "Slow soft flakes with a lateral sway, the near ones larger "
    "and brighter than the far ones.",
    "params": [
        common.count(140, 700),
        common.speed(0.22),
        common.direction(268),
        common.size(0.3),
        common.amount("sway", 0.55, "Sway", 1.0),
        common.color("#ffffff"),
        common.amount("opacity", 0.75, "Opacity", 1.0),
    ],
}


def draw(frame, tl, p, ctx, mask=None, offset=(0.0, 0.0)):
    h, w = frame.shape[:2]
    n = int(p["count"])
    period = common.period_from_speed(p["speed"], slowest=70.0, fastest=8.0)
    x, y, prog, tr = common.crossing_path(tl, n, tl.seed + 307, period, p["direction"])

    sway = tl.waves(period * 0.22, tr["lane"] * 2.7)
    sway2 = tl.waves(period * 0.13, tr["extra"] * 3.1)
    x = x + (sway * 0.7 + sway2 * 0.3) * float(p["sway"]) * 0.05

    px = x * w + offset[0]
    py = y * h + offset[1]
    near = 0.35 + 0.65 * tr["size"]
    rad = np.maximum(0.8, float(p["size"]) * 0.011 * min(h, w) * near)
    rgb = tuple(int(str(p["color"]).lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    return common.glow(
        frame, px, py, rad * 2.0, rgb, float(p["opacity"]) * near * 0.8, mask
    )
