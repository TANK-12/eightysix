"""
Shared particle machinery.

The awkward part of particles in a looping render is that they must not be
*state*. If a raindrop's position came from adding a little each frame, the loop
would never close. So instead every particle is a pure function of time:

* its fixed traits (lane, size, speed jitter, phase offset) are drawn once from
  a seeded RNG in `traits()`, cached per emitter,
* its position comes from `travel()`, a loop-wrapped ramp,

which means frame zero and frame N are identical by construction, and any frame
can be rendered without having rendered the ones before it.

Drawing happens two ways. Many small marks (rain, snow, dust) go into one PIL
overlay per frame and composite in a single pass; a few larger shapes (birds,
fish, leaves) blit cached sprites. Both end up alpha-composited through the
optional region mask.
"""

import math

import numpy as np
from PIL import Image, ImageDraw

from .. import imageops, overlay

_TRAITS_CACHE: dict = {}
_SPRITE_CACHE: dict = {}


# --------------------------------------------------------------------------
# parameter builders shared across emitters
# --------------------------------------------------------------------------
def count(default=60, maximum=600, label="How many"):
    return {
        "key": "count",
        "label": label,
        "type": "int",
        "default": default,
        "min": 1,
        "max": maximum,
        "step": 1,
    }


def speed(default=0.35, label="Speed"):
    return {
        "key": "speed",
        "label": label,
        "type": "range",
        "default": default,
        "min": 0.0,
        "max": 1.0,
        "step": 0.01,
    }


def direction(default=270, label="Direction"):
    return {
        "key": "direction",
        "label": label,
        "type": "angle",
        "default": default,
        "min": 0,
        "max": 359,
        "step": 1,
    }


def size(default=0.3, label="Size", maximum=1.0):
    return {
        "key": "size",
        "label": label,
        "type": "range",
        "default": default,
        "min": 0.0,
        "max": maximum,
        "step": 0.01,
    }


def amount(key, default, label, maximum=1.0, step=0.01):
    return {
        "key": key,
        "label": label,
        "type": "range",
        "default": default,
        "min": 0.0,
        "max": maximum,
        "step": step,
    }


def color(default="#ffffff", label="Colour"):
    return {"key": "color", "label": label, "type": "color", "default": default}


def period_from_speed(sp, slowest=40.0, fastest=3.0):
    sp = min(1.0, max(0.0, float(sp)))
    return slowest + (fastest - slowest) * sp


# --------------------------------------------------------------------------
# particles as a pure function of time
# --------------------------------------------------------------------------
def traits(seed, n, keys=("lane", "phase", "size", "rate", "extra")):
    """Per-particle constants, drawn once and cached. Never per frame -- a
    particle has to keep the same identity all the way through the loop."""
    key = (int(seed), int(n), tuple(keys))
    hit = _TRAITS_CACHE.get(key)
    if hit is None:
        rng = np.random.default_rng(int(seed) * 104729 + 17)
        hit = {k: rng.random(int(n)).astype(np.float32) for k in keys}
        if len(_TRAITS_CACHE) > 64:
            _TRAITS_CACHE.clear()
        _TRAITS_CACHE[key] = hit
    return hit


def travel(tl, period, offsets, rate=None):
    """Each particle's 0..1 progress along its path, wrapping with the loop."""
    return tl.saws(period, offsets, rate=rate)


def crossing_path(tl, n, seed, period, angle_deg, spread=1.0, margin=0.15):
    """Positions in 0..1 frame space for `n` things travelling in one direction
    and re-entering on the far side. Returns (x, y, progress)."""
    tr = traits(seed, n)
    ux, uy = imageops.direction_vector(angle_deg)
    prog = travel(tl, period, tr["phase"], rate=1.0 + np.rint(tr["rate"] * 2.0))
    span = 1.0 + 2.0 * margin
    along = -margin + prog * span
    across = (tr["lane"] - 0.5) * 2.0 * spread * 0.5 + 0.5
    # walk `along` down the travel direction and `across` perpendicular to it
    x = 0.5 + (along - 0.5) * ux - (across - 0.5) * uy
    y = 0.5 + (along - 0.5) * uy + (across - 0.5) * ux
    return x, y, prog, tr


