"""Tunnel -- the spectrum as rings rushing toward you.

Every pixel is read in polar space: its distance from the centre is depth
(1 / r), its angle picks a frequency band (mirrored left and right, so the
tunnel is symmetric). Rings sit at equal depth steps and slide outward as
the music plays, so they appear to fly past the viewer:

    speed      loudness drives how fast you travel
    rings      each ring is brighter where its band is loud
    bass       the sub band breathes the whole tunnel wider
    beats      fire a shockwave ring out of the centre
    centre     the vanishing point fades into a soft glow, never a hard dot
"""

import numpy as np

from .. import overlay as ov

SCENE = {
    "id": "tunnel",
    "label": "Spectrum Tunnel",
    "family": "visualizer",
    "description": "Rings of the spectrum rushing toward you through a tunnel. "
    "Loudness sets the speed, the bass breathes the walls, every beat fires "
    "a shockwave from the centre.",
    "params": [
        {
            "key": "color_a",
            "label": "Near colour",
            "type": "color",
            "default": "#ff4fd8",
        },
        {
            "key": "color_b",
            "label": "Far colour",
            "type": "color",
            "default": "#3b7bff",
        },
        {"key": "bg", "label": "Background", "type": "color", "default": "#05030c"},
        {
            "key": "rings",
            "label": "Rings",
            "type": "int",
            "default": 7,
            "min": 2,
            "max": 20,
        },
        {
            "key": "speed",
            "label": "Speed",
            "type": "float",
            "default": 1.0,
            "min": 0.1,
            "max": 4.0,
        },
        {
            "key": "spokes",
            "label": "Spokes",
            "type": "int",
            "default": 24,
            "min": 0,
            "max": 96,
        },
        {
            "key": "bass",
            "label": "Bass breathing",
            "type": "float",
            "default": 0.6,
            "min": 0.0,
            "max": 1.0,
        },
        {
            "key": "shock",
            "label": "Beat shockwave",
            "type": "float",
            "default": 1.0,
            "min": 0.0,
            "max": 1.0,
        },
    ],
}


def frames(ctx):
    h, w = ctx.h, ctx.w
    near = np.array(ov.hex_rgb(ctx.p("color_a")), dtype=np.float32)
    far = np.array(ov.hex_rgb(ctx.p("color_b")), dtype=np.float32)
    bg = np.array(ov.hex_rgb(ctx.p("bg")), dtype=np.float32)
    rings = float(ctx.p("rings", 7))
    speed = float(ctx.p("speed", 1.0))
    spokes = int(ctx.p("spokes", 24))
    bass_amt = float(ctx.p("bass", 0.6))
    shock_amt = float(ctx.p("shock", 1.0))

    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    half = min(h, w) / 2.0
    dx, dy = (xx - w / 2.0) / half, (yy - h / 2.0) / half
    r = np.sqrt(dx * dx + dy * dy) + 1e-3
    theta = np.arctan2(dy, dx)
    bands = np.asarray(ctx.feat["bands"], dtype=np.float32)
    nb = bands.shape[1]
    band_of = np.minimum(
        np.rint(np.abs(theta) / np.pi * (nb - 1)).astype(np.int32), nb - 1
    )
    # colour by depth, and a fade that hides the singular centre
    mix = np.clip(r / 1.2, 0.0, 1.0)[..., None]
    colour = far * (1.0 - mix) + near * mix
    centre_fade = np.clip(r * 2.2, 0.0, 1.0) ** 1.5
    spoke_mask = (
        0.75 + 0.25 * np.cos(theta * spokes) if spokes else np.ones_like(r)
    ).astype(np.float32)
    core = np.exp(-(r**2) / 0.02)[..., None]

    travel, shock_r, shock_on = 0.0, 0.0, 0.0
    for i in range(ctx.n_frames):
        energy = float(ctx.frame_feat("energy", i))
        sub = float(ctx.frame_feat("sub", i))
        if bool(ctx.frame_feat("beat", i)):
            shock_r, shock_on = 0.05, 1.0
        travel += speed * (0.25 + 1.5 * energy) / ctx.fps
        depth = (1.0 / r) * (1.0 - 0.3 * bass_amt * sub)
        phase = (depth * rings / 4.0 - travel) % 1.0
        ring = np.exp(-((phase - 0.5) ** 2) / 0.004)
        spec = bands[min(i, len(bands) - 1)][band_of]
        light = ring * (0.25 + 1.1 * spec) * spoke_mask * centre_fade
        if shock_on > 0.01:
            light += shock_amt * shock_on * np.exp(-((r - shock_r) ** 2) / 0.003)
            shock_r += 1.6 / ctx.fps
            shock_on *= 0.9
        img = bg + colour * light[..., None] + far * core * (0.3 + 0.7 * energy)
        yield np.clip(img, 0, 255).astype(np.uint8)
