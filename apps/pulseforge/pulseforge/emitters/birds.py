"""Birds -- a few crossing the frame, wings beating."""

import numpy as np

from .. import artsource
from . import common

EMITTER = {
    "id": "birds",
    "label": "Birds",
    "family": "creatures",
    "description": "Silhouettes crossing the frame with a wingbeat, the far "
    "ones smaller, paler and slower. Optionally in a loose V.",
    "params": [
        common.count(7, 60),
        common.speed(0.3),
        common.direction(5),
        common.size(0.3),
        common.amount("flap", 0.6, "Wingbeat rate", 1.0),
        common.amount("formation", 0.0, "V formation", 1.0),
        common.amount("depth_fade", 0.6, "Distance fade", 1.0),
        common.color("#2a2a33"),
        common.amount("opacity", 0.85, "Opacity", 1.0),
        common.amount("height", 0.35, "Height in frame", 1.0),
        common.amount("band", 0.4, "Spread", 1.0),
    ],
}


def draw(frame, tl, p, ctx, mask=None, offset=(0.0, 0.0)):
    h, w = frame.shape[:2]
    n = int(p["count"])
    period = common.period_from_speed(p["speed"], slowest=90.0, fastest=14.0)
    x, y, prog, tr = common.crossing_path(
        tl, n, tl.seed + 907, period, p["direction"], margin=0.2
    )

    # sit them in a band rather than all over the frame
    y = float(p["height"]) + (tr["lane"] - 0.5) * float(p["band"])
    form = float(p["formation"])
    if form > 0.001:
        rank = np.arange(n, dtype=np.float32) / max(1, n - 1)
        side = np.where(np.arange(n) % 2 == 0, 1.0, -1.0).astype(np.float32)
        x = x - rank * form * 0.12
        y = y + rank * side * form * 0.09

    y = y + tl.waves(period * 0.11, tr["extra"] * 2.0) * 0.02
    near = 0.35 + 0.65 * tr["size"]
    flapph = tl.saws(period * (0.03 + 0.05 * (1.0 - float(p["flap"]))), tr["phase"])

    base = float(p["size"]) * 0.06 * min(h, w)
    rgb = tuple(int(str(p["color"]).lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    fade = float(p["depth_fade"])
    px = x * w + offset[0]
    py = y * h + offset[1]
    for k in range(n):
        s = max(3, int(base * near[k]))
        sp = common.shape_sprite("bird", s, max(2, int(s * 0.55)), rgb, phase=flapph[k])
        artsource.blit(
            frame,
            sp,
            px[k] - sp.shape[1] / 2,
            py[k] - sp.shape[0] / 2,
            opacity=float(p["opacity"]) * (1.0 - fade + fade * float(near[k])),
            mask=mask,
        )
    return frame
