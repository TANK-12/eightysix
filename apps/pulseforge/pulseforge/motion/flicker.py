"""Flicker -- candles, fire, televisions, failing neon."""

import numpy as np

from .. import overlay
from . import common

EFFECT = {
    "id": "flicker",
    "label": "Flicker",
    "family": "light",
    "description": "Irregular jumps in brightness rather than a smooth pulse. "
    "The randomness is drawn once and replayed, so it stays "
    "irregular but still comes back to the start of the loop.",
    "params": [
        common.strength(0.35),
        common.speed(0.55, "Rate"),
        common.amount("smoothness", 0.4, "Smoothness", 1.0),
        {"key": "tint", "label": "Tint", "type": "color", "default": "#ffc27a"},
    ],
}

_SEQ_CACHE: dict = {}


def _sequence(steps, seed):
    """A ring of random levels. Indexing it by a wrapped phase is what lets
    something genuinely jittery still be loop-exact."""
    key = (steps, seed)
    seq = _SEQ_CACHE.get(key)
    if seq is None:
        rng = np.random.default_rng(seed)
        seq = rng.random(steps).astype(np.float32)
        _SEQ_CACHE[key] = seq
    return seq


def apply(frame, mask, box, tl, p, ctx):
    y0, y1, x0, x1 = box
    rate = 2.0 + 22.0 * float(p["speed"])
    steps = max(2, int(round(tl.loop_s * rate)))
    seq = _sequence(steps, tl.seed + 977)

    pos = tl.saw(tl.loop_s) * steps  # one pass through the ring per loop
    i0 = int(pos) % steps
    i1 = (i0 + 1) % steps
    frac = pos - int(pos)
    smooth = float(p["smoothness"])
    blend = (frac * frac * (3 - 2 * frac)) * smooth  # 0 = hard steps
    level = seq[i0] * (1.0 - blend) + seq[i1] * blend

    swing = float(p["strength"])
    gain = 1.0 - swing * 0.5 + swing * float(level)
    tint = np.array(overlay.hex_rgb(str(p["tint"])), dtype=np.float32) / 255.0
    m = mask[y0:y1, x0:x1][..., None]
    region = frame[y0:y1, x0:x1]
    lit = np.clip(region * (gain * tint + (1.0 - tint)), 0.0, 255.0)
    region[...] = region * (1.0 - m) + lit * m
    return frame
