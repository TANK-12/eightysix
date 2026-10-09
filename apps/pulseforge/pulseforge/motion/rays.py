"""Light rays -- shafts through cloud, trees, a window, water."""

import math

import numpy as np

from .. import imageops, overlay
from . import common

EFFECT = {
    "id": "rays",
    "label": "Light rays",
    "family": "light",
    "description": "Shafts of light fanning out from a point, drifting and "
    "breathing. Through gaps in cloud, between trees, in from a "
    "window, or down through water.",
    "params": [
        common.strength(0.35),
        {
            "key": "count",
            "label": "How many shafts",
            "type": "int",
            "default": 7,
            "min": 1,
            "max": 40,
            "step": 1,
        },
        common.speed(0.15, "Drift"),
        common.direction(270, "Pointing"),
        {
            "key": "spread",
            "label": "Fan width",
            "type": "range",
            "default": 70,
            "min": 5,
            "max": 360,
            "step": 1,
            "unit": "°",
        },
        {
            "key": "length",
            "label": "Reach",
            "type": "range",
            "default": 0.7,
            "min": 0.1,
            "max": 2.0,
            "step": 0.01,
        },
        common.amount("softness", 0.5, "Softness", 1.0),
        {
            "key": "source_x",
            "label": "Source across",
            "type": "range",
            "default": 0.5,
            "min": -0.5,
            "max": 1.5,
            "step": 0.01,
        },
        {
            "key": "source_y",
            "label": "Source down",
            "type": "range",
            "default": 0.0,
            "min": -0.5,
            "max": 1.5,
            "step": 0.01,
        },
        {"key": "tint", "label": "Tint", "type": "color", "default": "#ffeccc"},
    ],
}

_GEOM_CACHE: dict = {}


def _geometry(box, frame_shape, sx, sy, length, spread, facing):
    """Angle, falloff and the cone mask for every pixel in the box.

    None of this changes from frame to frame -- only the phase does -- so it is
    computed once per shot and cached. `arctan2` over a full-frame region every
    frame would otherwise dominate the effect's cost.
    """
    h, w = frame_shape
    key = (
        box,
        h,
        w,
        round(sx, 3),
        round(sy, 3),
        round(length, 3),
        round(spread, 1),
        round(facing, 1),
    )
    hit = _GEOM_CACHE.get(key)
    if hit is not None:
        return hit

    y0, y1, x0, x1 = box
    px, py = sx * w, sy * h
    ys = np.arange(y0, y1, dtype=np.float32)[:, None] - py
    xs = np.arange(x0, x1, dtype=np.float32)[None, :] - px
    ang = np.arctan2(ys, xs).astype(np.float32)
    dist = np.sqrt(xs * xs + ys * ys).astype(np.float32)

    reach = length * math.hypot(w, h)
    falloff = np.clip(1.0 - dist / max(1.0, reach), 0.0, 1.0) ** 1.6

    # keep the light inside a fan rather than a full circle
    fx, fy = imageops.direction_vector(facing)
    facing_rad = math.atan2(fy, fx)
    delta = np.abs(np.arctan2(np.sin(ang - facing_rad), np.cos(ang - facing_rad)))
    half = math.radians(max(1.0, spread)) * 0.5
    cone = np.clip(1.0 - (delta / half) ** 2, 0.0, 1.0).astype(np.float32)

    out = (ang, (falloff * cone).astype(np.float32))
    if len(_GEOM_CACHE) > 6:
        _GEOM_CACHE.clear()
    _GEOM_CACHE[key] = out
    return out


def apply(frame, mask, box, tl, p, ctx):
    y0, y1, x0, x1 = box
    if y1 <= y0 or x1 <= x0:
        return frame

    ang, falloff = _geometry(
        box,
        frame.shape[:2],
        float(p["source_x"]),
        float(p["source_y"]),
        float(p["length"]),
        float(p["spread"]),
        float(p["direction"]),
    )

    n = max(1, int(p["count"]))
    period = common.period_from_speed(p["speed"], slowest=140.0, fastest=20.0)
    # whole-number harmonics of the angle, so there is no seam where the angle
    # wraps from +pi to -pi
    turn = 2 * np.pi * tl.phase(period)
    beams = np.sin(ang * n + turn)
    beams += 0.55 * np.sin(ang * (n * 2 + 1) - 2 * np.pi * tl.phase(period * 0.61))

    soft = float(p["softness"])
    beams = np.clip(beams / 1.55, -1.0, 1.0)
    beams = (beams * 0.5 + 0.5) ** (1.0 + 6.0 * (1.0 - soft))

    breathe = 0.75 + 0.25 * tl.wave(period * 0.43, offset=0.2)
    light = (beams * falloff * (float(p["strength"]) * 150.0 * breathe)).astype(
        np.float32
    )
    light *= mask[y0:y1, x0:x1]

    tint = np.array(overlay.hex_rgb(str(p["tint"])), dtype=np.float32) / 255.0
    region = frame[y0:y1, x0:x1]
    region += light[..., None] * tint
    np.clip(region, 0.0, 255.0, out=region)
    return frame