# --------------------------------------------------------------------------
# drawing
# --------------------------------------------------------------------------
def canvas(h, w):
    im = Image.new("RGBA", (int(w), int(h)), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def composite(frame, im, opacity=1.0, mode="over", mask=None):
    """Flatten a PIL RGBA overlay onto the float32 frame in one pass."""
    arr = np.asarray(im, dtype=np.float32)
    a = (arr[..., 3:4] / 255.0) * float(opacity)
    if mask is not None:
        a = a * mask[..., None]
    rgb = arr[..., :3]
    if mode == "add":
        frame[...] = np.clip(frame + rgb * a, 0.0, 255.0)
    elif mode == "screen":
        frame[...] = 255.0 - (255.0 - frame) * (1.0 - a * (rgb / 255.0))
    else:
        frame[...] = frame * (1.0 - a) + rgb * a
    return frame


def glow(frame, xs, ys, radius, rgb, intensity, mask=None):
    """Soft additive dots, reusing the cached gaussian kernel in overlay.py."""
    if mask is not None:
        keep = (
            mask[
                np.clip(np.rint(ys), 0, frame.shape[0] - 1).astype(np.intp),
                np.clip(np.rint(xs), 0, frame.shape[1] - 1).astype(np.intp),
            ]
            > 0.15
        )
        xs, ys = xs[keep], ys[keep]
        intensity = np.asarray(intensity)[keep] if np.ndim(intensity) else intensity
        radius = np.asarray(radius)[keep] if np.ndim(radius) else radius
        if len(xs) == 0:
            return frame
    return overlay.glow_dots(frame, xs, ys, radius, rgb, intensity)


def shape_sprite(kind, w, h, rgb, phase=0.0, seed=0):
    """A small cached RGBA sprite. `phase` buckets an animation (a wingbeat, a
    tumbling leaf) so a whole render reuses a handful of images."""
    w, h = max(2, int(w)), max(2, int(h))
    bucket = int(round(float(phase) * 11)) % 12
    key = (kind, w, h, tuple(rgb), bucket, int(seed))
    hit = _SPRITE_CACHE.get(key)
    if hit is not None:
        return hit

    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    col = (int(rgb[0]), int(rgb[1]), int(rgb[2]), 255)
    ph = bucket / 12.0

    if kind == "bird":
        # a shallow M that flexes -- wings up at ph 0, down at ph 0.5
        flap = math.sin(2 * math.pi * ph)
        mid = h * (0.5 - 0.22 * flap)
        tip = h * (0.5 + 0.30 * flap)
        lw = max(1, int(round(h * 0.16)))
        d.line([(0, tip), (w * 0.28, mid), (w * 0.5, h * 0.5)], fill=col, width=lw)
        d.line([(w * 0.5, h * 0.5), (w * 0.72, mid), (w - 1, tip)], fill=col, width=lw)
    elif kind == "fish":
        d.ellipse([0, h * 0.22, w * 0.72, h * 0.78], fill=col)
        wag = math.sin(2 * math.pi * ph) * h * 0.22
        d.polygon(
            [
                (w * 0.66, h * 0.5),
                (w - 1, h * 0.5 - h * 0.3 + wag),
                (w - 1, h * 0.5 + h * 0.3 + wag),
            ],
            fill=col,
        )
    elif kind == "leaf":
        squash = abs(math.cos(math.pi * ph))  # tumbling edge-on and flat
        ww = max(1, int(w * (0.15 + 0.85 * squash)))
        off = (w - ww) // 2
        d.ellipse([off, 0, off + ww - 1, h - 1], fill=col)
    elif kind == "petal":
        squash = abs(math.cos(math.pi * ph))
        ww = max(1, int(w * (0.2 + 0.8 * squash)))
        off = (w - ww) // 2
        d.pieslice([off, 0, off + ww - 1, h * 2 - 1], 180, 360, fill=col)
    else:  # "dot"
        d.ellipse([0, 0, w - 1, h - 1], fill=col)

    arr = np.asarray(im, dtype=np.uint8)
    if len(_SPRITE_CACHE) > 400:
        _SPRITE_CACHE.clear()
    _SPRITE_CACHE[key] = arr
    return arr
