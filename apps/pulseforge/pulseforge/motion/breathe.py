"""Breathe -- a slow swell in and out of a region."""

from .. import imageops
from . import common

EFFECT = {
    "id": "breathe",
    "label": "Breathe",
    "family": "geometry",
    "description": "Scales the region gently in and out around a point. Reads "
    "as something alive without any part of it obviously moving. "
    "For chests, foliage masses, steam and glowing things.",
    "params": [
        common.strength(0.25),
        common.speed(0.15),
        {
            "key": "centre_x",
            "label": "Centre across",
            "type": "range",
            "default": 0.5,
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
        },
        {
            "key": "centre_y",
            "label": "Centre down",
            "type": "range",
            "default": 0.5,
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
        },
    ],
}


def apply(frame, mask, box, tl, p, ctx):
    period = common.period_from_speed(p["speed"], slowest=24.0, fastest=3.0)
    scale = 1.0 + float(p["strength"]) * 0.06 * tl.wave(period)
    dx, dy = imageops.zoom_field(
        box, scale, cx=float(p["centre_x"]), cy=float(p["centre_y"])
    )
    return imageops.displace(frame, dx=dx, dy=dy, mask=mask, box=box, fast=ctx.fast)
