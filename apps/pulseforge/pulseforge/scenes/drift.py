"""Drifting scenery -- a still image with slow parallax, Ken Burns and clouds. Lofi look."""

import numpy as np

from .. import overlay as ov

SCENE = {
    "id": "drift",
    "label": "Drifting Scenery",
    "family": "scenery",
    "description": "A background image (yours or AI-made) with a slow Ken Burns "
    "zoom, a parallax haze layer and clouds crossing the frame. "
    "Breathes gently with the music. The 'lofi study beats' look.",
    "params": [
        {
            "key": "zoom",
            "label": "Zoom over the track",
            "type": "float",
            "default": 0.10,
            "min": 0.0,
            "max": 0.4,
        },
        {
            "key": "breathe",
            "label": "Beat breathing",
            "type": "float",
            "default": 0.06,
            "min": 0.0,
            "max": 0.25,
        },
        {
            "key": "cloud_tint",
            "label": "Cloud tint",
            "type": "color",
            "default": "#8fb6ff",
        },
        {
            "key": "cloud_amount",
            "label": "Cloud amount",
            "type": "float",
            "default": 0.35,
            "min": 0.0,
            "max": 1.0,
        },
        {
            "key": "grade_top",
            "label": "Sky grade",
            "type": "color",
            "default": "#1a1030",
        },
        {
            "key": "grade_bottom",
            "label": "Ground grade",
            "type": "color",
            "default": "#060812",
        },
        {
            "key": "vignette",
            "label": "Vignette",
            "type": "float",
            "default": 0.35,
            "min": 0.0,
            "max": 1.0,
        },
    ],
}


def frames(ctx):
    h, w = ctx.h, ctx.w
    img = None
    for a in ctx.assets:
        if a.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
            img = ov.load_image_cover(a, h, w)
            break

    grad = ov.vertical_gradient(
        h, w, ov.hex_rgb(ctx.p("grade_top")), ov.hex_rgb(ctx.p("grade_bottom"))
    ).astype(np.float64)
    tint = ov.hex_rgb(ctx.p("cloud_tint"))
    # vignette mask: 0 at centre, 1 at the corners
    vmask = (
        ov.radial_gradient(h, w, (0, 0, 0), (255, 255, 255), power=1.4)[..., 0] / 255.0
    )
    zoom = float(ctx.p("zoom", 0.10))
    breathe = float(ctx.p("breathe", 0.06))
    cloud_amt = float(ctx.p("cloud_amount", 0.35))
    vig_amt = float(ctx.p("vignette", 0.35))

    for i in range(ctx.n_frames):
        t = i / max(1, ctx.n_frames - 1)
        energy = float(ctx.frame_feat("energy", i))
        sub = float(ctx.frame_feat("sub", i))

        z_end = 1.0 + zoom + breathe * sub
        if img is not None:
            base = ov.ken_burns(
                img,
                h,
                w,
                t,
                1.0 + breathe * 0.3 * energy,
                z_end,
                pan=(0.4, 0.15),
                fast=ctx.fast,
            )
        else:
            base = grad.copy()

        if cloud_amt > 0:
            haze = ov.clouds(h, w, t, tint, density=0.45 + 0.2 * energy, speed=0.03)
            base = ov.screen(base, haze * cloud_amt)

        if vig_amt > 0:
            base = base * (1.0 - vmask[..., None] * vig_amt)

        yield ov.to_uint8(base)
