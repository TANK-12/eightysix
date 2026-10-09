"""Water -- ponds, lakes, sea, puddles, reflections."""

import numpy as np

from .. import imageops
from . import common

EFFECT = {
    "id": "water",
    "label": "Water",
    "family": "geometry",
    "description": "Rolling ripples across the region, bigger toward the "
    "bottom of it the way real water reads in perspective, with "
    "optional light catching the crests. For ponds, lakes, sea "
    "and reflections.",
    "params": [
        common.strength(0.35),
        common.length(140.0),
        common.speed(0.3),
        common.direction(270),  # rolling toward the viewer
        common.amount("chop", 0.45, "Chop", 1.0),
        common.amount("glint", 0.25, "Glint", 1.0),
    ],
}


def apply(frame, mask, box, tl, p, ctx):
    y0, y1, x0, x1 = box
    bh = y1 - y0
    gy, _gx = imageops.grid(box)

    ux, uy = imageops.direction_vector(p["direction"])
    wl = max(8.0, float(p["wave_length"]))
    xs = np.arange(x0, x1, dtype=np.float32)[None, :]
    ys = np.arange(y0, y1, dtype=np.float32)[:, None]
    # Ripples crowd together toward the far edge of the water and open out as
    # they come toward the viewer. Without this the region reads as flat bands
    # rather than as a surface going away from you.
    squeeze = 0.35 + 0.65 * gy
    u = np.cumsum(np.broadcast_to(1.0 / (wl * squeeze), (y1 - y0, 1)), axis=0)
    u = u * uy + (xs * ux) / wl

    period = common.period_from_speed(p["speed"], slowest=16.0, fastest=1.5)
    ph1 = tl.phase(period)
    ph2 = tl.phase(period * 0.63, offset=0.31)

    # near water has bigger waves than far water
    perspective = (0.25 + 0.75 * gy).astype(np.float32)
    # `u - phase` so the crests travel *along* the stated direction
    w1 = np.sin(2 * np.pi * (u - ph1)).astype(np.float32)
    w2 = np.sin(2 * np.pi * (u * 1.87 + ph2)).astype(np.float32)

    amp = float(p["strength"]) * 0.055 * bh
    disp = amp * perspective * (w1 + float(p["chop"]) * w2)
    imageops.displace(frame, dx=disp * 0.3, dy=disp, mask=mask, box=box, fast=ctx.fast)

    glint = float(p["glint"])
    if glint > 0.001:
        crest = np.clip(w1, 0.0, 1.0) ** 8
        light = (crest * perspective * glint * 90.0)[..., None]
        m = mask[y0:y1, x0:x1][..., None]
        region = frame[y0:y1, x0:x1]
        region[...] = np.clip(region + light * m, 0.0, 255.0)
    return frame
