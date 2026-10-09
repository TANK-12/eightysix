"""Stars -- fixed points that twinkle. For a sky region."""

import numpy as np

from . import common

EMITTER = {
    "id": "stars",
    "label": "Stars",
    "family": "particles",
    "description": "Points that stay put and vary in brightness, each on its "
    "own rhythm. Give it a sky region so they do not appear over "
    "the ground.",
    "params": [
        common.count(160, 900),
        common.amount("twinkle", 0.6, "Twinkle", 1.0),
        common.speed(0.3, "Twinkle rate"),
        common.size(0.22),
        common.amount("drift", 0.0, "Drift", 1.0),
        common.color("#eaf2ff"),
        common.amount("opacity", 0.8, "Opacity", 1.0),
    ],
}


def draw(frame, tl, p, ctx, mask=None, offset=(0.0, 0.0)):
    h, w = frame.shape[:2]
    n = int(p["count"])
    tr = common.traits(tl.seed + 701, n)
    period = common.period_from_speed(p["speed"], slowest=30.0, fastest=2.5)

    x = tr["lane"]
    y = tr["extra"]
    drift = float(p["drift"])
    if drift > 0.001:
        # the whole sky turning slowly, as it would over a long take
        x = (x + tl.saw(period * 24.0) * drift * 0.5) % 1.0

    tw = float(p["twinkle"])
    level = (1.0 - tw) + tw * np.clip(
        0.5 + 0.5 * tl.waves(period, tr["phase"] * 8.0), 0, 1
    )
    px = x * w + offset[0]
    py = y * h + offset[1]
    rad = np.maximum(0.6, float(p["size"]) * 0.009 * min(h, w) * (0.3 + tr["size"]))
    rgb = tuple(int(str(p["color"]).lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    return common.glow(
        frame, px, py, rad * 2.5, rgb, float(p["opacity"]) * level * 0.75, mask
    )
