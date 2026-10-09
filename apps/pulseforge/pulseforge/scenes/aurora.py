"""
Aurora -- curtains of light over a night sky.

The first version of this scene drew horizontal sine ribbons: evenly spaced
bands that slid up and down and never folded. It was called out as not good,
and it was, because that is not what an aurora looks like from any angle. A
real one is a **vertical curtain** -- a sheet of light standing on a crisp lower
edge and fading out as it rises, shot through with fine vertical rays, folding
along its length like a hanging cloth, and changing colour with height because
the height *is* the physics: oxygen glows green low down and red high up, with
nitrogen putting violet along the bottom edge.

So this draws that instead:

    the curtain      a meandering line the sheet hangs from, which leans and
                     folds as it climbs rather than staying vertical
    the lower edge   crisp, because that is the single most recognisable thing
                     about an aurora; the top is diffuse
    the rays         fine vertical striations from two beating frequencies, so
                     they never fall into a visible repeat
    the colour       green low, through the palette, to violet at the top
    the sky          a real gradient with stars behind it and a horizon glow

and the music moves it: the bass rolls the curtains sideways, loudness drives
how far they climb, and brightness in the track sharpens the rays.

The four original parameters keep their names, meanings and defaults, so any
project already using this scene opens unchanged and looks better. Everything
new is additive and defaults to the behaviour described above.
"""

import numpy as np

from .. import overlay as ov

SCENE = {
    "id": "aurora",
    "label": "Aurora Field",
    "family": "visualizer",
    "description": "Curtains of light standing over a starfield: a crisp lower edge, fine "
    "vertical rays, folding as they climb, green through violet with height. "
    "The bass rolls them sideways and the highs sharpen the rays.",
    "params": [
        {
            "key": "palette",
            "label": "Palette",
            "type": "select",
            "default": "violet",
            "options": ["violet", "ocean", "ember", "forest", "classic"],
        },
        {
            "key": "bands",
            "label": "Curtain count",
            "type": "int",
            "default": 5,
            "min": 2,
            "max": 10,
        },
        {
            "key": "flow",
            "label": "Flow speed",
            "type": "float",
            "default": 0.5,
            "min": 0.0,
            "max": 2.0,
        },
        {
            "key": "glow",
            "label": "Glow",
            "type": "float",
            "default": 0.7,
            "min": 0.0,
            "max": 1.5,
        },
        {
            "key": "height",
            "label": "How far they climb",
            "type": "float",
            "default": 0.55,
            "min": 0.15,
            "max": 1.0,
        },
        {
            "key": "base",
            "label": "Where the bottom edge sits",
            "type": "float",
            "default": 0.72,
            "min": 0.3,
            "max": 1.0,
            "help": "0 is the top of the frame, 1 the bottom.",
        },
        {
            "key": "rays",
            "label": "Vertical rays",
            "type": "float",
            "default": 0.55,
            "min": 0.0,
            "max": 1.0,
        },
        {
            "key": "fold",
            "label": "Folding",
            "type": "float",
            "default": 0.5,
            "min": 0.0,
            "max": 1.5,
        },
        {
            "key": "stars",
            "label": "Stars",
            "type": "float",
            "default": 0.6,
            "min": 0.0,
            "max": 1.0,
        },
        {
            "key": "reactivity",
            "label": "How much it reacts to the music",
            "type": "float",
            "default": 0.7,
            "min": 0.0,
            "max": 1.5,
        },
    ],
}

# (sky, low colour, high colour). Low is what the bottom of the curtain glows,
# high is what it fades to -- the pairing is the whole look of each palette.
_PALETTES = {
    "violet": [(10, 8, 26), (120, 255, 190), (190, 90, 255)],
    "ocean": [(4, 12, 26), (60, 230, 220), (70, 120, 255)],
    "ember": [(20, 8, 8), (255, 170, 70), (255, 70, 120)],
    "forest": [(6, 14, 10), (120, 255, 130), (230, 255, 120)],
    "classic": [(8, 10, 20), (90, 255, 120), (220, 80, 200)],
}


def _starfield(h, w, amount, seed=5):
    """A sparse field of stars, brighter near the top of the frame."""
    if amount <= 0.001:
        return np.zeros((h, w), dtype=np.float32)
    rng = np.random.default_rng(seed)
    field = np.zeros((h, w), dtype=np.float32)
    n = int(h * w * 0.0016 * amount)
    ys = rng.integers(0, h, n)
    xs = rng.integers(0, w, n)
    mag = rng.random(n).astype(np.float32) ** 2.4
    field[ys, xs] = mag
    return field


