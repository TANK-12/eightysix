"""Pixel-sprite swarm -- ForgeArtData sprites drifting and pulsing with the music."""

import numpy as np

from .. import overlay as ov

SCENE = {
    "id": "swarm",
    "label": "Sprite Swarm",
    "family": "sprites",
    "description": "Pixel sprites from a ForgeArtData pack drift across the frame, "
    "bob with the bass and burst outward on each beat. Ties into "
    "your pixel-art tooling. Pick a pack in the Compose tab.",
    "params": [
        {
            "key": "count",
            "label": "Sprite count",
            "type": "int",
            "default": 40,
            "min": 4,
            "max": 160,
        },
        {
            "key": "size",
            "label": "Sprite scale",
            "type": "int",
            "default": 4,
            "min": 1,
            "max": 12,
        },
        {
            "key": "drift",
            "label": "Drift speed",
            "type": "float",
            "default": 0.4,
            "min": 0.0,
            "max": 2.0,
        },
        {
            "key": "bg_top",
            "label": "Background top",
            "type": "color",
            "default": "#0b0f1e",
        },
        {
            "key": "bg_bottom",
            "label": "Background bottom",
            "type": "color",
            "default": "#02030a",
        },
        {
            "key": "use_image",
            "label": "Use background image if attached",
            "type": "bool",
            "default": True,
        },
    ],
}


def _sprite_frames(pack, palette_colors, scale):
    """Return a list of RGBA arrays -- the first frame of every sprite in the pack."""
    out = []
    for name, spr in (pack.get("sprites") or {}).items():
        frs = spr.get("frames") or []
        if not frs:
            continue
        rows = frs[0].get("rows") or []
        if rows:
            out.append(ov.rasterize_sprite(rows, palette_colors, scale=scale))
    return out


def frames(ctx):
    h, w = ctx.h, ctx.w
    pack = ctx.art_pack or {}
    palette_colors = (
        ctx.params.get("_palette_colors") or (pack.get("_palette_colors")) or {}
    )
    sprites = _sprite_frames(pack, palette_colors, int(ctx.p("size", 4)))
    if not sprites:
        # no pack -> fall back to soft glowing dots so the scene still renders
        sprites = None

    n = int(ctx.p("count", 40))
    rng = np.random.default_rng(42)
    px = rng.random(n) * w
    py = rng.random(n) * h
    vx = (rng.random(n) - 0.5) * 2
    vy = (rng.random(n) - 0.5) * 2
    kind = rng.integers(0, max(1, len(sprites) if sprites else 1), n)
    phase = rng.random(n) * 6.28

    grad = ov.vertical_gradient(
        h, w, ov.hex_rgb(ctx.p("bg_top")), ov.hex_rgb(ctx.p("bg_bottom"))
    ).astype(np.float64)
    bg_img = None
    if ctx.p("use_image", True):
        for a in ctx.assets:
            if a.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
                bg_img = ov.load_image_cover(a, h, w)
                break

    drift = float(ctx.p("drift", 0.4))
    dt = 1.0 / ctx.fps

    for i in range(ctx.n_frames):
        energy = float(ctx.frame_feat("energy", i))
        sub = float(ctx.frame_feat("sub", i))
        beat = bool(ctx.frame_feat("beat", i))

        speed = drift * (0.5 + 1.5 * energy) * 60 * dt
        px = (px + vx * speed) % w
        py = (py + vy * speed + np.sin(phase + i * 0.05) * sub * 3) % h
        if beat:
            cx, cy = w / 2, h / 2
            ang = np.arctan2(py - cy, px - cx)
            px = px + np.cos(ang) * 18
            py = py + np.sin(ang) * 18

        base = (
            ov.ken_burns(
                bg_img, h, w, i / max(1, ctx.n_frames - 1), 1.0, 1.06, fast=ctx.fast
            )
            if bg_img is not None
            else grad.copy()
        )

        if sprites:
            op = 0.6 + 0.4 * energy
            for k in range(n):
                spr = sprites[int(kind[k]) % len(sprites)]
                ov.blit_rgba(base, spr, px[k], py[k], opacity=op)
        else:
            col = (180, 150, 255)
            base = ov.glow_dots(base, px, py, 4 + 6 * energy, col, 0.5 + 0.5 * energy)

        yield ov.to_uint8(base)
