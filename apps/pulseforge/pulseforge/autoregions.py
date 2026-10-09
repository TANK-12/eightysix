"""
Guessing where the moving parts of a picture are.

Marking regions by hand is the slow part of building a shot, and most
backgrounds are made of the same few things: sky at the top, water below the
horizon, foliage in the greens, and a handful of bright spots that want to
glow. This looks for those and proposes a region plus the effect that usually
belongs on it, so a new background can be animated in one click and then
corrected by hand rather than started from nothing.

It is deliberately a *suggestion*. Everything it returns is an ordinary brush
region that the editor can paint over, and every effect it picks is one the
user can change. Nothing here is clever enough to be trusted blindly, and the
editor never applies it without being asked.

The work happens on a downsampled copy -- a 128-pixel-wide thumbnail is plenty
to tell sky from water, and it keeps the whole thing instant.
"""

import numpy as np
from PIL import Image

from . import imageops

THUMB_W = 128


def _analyse(path):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    tw = THUMB_W
    th = max(8, int(round(h * tw / max(1, w))))
    small = np.asarray(im.resize((tw, th), Image.Resampling.BILINEAR), dtype=np.float32)
    r, g, b = small[..., 0], small[..., 1], small[..., 2]
    mx = small.max(axis=2)
    mn = small.min(axis=2)
    value = mx / 255.0
    sat = np.where(mx > 1, (mx - mn) / np.maximum(1.0, mx), 0.0)
    # local busyness: how far each pixel sits from a blurred version of itself
    soft = imageops.box_blur(small, 3, passes=1)
    texture = np.abs(small - soft).mean(axis=2) / 255.0
    ys = np.linspace(0.0, 1.0, th, dtype=np.float32)[:, None]
    ys = np.broadcast_to(ys, (th, tw))
    return dict(
        small=small,
        r=r,
        g=g,
        b=b,
        value=value,
        sat=sat,
        texture=texture,
        ys=ys,
        h=th,
        w=tw,
    )


def _clean(mask, radius=2, keep=0.45):
    """Blur-and-threshold: drops speckle and closes small holes without scipy."""
    m = imageops.box_blur(mask.astype(np.float32), radius, passes=2)
    return (m > keep).astype(np.float32)


def _from_edge(mask, edge="bottom"):
    """Keep only the unbroken run reaching in from one edge of the frame.

    Sky touches the top of the picture and water touches the bottom; things
    that merely look similar -- a grey mountain, a patch of pale wall -- usually
    do not. Running a cumulative product up (or down) each column is a cheap
    way to say "connected to that edge" without pulling in scipy.
    """
    m = mask if edge == "top" else np.flip(mask, axis=0)
    run = np.cumprod(np.clip(m, 0.0, 1.0) > 0.5, axis=0).astype(np.float32)
    return run if edge == "top" else np.flip(run, axis=0)


def _horizon(a):
    """Row where the sky most likely stops: the biggest drop in blueness."""
    blueness = (a["b"] - (a["r"] + a["g"]) * 0.5).mean(axis=1)
    if len(blueness) < 6:
        return 0.5
    d = blueness[:-1] - blueness[1:]
    top = int(np.argmax(d[: max(1, int(len(d) * 0.85))]))
    return float(top + 1) / a["h"]


def _candidates(a):
    hz = _horizon(a)
    blue = (a["b"] - np.maximum(a["r"], a["g"])) / 255.0
    green = (a["g"] - np.maximum(a["r"], a["b"])) / 255.0

    sky = (
        (a["ys"] < max(0.22, hz + 0.04))
        & (a["texture"] < 0.06)
        & ((blue > 0.02) | ((a["value"] > 0.55) & (a["sat"] < 0.25)))
    )
    # Water is one colour field reaching the bottom of the frame, so compare
    # against what is actually down there rather than against "blueish". This
    # is what keeps a dark blue-grey hillside out of the lake.
    floor = np.median(a["small"][int(int(a["h"]) * 0.95) :].reshape(-1, 3), axis=0)
    like_floor = np.linalg.norm(a["small"] - floor, axis=2) / 255.0
    water = (
        (a["ys"] > max(0.30, hz - 0.02))
        & (a["texture"] < 0.09)
        & (like_floor < 0.16)
        & ((blue > 0.01) | ((a["sat"] < 0.30) & (a["value"] < 0.65)))
    )
    foliage = (green > 0.03) & (a["sat"] > 0.12)
    glow = a["value"] > max(0.86, float(np.quantile(a["value"], 0.995)) - 0.02)

    return [
        (
            "sky",
            "sky_clouds",
            _from_edge(_clean(sky, 2), "top"),
            {"amount": 0.45, "speed": 0.22},
        ),
        (
            "water",
            "water",
            _from_edge(_clean(water, 2), "bottom"),
            {"strength": 0.3, "speed": 0.28},
        ),
        (
            "foliage",
            "sway",
            _clean(foliage, 2),
            {"strength": 0.22, "anchor": "bottom", "speed": 0.28},
        ),
        (
            "lights",
            "glow_pulse",
            _clean(glow, 1, keep=0.3),
            {"strength": 0.3, "speed": 0.15},
        ),
    ]


def suggest(path, min_coverage=0.012, max_coverage=0.92):
    """Regions worth offering for this image.

    Returns a list of `{name, effect, params, coverage, mask}` where `mask` is a
    float array at thumbnail size. The caller scales it up and saves it as a
    brush PNG; keeping the array small here means this stays instant even on a
    4K background.
    """
    a = _analyse(path)
    out = []
    claimed = np.zeros((int(a["h"]), int(a["w"])), dtype=np.float32)
    for name, effect, mask, params in _candidates(a):
        # earlier, more confident regions win the overlap
        mask = mask * (1.0 - claimed)
        cov = float(mask.mean())
        if cov < min_coverage or cov > max_coverage:
            continue
        claimed = np.clip(claimed + mask, 0.0, 1.0)
        out.append(
            {
                "name": name,
                "effect": effect,
                "params": params,
                "coverage": round(cov, 4),
                "mask": mask,
            }
        )
    return out


def mask_to_png(mask, path, out_w, out_h, feather_px=6):
    """Save a thumbnail-sized mask as a full-size brush PNG for the editor."""
    m = np.clip(mask, 0.0, 1.0)
    im = Image.fromarray((m * 255).astype(np.uint8)).resize(
        (int(out_w), int(out_h)), Image.Resampling.BILINEAR
    )
    arr = imageops.box_blur(np.asarray(im, dtype=np.float32), int(feather_px), passes=2)
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(str(path))
    return str(path)