def frames(ctx):
    from PIL import Image

    H, W = ctx.h, ctx.w
    # The field is smooth, so it is computed at half resolution and upscaled.
    h, w = max(2, H // 2), max(2, W // 2)
    pal = _PALETTES.get(ctx.p("palette", "violet"), _PALETTES["violet"])
    sky_col = np.array(pal[0], dtype=np.float32)
    lo_col = np.array(pal[1], dtype=np.float32)
    hi_col = np.array(pal[2], dtype=np.float32)

    nb = int(ctx.p("bands", 5))
    flow = float(ctx.p("flow", 0.5))
    glow = float(ctx.p("glow", 0.7))
    climb = float(ctx.p("height", 0.55))
    base_y = float(ctx.p("base", 0.72))
    ray_amt = float(ctx.p("rays", 0.55))
    fold_amt = float(ctx.p("fold", 0.5))
    star_amt = float(ctx.p("stars", 0.6))
    react = float(ctx.p("reactivity", 0.7))

    xs = np.linspace(0.0, 1.0, w, dtype=np.float32)[None, :]
    ys = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]

    stars = _starfield(h, w, star_amt)
    # A soft band centred on the base line, falling away above and below.
    horizon = np.exp(-(((ys - base_y) / 0.11) ** 2)) * np.ones((1, w), dtype=np.float32)
    # The sky is darkest overhead and lifts a little towards the horizon.
    # `ys` is a column, so it has to be spread across the width before it can
    # become an image rather than a one-pixel-wide strip.
    grad = (0.55 + 0.55 * ys) * np.ones((1, w), dtype=np.float32)
    sky = sky_col[None, None, :] * grad[..., None]
    # Curtains are spread across the frame and given their own rhythm, so they
    # never line up into a pattern.
    offs = np.linspace(-0.34, 0.34, nb) if nb > 1 else np.array([0.0])
    rng = np.random.default_rng(17)
    phases = rng.random(nb).astype(np.float32) * 6.283
    widths = 0.045 + 0.05 * rng.random(nb).astype(np.float32)
    # Each curtain stands on its own base and climbs its own distance, so the
    # row does not read as one shape stamped out several times.
    base_jit = (rng.random(nb).astype(np.float32) - 0.5) * 0.06
    climb_jit = 0.75 + 0.5 * rng.random(nb).astype(np.float32)

    bands_arr = ctx.feat["bands"]
    n_bands = bands_arr.shape[1] if bands_arr.ndim == 2 else 1

    for i in range(ctx.n_frames):
        t = i / ctx.fps
        energy = float(ctx.frame_feat("energy", i))
        sub = float(ctx.frame_feat("sub", i))
        centroid = float(ctx.frame_feat("centroid", i))
        row = bands_arr[min(i, len(bands_arr) - 1)]

        img = sky.copy()
        if star_amt > 0.001:
            twinkle = 0.75 + 0.25 * np.sin(t * 2.1 + stars * 40.0)
            img += (stars * twinkle * 200.0)[..., None]

        light = np.zeros((h, w, 3), dtype=np.float32)
        for b in range(nb):
            ph = float(phases[b])
            # This curtain's own slice of the spectrum drives its brightness,
            # so they light up one after another rather than all at once.
            amp = float(row[int(b / max(1, nb) * n_bands) % n_bands])

            # Where the sheet hangs, as a function of height: it drifts, leans
            # over as it climbs, and folds. The fold is what stops it reading
            # as a stripe.
            drift = 0.16 * np.sin(t * flow * 0.31 + ph) + 0.07 * np.sin(
                t * flow * 0.17 + ph * 1.7
            )
            roll = 0.10 * sub * react * np.sin(t * flow * 0.9 + ph)
            lean = 0.18 * np.sin(t * flow * 0.23 + ph * 0.7)
            my_base = base_y + float(base_jit[b])
            my_climb = max(0.05, climb * float(climb_jit[b]))
            u = np.clip((my_base - ys) / my_climb, 0.0, 1.0)  # 0 base, 1 top
            fold = fold_amt * 0.05 * np.sin(u * 9.0 + t * flow * 0.8 + ph)
            centre = float(offs[b]) + 0.5 + drift + roll + lean * u + fold

            d = (xs - centre) / (widths[b] * (1.0 + 0.5 * u))
            across = np.exp(-d * d)

            # A crisp lower edge and a diffuse top: the single most recognisable
            # thing about an aurora, and what the sine ribbons never had.
            above = (my_base - ys) >= 0
            vert = np.exp(-u * 2.1) * np.clip(u / 0.04, 0.0, 1.0) * above

            body = across * vert * (0.35 + 0.9 * amp * react + 0.25 * energy)

            if ray_amt > 0.001:
                # Two close frequencies beating against each other: the rays
                # drift and never resolve into a visible repeat.
                sharp = 0.5 + 0.5 * centroid
                r1 = 0.5 + 0.5 * np.sin((xs * 47.0 + t * flow * 0.7 + ph) * 6.283)
                r2 = 0.5 + 0.5 * np.sin((xs * 61.0 - t * flow * 0.4 + ph) * 6.283)
                body = body * (1.0 - ray_amt * sharp * (1.0 - r1 * r2))

            # Colour by height, because in a real aurora the height is the
            # reason the colour changes at all.
            col = (
                lo_col[None, None, :] * (1.0 - u[..., None])
                + hi_col[None, None, :] * u[..., None]
            )
            light += body[..., None] * col

        if glow > 0.001:
            # Bloom at quarter size: a down-and-up resample is a cheap, smooth
            # blur and costs almost nothing next to the field itself.
            small = Image.fromarray(ov.to_uint8(light)).resize(
                (max(2, w // 4), max(2, h // 4)), Image.Resampling.BILINEAR
            )
            blurred = np.asarray(
                small.resize((w, h), Image.Resampling.BILINEAR), dtype=np.float32
            )
            light = light + blurred * glow

        img += light
        # A wash of the curtains' colour along the horizon, as though the sky
        # itself were lit from below. It has to fall away on *both* sides of
        # the base line: clipping it instead left everything below the line at
        # full strength, which drew a hard horizontal seam straight across the
        # frame -- the one thing a sky must not have.
        img += horizon[..., None] * lo_col[None, None, :] * (0.05 + 0.14 * energy)

        yield np.asarray(
            Image.fromarray(ov.to_uint8(img)).resize((W, H), Image.Resampling.BILINEAR)
        )
