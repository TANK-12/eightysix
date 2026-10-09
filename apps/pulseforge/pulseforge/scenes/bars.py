"""Reactive spectrum bars over a gradient or image -- the classic music-channel look."""

import numpy as np

from .. import overlay as ov

SCENE = {
    "id": "bars",
    "label": "Spectrum Bars",
    "family": "visualizer",
    "description": "A row of frequency bars that ride the music, a circular "
    "equaliser behind them, and a bloom on every beat. Sits over "
    "a colour gradient or your background image.",
    "params": [
        {"key": "color_a", "label": "Colour A", "type": "color", "default": "#d16bff"},
        {"key": "color_b", "label": "Colour B", "type": "color", "default": "#3bd6ff"},
        {
            "key": "bg_top",
            "label": "Background top",
            "type": "color",
            "default": "#12071e",
        },
        {
            "key": "bg_bottom",
            "label": "Background bottom",
            "type": "color",
            "default": "#03040a",
        },
        {
            "key": "use_image",
            "label": "Use background image if attached",
            "type": "bool",
            "default": True,
        },
        {
            "key": "image_dim",
            "label": "Dim the image",
            "type": "float",
            "default": 0.55,
            "min": 0.0,
            "max": 1.0,
        },
        {"key": "ring", "label": "Circular equaliser", "type": "bool", "default": True},
        {
            "key": "style",
            "label": "Bar style",
            "type": "select",
            "default": "glow",
            "options": ["glow", "soft"],
        },
        {
            "key": "bar_count",
            "label": "Bars (soft style)",
            "type": "int",
            "default": 64,
            "min": 16,
            "max": 160,
        },
        {
            "key": "bar_height",
            "label": "Bar height (soft style)",
            "type": "float",
            "default": 0.28,
            "min": 0.05,
            "max": 0.7,
        },
        {
            "key": "bar_opacity",
            "label": "Bar opacity (soft style)",
            "type": "float",
            "default": 0.8,
            "min": 0.1,
            "max": 1.0,
        },
        {
            "key": "flash",
            "label": "Beat flash",
            "type": "float",
            "default": 1.0,
            "min": 0.0,
            "max": 1.0,
        },
    ],
}


def frames(ctx):
    h, w = ctx.h, ctx.w
    ca, cb = ov.hex_rgb(ctx.p("color_a")), ov.hex_rgb(ctx.p("color_b"))
    bands = ctx.feat["bands"]
    nb = bands.shape[1]

    bg_img = None
    if ctx.p("use_image", True) and ctx.assets:
        for a in ctx.assets:
            if a.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
                bg_img = ov.load_image_cover(a, h, w)
                break
    grad = ov.vertical_gradient(
        h, w, ov.hex_rgb(ctx.p("bg_top")), ov.hex_rgb(ctx.p("bg_bottom"))
    ).astype(np.float64)
    flash = ov.radial_gradient(h, w, (255, 255, 255), (0, 0, 0), power=1.6).astype(
        np.float64
    )

    soft = ctx.p("style", "glow") == "soft"
    src = cols = shown = np.zeros(0)
    if soft:
        n_bars = int(ctx.p("bar_count", 64))
        # mirrored spectrum: bass in the middle, treble at both edges
        half = np.interp(
            np.linspace(0, nb - 1, n_bars // 2), np.arange(nb), np.arange(nb)
        )
        src = np.concatenate([half[::-1], half])
        cols = np.array(
            [
                ov.lerp(ca, cb, abs(k - (len(src) - 1) / 2) / (len(src) / 2))
                for k in range(len(src))
            ],
            dtype=np.float64,
        )
        shown = np.zeros(len(src))
    flash_amt = float(ctx.p("flash", 1.0))

    for i in range(ctx.n_frames):
        row = bands[min(i, len(bands) - 1)]
        energy = float(ctx.frame_feat("energy", i))
        beat = bool(ctx.frame_feat("beat", i))

        if bg_img is not None:
            t = i / max(1, ctx.n_frames - 1)
            base = ov.ken_burns(
                bg_img, h, w, t, 1.0, 1.08, pan=(0.3, 0.0), fast=ctx.fast
            )
            base = base * (1.0 - 0.85 * float(ctx.p("image_dim", 0.55)))
        else:
            base = grad.copy()

        buf = base

        if ctx.p("ring", True):
            rv = np.concatenate([row, row[::-1]])
            buf = ov.ring(
                buf,
                w / 2,
                h / 2,
                min(h, w) * 0.24,
                min(h, w) * 0.10,
                rv,
                ov.lerp(ca, cb, 0.5),
            )

        if soft:
            # rise fast, fall slowly -- the motion reads as music, not flicker
            target = np.interp(src, np.arange(nb), row)
            shown = np.where(target > shown, target, shown * 0.86 + target * 0.14)
            buf = _soft_bars(buf, shown, cols, h, w, ctx)
        else:
            # bar colour walks A->B across the spectrum
            for b in range(nb):
                col = ov.lerp(ca, cb, b / max(1, nb - 1))
                one = np.zeros(nb)
                one[b] = row[b]
                buf = ov.bars(buf, one, col, glow=0.5)

        if beat and flash_amt > 0:
            buf = ov.add(buf, flash, amount=(0.18 + 0.25 * energy) * flash_amt)

        yield ov.to_uint8(buf)


def _soft_bars(buf, values, cols, h, w, ctx):
    """Thin translucent bars blended over the picture rather than added to it,
    so a bright background keeps its colour instead of blowing out to white."""
    n = len(values)
    baseline = int(h * 0.93)
    max_h = h * float(ctx.p("bar_height", 0.28))
    alpha = float(ctx.p("bar_opacity", 0.8))
    margin = w * 0.06
    slot = (w - 2 * margin) / n
    bw = max(2, int(slot * 0.55))
    for k in range(n):
        v = float(np.clip(values[k], 0, 1))
        bh = int(max(3, v * max_h))
        x0 = int(margin + k * slot + (slot - bw) / 2)
        y0 = baseline - bh
        a = alpha * (0.55 + 0.45 * v)
        seg = buf[y0:baseline, x0 : x0 + bw]
        seg *= 1 - a
        seg += cols[k] * a
        # a faint reflection under the baseline
        r1 = min(h, baseline + bh // 4)
        ref = buf[baseline:r1, x0 : x0 + bw]
        ref *= 1 - a * 0.25
        ref += cols[k] * a * 0.25
    return buf
