"""Glow -- neon signs, lit windows, lanterns, screens, embers."""

import numpy as np

from .. import imageops, overlay
from . import common

EFFECT = {
    "id": "glow_pulse",
    "label": "Glow",
    "family": "light",
    "description": "Lifts the region's brightness in a slow swell, with an "
    "optional soft bloom spilling past its edges. Can be driven "
    "by the music instead of the clock. For neon, lit windows "
    "and lanterns.",
    "params": [
        common.strength(0.35),
        common.speed(0.2),
        common.radius(0.3, "Bloom"),
        {"key": "tint", "label": "Tint", "type": "color", "default": "#ffd9a0"},
        {
            "key": "drive",
            "label": "Driven by",
            "type": "select",
            "default": "clock",
            "options": ["clock", "energy", "sub", "onset"],
            "help": "Anything but 'clock' needs Live mode -- a loop has no song "
            "position to read.",
        },
        common.amount("floor", 0.35, "Base level", 1.0),
    ],
}


def apply(frame, mask, box, tl, p, ctx):
    y0, y1, x0, x1 = box
    bh, bw = y1 - y0, x1 - x0
    if bh < 2 or bw < 2:
        return frame

    drive = str(p["drive"])
    if drive == "clock":
        period = common.period_from_speed(p["speed"], slowest=20.0, fastest=1.5)
        level = 0.5 + 0.5 * tl.wave(period)
    else:
        level = tl.audio(drive, default=0.5)
    level = float(p["floor"]) + (1.0 - float(p["floor"])) * float(level)

    tint = np.array(overlay.hex_rgb(str(p["tint"])), dtype=np.float32) / 255.0
    m = mask[y0:y1, x0:x1]
    lift = (m * level * float(p["strength"]) * 110.0)[..., None] * tint
    region = frame[y0:y1, x0:x1]
    region[...] = np.clip(region + lift, 0.0, 255.0)

    bloom = float(p["radius"])
    if bloom > 0.01:
        # spill past the region, so the light looks like it is in the air
        r = max(2, int(bloom * 0.12 * min(frame.shape[0], frame.shape[1])))
        pad = r * 2
        py0, py1 = max(0, y0 - pad), min(frame.shape[0], y1 + pad)
        px0, px1 = max(0, x0 - pad), min(frame.shape[1], x1 + pad)
        halo = imageops.box_blur(mask[py0:py1, px0:px1] * level, r, passes=2)
        glow = (halo * float(p["strength"]) * 70.0)[..., None] * tint
        big = frame[py0:py1, px0:px1]
        big[...] = np.clip(big + glow, 0.0, 255.0)
    return frame
