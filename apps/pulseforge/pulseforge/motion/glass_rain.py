"""Rain on glass -- droplets bending the picture behind them."""

import numpy as np

from .. import imageops
from . import common

EFFECT = {
    "id": "glass_rain",
    "label": "Rain on glass",
    "family": "geometry",
    "description": "Droplets on a window, each one a little lens bending the "
    "picture behind it. Some cling and tremble, some slide down. "
    "The falling-rain sprites can't do this -- the whole point "
    "here is the refraction.",
    "params": [
        common.strength(0.6, "Lens strength"),
        {
            "key": "count",
            "label": "How many drops",
            "type": "int",
            "default": 90,
            "min": 1,
            "max": 500,
            "step": 1,
        },
        common.amount("size", 0.35, "Drop size", 1.0),
        common.amount("size_variation", 0.7, "Size variation", 1.0),
        common.speed(0.3, "Slide speed"),
        common.amount("sliding", 0.35, "Fraction that slide", 1.0),
        common.amount("rim", 0.4, "Rim light", 1.0),
        common.amount("fog", 0.15, "Fogging", 1.0),
    ],
}

_DROP_CACHE: dict = {}


def _drops(seed, n):
    key = (int(seed), int(n))
    hit = _DROP_CACHE.get(key)
    if hit is None:
        rng = np.random.default_rng(int(seed) * 7717 + 13)
        hit = {
            "x": rng.random(n).astype(np.float32),
            "y": rng.random(n).astype(np.float32),
            "size": rng.random(n).astype(np.float32),
            "phase": rng.random(n).astype(np.float32),
            "roll": rng.random(n).astype(np.float32),
        }
        if len(_DROP_CACHE) > 16:
            _DROP_CACHE.clear()
        _DROP_CACHE[key] = hit
    return hit


def apply(frame, mask, box, tl, p, ctx):
    y0, y1, x0, x1 = box
    bh, bw = y1 - y0, x1 - x0
    if bh < 4 or bw < 4:
        return frame

    n = max(1, int(p["count"]))
    d = _drops(tl.seed + 4409, n)
    period = common.period_from_speed(p["speed"], slowest=40.0, fastest=5.0)

    slides = d["roll"] < float(p["sliding"])
    # sliding drops run down and re-enter at the top; clinging ones only tremble
    travel = tl.saws(period, d["phase"], rate=1.0 + np.rint(d["size"] * 2.0))
    ys = np.where(slides, (d["y"] + travel) % 1.0, d["y"])
    tremble = tl.waves(period * 0.23, d["phase"] * 5.0) * 0.0016
    xs = d["x"] + np.where(slides, 0.0, tremble)

    base_r = float(p["size"]) * 0.045 * min(bh, bw)
    var = float(p["size_variation"])
    radii = np.maximum(1.5, base_r * (1.0 - var * 0.7 + d["size"] * var * 1.6))

    dx = np.zeros((bh, bw), dtype=np.float32)
    dy = np.zeros((bh, bw), dtype=np.float32)
    rim = np.zeros((bh, bw), dtype=np.float32)
    lens = float(p["strength"])
    rim_amt = float(p["rim"])

    px = xs * bw
    py = ys * bh
    for k in range(n):
        r = float(radii[k])
        cx, cy = float(px[k]), float(py[k])
        a0, a1 = max(0, int(cy - r)), min(bh, int(cy + r) + 1)
        b0, b1 = max(0, int(cx - r)), min(bw, int(cx + r) + 1)
        if a1 <= a0 or b1 <= b0:
            continue
        gy = np.arange(a0, a1, dtype=np.float32)[:, None] - cy
        gx = np.arange(b0, b1, dtype=np.float32)[None, :] - cx
        rr = np.sqrt(gx * gx + gy * gy) / r
        inside = rr < 1.0
        if not inside.any():
            continue
        # a droplet magnifies: sample nearer its centre the further out you are
        pull = np.where(inside, (1.0 - np.sqrt(np.clip(1.0 - rr * rr, 0, 1))), 0.0)
        pull = (pull * lens * 1.6).astype(np.float32)
        dx[a0:a1, b0:b1] -= gx * pull
        dy[a0:a1, b0:b1] -= gy * pull
        if rim_amt > 0.001:
            edge = np.where(inside, np.clip((rr - 0.62) / 0.38, 0.0, 1.0) ** 2, 0.0)
            rim[a0:a1, b0:b1] += edge.astype(np.float32) * rim_amt

    fog = float(p["fog"])
    if fog > 0.001:
        r = max(1, int(fog * 0.012 * min(bh, bw)))
        soft = imageops.box_blur(frame[y0:y1, x0:x1], r, passes=1)
        region = frame[y0:y1, x0:x1]
        # through the mask, not across the whole box -- the box is padded past
        # the region and the glass must not fog the wall around the window
        a = (fog * 0.85) * mask[y0:y1, x0:x1][..., None]
        region *= 1.0 - a
        region += soft * a

    imageops.displace(frame, dx=dx, dy=dy, mask=mask, box=box, fast=ctx.fast)

    if rim_amt > 0.001:
        region = frame[y0:y1, x0:x1]
        region += (np.clip(rim, 0.0, 1.5) * 70.0 * mask[y0:y1, x0:x1])[..., None]
        np.clip(region, 0.0, 255.0, out=region)
    return frame
