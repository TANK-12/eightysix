"""Scope -- a glowing harmonograph trace drawn by the spectrum.

There is no raw waveform in the feature track, so the trace is built the
way a harmonograph is: a few sine pendulums on each axis, one per band
group, whose sizes are the live band levels. Quiet music draws a small,
calm loop; a busy mix folds it into dense Lissajous knots. Points land in a
phosphor buffer that fades a little each frame, so the trace leaves glowing
trails like an old oscilloscope:

    shape      band levels size each pendulum; slow drift keeps it turning
    colour     shifts between the two colours with the track's brightness
    kicks      a beat flashes the phosphor and thickens the line
"""

import numpy as np

from .. import overlay as ov

SCENE = {
    "id": "scope",
    "label": "Harmonograph Scope",
    "family": "visualizer",
    "description": "An oscilloscope-style glowing trace that the music folds into "
    "Lissajous knots, with phosphor trails and a flash on every kick.",
    "params": [
        {
            "key": "color_a",
            "label": "Colour (dark songs)",
            "type": "color",
            "default": "#39ff9e",
        },
        {
            "key": "color_b",
            "label": "Colour (bright songs)",
            "type": "color",
            "default": "#ffd23b",
        },
        {"key": "bg", "label": "Background", "type": "color", "default": "#020806"},
        {
            "key": "trail",
            "label": "Trail length",
            "type": "float",
            "default": 0.86,
            "min": 0.5,
            "max": 0.97,
        },
        {
            "key": "size",
            "label": "Size",
            "type": "float",
            "default": 0.8,
            "min": 0.3,
            "max": 1.0,
        },
        {"key": "grid", "label": "Scope grid", "type": "bool", "default": True},
        {
            "key": "flash",
            "label": "Kick flash",
            "type": "float",
            "default": 1.0,
            "min": 0.0,
            "max": 1.0,
        },
    ],
}

POINTS = 6000
FREQ_X = np.array([1.0, 2.0, 3.0, 5.0], dtype=np.float32)
FREQ_Y = np.array([1.5, 2.0, 4.0, 6.0], dtype=np.float32)


def _grid(h, w):
    g = np.zeros((h, w), dtype=np.float32)
    for k in range(1, 10):
        g[int(h * k / 10), :] = 0.10
        g[:, int(w * k / 10)] = 0.10
    g[h // 2, :] = g[:, w // 2] = 0.2
    return g


def frames(ctx):
    h, w = ctx.h, ctx.w
    ca = np.array(ov.hex_rgb(ctx.p("color_a")), dtype=np.float32)
    cb = np.array(ov.hex_rgb(ctx.p("color_b")), dtype=np.float32)
    bg = np.array(ov.hex_rgb(ctx.p("bg")), dtype=np.float32)
    trail = float(ctx.p("trail", 0.86))
    size = float(ctx.p("size", 0.8)) * 0.92 * h / 2.0
    flash_amt = float(ctx.p("flash", 1.0))
    grid = _grid(h, w) if ctx.p("grid", True) else np.zeros((h, w), np.float32)
    bands = np.asarray(ctx.feat["bands"], dtype=np.float32)
    groups = np.array_split(np.arange(bands.shape[1]), len(FREQ_X))
    u = np.linspace(0.0, 2.0 * np.pi * 3.0, POINTS, dtype=np.float32)
    phos = np.zeros((h, w), dtype=np.float32)
    flash = 0.0

    for i in range(ctx.n_frames):
        t = i / ctx.fps
        row = bands[min(i, len(bands) - 1)]
        amp = np.array([row[g].mean() for g in groups], dtype=np.float32) + 0.08
        amp /= amp.sum()
        x = (
            amp[:, None] * np.sin(FREQ_X[:, None] * u + 0.37 * t * FREQ_X[:, None])
        ).sum(0)
        y = (
            amp[:, None] * np.cos(FREQ_Y[:, None] * u + 0.23 * t * FREQ_Y[:, None])
        ).sum(0)
        beat = bool(ctx.frame_feat("beat", i))
        flash = max(flash * 0.8, 1.0 if beat else 0.0)
        # Centre the knot and fit it to the frame; loudness sets how much of
        # the frame it fills, so quiet passages draw a small calm loop.
        x, y = x - x.mean(), y - y.mean()
        reach = float(max(np.abs(x).max(), np.abs(y).max(), 1e-6))
        energy = float(ctx.frame_feat("energy", i))
        grow = size * (0.4 + 0.6 * min(1.0, energy * 1.4)) / reach
        px = np.clip((w / 2 + x * grow * w / h).astype(np.int32), 0, w - 1)
        py = np.clip((h / 2 + y * grow).astype(np.int32), 0, h - 1)
        phos *= trail
        np.add.at(phos, (py, px), 0.35 + 0.4 * flash)
        if flash > 0.3:  # a thicker line on kicks
            np.add.at(phos, (np.minimum(py + 1, h - 1), px), 0.25 * flash)
            np.add.at(phos, (py, np.minimum(px + 1, w - 1)), 0.25 * flash)
        glow = (
            phos
            + 0.5
            * (
                np.roll(phos, 1, 0)
                + np.roll(phos, -1, 0)
                + np.roll(phos, 1, 1)
                + np.roll(phos, -1, 1)
            )
            / 4.0
        )
        light = np.clip(glow, 0.0, 1.6)
        c = float(np.clip(ctx.frame_feat("centroid", i), 0.0, 1.0))
        colour = ca * (1.0 - c) + cb * c
        img = bg + colour * (light + grid)[..., None] + flash_amt * flash * 18.0
        yield np.clip(img, 0, 255).astype(np.uint8)
