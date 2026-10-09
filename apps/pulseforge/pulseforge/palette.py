"""
Read a background picture and build the whole look out of it.

The usual way round is backwards. You import an illustration, then go through
twenty sliders deciding how warm it should be, how much bloom, whether it wants
a vignette -- and the answers were all sitting in the picture the whole time. A
night scene wants a cool grade, a heavy vignette, bloom on its lamps and grain;
a golden-hour scene wants warmth, a light leak from the side the sun is on, and
almost no vignette at all. None of that is taste. It is measurable.

So this measures it:

    palette      the dominant colours, most common first
    brightness   how dark the picture is overall
    warmth       red against blue, -1 cold .. +1 warm
    saturation   how colourful
    contrast     how much range there is
    light        which way the light is coming from, and how directional
    mood         the one-word reading those add up to
    sky / water  whether there is any, reusing the same detector the
                 Scenery editor's automatic regions already use

and turns them into a set of the living scene's own parameters, plus the region
effects and emitters that go with them. Every number it produces is an ordinary
parameter you can then move; nothing here is a mode you get stuck in.

The light leak's colour is taken from the picture's own brightest tones rather
than from a fixed orange, which is what stops it reading as a filter laid on
top -- it looks like light that was already in the scene.
"""

import numpy as np
from PIL import Image

from . import autoregions

THUMB = 220  # everything is measured on a thumbnail; the answers are averages


def _rgb_to_hex(rgb):
    return "#%02x%02x%02x" % tuple(int(np.clip(v, 0, 255)) for v in rgb)


def _load(path):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    scale = THUMB / max(1, max(w, h))
    if scale < 1.0:
        im = im.resize(
            (max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.BILINEAR
        )
    return np.asarray(im, dtype=np.float32)


def dominant_colours(arr, k=6):
    """The k most common colours, by a small k-means over the pixels.

    Written out rather than pulled from OpenCV so this works on a machine
    without it -- the Scenery editor is the one part of the app that has to run
    everywhere, and it is only a few hundred pixels of work."""
    px = arr.reshape(-1, 3)
    if px.shape[0] > 6000:
        px = px[:: px.shape[0] // 6000]
    rng = np.random.default_rng(11)
    centres = px[
        rng.choice(px.shape[0], size=min(k, px.shape[0]), replace=False)
    ].copy()
    labels = np.zeros(px.shape[0], dtype=int)
    for _ in range(12):
        d = ((px[:, None, :] - centres[None, :, :]) ** 2).sum(axis=2)
        labels = np.argmin(d, axis=1)
        for i in range(len(centres)):
            sel = px[labels == i]
            if len(sel):
                centres[i] = sel.mean(axis=0)
    counts = np.bincount(labels, minlength=len(centres))
    order = np.argsort(-counts)
    return [[int(v) for v in centres[i]] for i in order], [
        float(counts[i] / max(1, len(px))) for i in order
    ]


def measure(arr):
    """The numbers everything else is decided from."""
    f = arr / 255.0
    luma = 0.2126 * f[..., 0] + 0.7152 * f[..., 1] + 0.0722 * f[..., 2]
    mx, mn = f.max(axis=2), f.min(axis=2)
    sat = np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    # Warmth twice: over everything, and over the *lit* half only.
    #
    # The second is what the mood is read from, and the difference is not
    # subtle. A sunset is warm where the light is and deep blue everywhere
    # else, and the sky is usually the larger area -- so a global average calls
    # a golden-hour painting cold and then grades the warmth straight out of
    # it. Asking "what colour is the light in this picture" means looking only
    # at the parts that are lit.
    # How much of the picture is *exactly* one colour. Vector-style artwork is
    # built from large uniform fills; a photograph or a painting has a gradient
    # almost everywhere. Tonal contrast does not tell these apart -- a flat
    # illustration of dark pines against a bright sky has plenty of contrast --
    # so this measures the area with no local gradient at all, which does.
    gx = np.abs(np.diff(luma, axis=1, prepend=luma[:, :1]))
    gy = np.abs(np.diff(luma, axis=0, prepend=luma[:1, :]))
    flat_area = float(((gx + gy) < 0.012).mean())

    lit = luma >= luma.mean()
    if lit.sum() < 16:
        lit = np.ones_like(luma, dtype=bool)
    warm_all = (f[..., 0].mean() - f[..., 2].mean()) * 3.0
    warm_lit = (f[..., 0][lit].mean() - f[..., 2][lit].mean()) * 3.0
    return {
        "brightness": float(luma.mean()),
        "contrast": float(luma.std()),
        "saturation": float(sat.mean()),
        "warmth": float(np.clip(warm_all, -1, 1)),
        "light_warmth": float(np.clip(warm_lit, -1, 1)),
        "dark_fraction": float((luma < 0.12).mean()),
        "bright_fraction": float((luma > 0.85).mean()),
        "flat_area": flat_area,
    }


def light_direction(arr):
    """Where the light is coming from, as a point and a compass word.

    The centre of mass of everything brighter than average. A sky lit from the
    left puts it at the left; a flat, evenly lit illustration puts it in the
    middle and `strength` says so, which is how the caller knows not to add a
    directional light leak to a picture that has no direction."""
    f = arr / 255.0
    luma = 0.2126 * f[..., 0] + 0.7152 * f[..., 1] + 0.0722 * f[..., 2]
    w = np.clip(luma - luma.mean(), 0, None)
    if w.sum() < 1e-6:
        return {"x": 0.5, "y": 0.5, "strength": 0.0, "where": "flat"}
    h, wd = luma.shape
    ys, xs = np.mgrid[0:h, 0:wd]
    cx = float((w * xs).sum() / w.sum()) / max(1, wd - 1)
    cy = float((w * ys).sum() / w.sum()) / max(1, h - 1)
    strength = float(np.clip(np.hypot(cx - 0.5, cy - 0.5) * 2.6, 0, 1))
    if strength < 0.18:
        where = "flat"
    else:
        vert = "top" if cy < 0.42 else ("bottom" if cy > 0.58 else "")
        horiz = "left" if cx < 0.42 else ("right" if cx > 0.58 else "")
        where = "-".join([p for p in (vert, horiz) if p]) or "centre"
    return {
        "x": round(cx, 3),
        "y": round(cy, 3),
        "strength": round(strength, 3),
        "where": where,
    }


def read_mood(m):
    """One word for what kind of picture this is.

    Ordered so the strongest signal wins. Darkness beats everything -- a warm
    night scene is still a night scene -- and flatness of colour is checked
    before warmth, because an overcast picture can read slightly warm without
    being golden."""
    b, s = m["brightness"], m["saturation"]
    w = m.get("light_warmth", m["warmth"])
    if b < 0.22 or m["dark_fraction"] > 0.45:
        return "night"
    if b < 0.36:
        return "dusk"
    if s < 0.16:
        return "overcast"
    if w > 0.16 and b < 0.68:
        return "golden hour"
    # Bright and colourful is checked *before* coldness. Almost every outdoor
    # picture is blue-dominant, because most of it is sky -- a sunny afternoon
    # over green grass measures colder than an overcast one. Testing warmth
    # first filed a blue-sky summer scene as cold daylight and graded it
    # bleach-bypass, which is the opposite of what it wants.
    if b > 0.6 and s > 0.32:
        return "bright day"
    if w < -0.14:
        return "cold daylight"
    return "daylight"


# How each mood is dressed. One table, so a mood is a row rather than a branch
# buried in a function -- and so the reasoning is legible next to the numbers.
MOODS = {
    "night": {
        "grade": "night",
        "grade_amount": 0.75,
        "vignette": 0.55,
        "grain": 0.14,
        "bloom": 0.42,
        "saturation": 0.85,
        "warmth": -0.12,
        "haze": 0.12,
        "leak": 0.0,
        "push": 0.05,
        "drift": 0.28,
        "why": "dark and low-contrast, so the light sources are bloomed, the corners pulled down and the colour cooled",
        "effects": ["glow_pulse", "flicker"],
        "emitters": ["stars", "fireflies"],
    },
    "dusk": {
        "grade": "teal_orange",
        "grade_amount": 0.5,
        "vignette": 0.42,
        "grain": 0.1,
        "bloom": 0.3,
        "saturation": 0.98,
        "warmth": 0.08,
        "haze": 0.2,
        "leak": 0.14,
        "push": 0.06,
        "drift": 0.32,
        "why": "half-light, so the shadows go cool and the remaining warmth is kept in the highlights",
        "effects": ["glow_pulse"],
        "emitters": ["dust", "fireflies"],
    },
    "overcast": {
        "grade": "faded",
        "grade_amount": 0.6,
        "vignette": 0.22,
        "grain": 0.09,
        "bloom": 0.12,
        "saturation": 0.92,
        "warmth": -0.04,
        "haze": 0.3,
        "leak": 0.0,
        "push": 0.05,
        "drift": 0.3,
        "why": "flat colour and soft light, so the blacks are lifted and distance hazed rather than contrast added",
        "effects": ["sky_clouds"],
        "emitters": ["rain", "dust"],
    },
    "golden hour": {
        "grade": "kodak",
        "grade_amount": 0.65,
        "vignette": 0.2,
        "grain": 0.07,
        "bloom": 0.3,
        "saturation": 1.08,
        "warmth": 0.24,
        "haze": 0.16,
        "leak": 0.3,
        "push": 0.07,
        "drift": 0.35,
        "why": "warm and directional, so a light leak is added from the side the light is already on",
        "effects": ["rays", "shimmer"],
        "emitters": ["dust", "leaves"],
    },
    "cold daylight": {
        # No colour grade at all, on purpose. Bleach bypass was the first
        # choice and it was wrong: most cold pictures reaching this app are
        # illustrations whose colour is already a deliberate decision, and
        # draining a vivid blue-violet painting towards grey "corrects" the one
        # thing that made it worth using. Cold light gets depth and haze
        # instead, and keeps its own colour.
        "grade": "none",
        "grade_amount": 0.0,
        "vignette": 0.28,
        "grain": 0.07,
        "bloom": 0.2,
        "saturation": 1.02,
        "warmth": -0.06,
        "haze": 0.22,
        "leak": 0.0,
        "push": 0.05,
        "drift": 0.3,
        "why": "cold, directional light, so it keeps its own colour and gains depth and haze rather than a grade",
        "effects": ["sky_clouds"],
        "emitters": ["snow", "dust"],
    },
    "bright day": {
        "grade": "none",
        "grade_amount": 0.0,
        "vignette": 0.18,
        "grain": 0.05,
        "bloom": 0.22,
        "saturation": 1.05,
        "warmth": 0.06,
        "haze": 0.1,
        "leak": 0.12,
        "push": 0.06,
        "drift": 0.34,
        "why": "already bright and colourful, so almost nothing is added -- only a little bloom and lift",
        "effects": ["sky_clouds", "shimmer"],
        "emitters": ["birds", "dust"],
    },
    "daylight": {
        "grade": "faded",
        "grade_amount": 0.4,
        "vignette": 0.28,
        "grain": 0.08,
        "bloom": 0.18,
        "saturation": 1.0,
        "warmth": 0.02,
        "haze": 0.14,
        "leak": 0.08,
        "push": 0.06,
        "drift": 0.33,
        "why": "an ordinary daylight picture, given a light film grade and a slow drift",
        "effects": ["sky_clouds"],
        "emitters": ["dust", "birds"],
    },
}


def _highlight_colour(colours, weights):
    """The brightest of the picture's own dominant colours, pushed towards the
    light. Used for the leak, so it looks like light that was already there."""
    best, best_l = colours[0], -1.0
    for c in colours:
        lum = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
        if lum > best_l:
            best, best_l = c, lum
    return [int(np.clip(v * 0.55 + 255 * 0.45, 0, 255)) for v in best]


def _haze_colour(colours):
    """The coolest dominant colour, lightened. Distance haze is the sky's
    colour bleeding into what is far away, so taking it from the picture keeps
    the far hills the right colour for that sky."""
    best, best_b = colours[0], -1e9
    for c in colours:
        blue = c[2] - (c[0] + c[1]) * 0.5
        if blue > best_b:
            best, best_b = c, blue
    return [int(np.clip(v * 0.4 + 255 * 0.6, 0, 255)) for v in best]


def look_from_image(path):
    """Everything above, as a look ready to apply to a shot."""
    arr = _load(path)
    m = measure(arr)
    light = light_direction(arr)
    colours, weights = dominant_colours(arr)
    mood = read_mood(m)
    row = MOODS[mood]

    params = {
        "grade": row["grade"],
        "grade_amount": row["grade_amount"],
        "vignette": row["vignette"],
        "grain": row["grain"],
        "bloom": row["bloom"],
        "saturation": row["saturation"],
        "warmth": row["warmth"],
        "haze": row["haze"],
        "haze_color": _rgb_to_hex(_haze_colour(colours)),
        "push": row["push"],
        "drift": row["drift"],
    }
    # A leak only makes sense when the light actually comes from somewhere. On
    # a flat, evenly lit illustration it reads as a smear, so it is dropped.
    leak = row["leak"] * (0.35 + 0.65 * light["strength"])
    if light["where"] == "flat":
        leak *= 0.3
    params["leak"] = round(float(leak), 3)
    params["leak_color"] = _rgb_to_hex(_highlight_colour(colours, weights))
    # More bloom when there are actual *highlights* to bloom -- and less when
    # the picture is simply bright all over.
    #
    # The first version multiplied by `bright_fraction` alone, which is the
    # area that is bright, not the presence of highlights. A pastel sky or a
    # flat green field is 40% "bright", so it got nearly triple bloom and
    # clipped into a white band; a night scene with three lamps got almost
    # none, which is the one case that actually wanted it. So: the boost
    # saturates as soon as there are *some* highlights, and is then damped by
    # how bright the picture already is.
    # Bloom wants a *hump*, not a ramp: it has to rise once there are some
    # bright pixels to glow, then fall away again once "bright" stops meaning
    # highlights and starts meaning a large pale field. Blooming a big soft
    # bright area does not make it glow, it pushes it over the top and flattens
    # it to white. Measured on six real pictures, the one that blew out had 20%
    # of its frame near-white and was being handed the *maximum* boost -- a
    # plain ramp on bright area gets this exactly the wrong way round.
    bf = m["bright_fraction"]
    rise = float(np.clip(bf / 0.03, 0.0, 1.0))
    fall = float(np.clip(1.0 - (bf - 0.06) / 0.20, 0.15, 1.0))
    headroom = float(np.clip(1.35 - m["brightness"], 0.35, 1.2))
    params["bloom"] = round(
        float(np.clip(row["bloom"] * (0.45 + 0.75 * rise) * fall * headroom, 0.0, 1.0)),
        3,
    )

    # A film grade emulates how film responded to light. Flat vector-style
    # artwork never went through a camera, has no texture to hold the grade,
    # and turns lurid when you push one onto it -- a green minimal landscape
    # came back acid. `contrast` is a decent stand-in for how photographic a
    # picture is, so grade strength, added saturation and the leak are all
    # scaled back on flat art.
    flatness = float(np.clip((m["flat_area"] - 0.30) / 0.45, 0.0, 1.0))
    if flatness > 0.05:
        keep = 1.0 - 0.75 * flatness
        params["grade_amount"] = round(float(params["grade_amount"] * keep), 3)
        params["saturation"] = round(
            float(1.0 + (params["saturation"] - 1.0) * keep), 3
        )
        params["leak"] = round(float(params["leak"] * keep), 3)
        params["bloom"] = round(float(params["bloom"] * (1.0 - 0.5 * flatness)), 3)

    regions = []
    try:
        for r in autoregions.suggest(path):
            regions.append(
                {
                    "name": r["name"],
                    "effect": r["effect"],
                    "coverage": round(float(r["coverage"]), 3),
                }
            )
    except Exception:
        pass
    found = {r["name"] for r in regions}
    if "sky" in found:
        params["sky_clouds"] = 0.35

    return {
        "mood": mood,
        "why": row["why"],
        "flatness": round(flatness, 3),
        "measures": {k: round(v, 4) for k, v in m.items()},
        "light": light,
        "palette": [_rgb_to_hex(c) for c in colours],
        "palette_weights": [round(w, 4) for w in weights],
        "params": {
            k: (round(v, 4) if isinstance(v, float) else v) for k, v in params.items()
        },
        "suggested_effects": row["effects"],
        "suggested_emitters": row["emitters"],
        "regions_found": regions,
    }


# Where each parameter has to be written for the renderer to see it. A shot
# keeps its colour under `look` and its movement under `camera`; they are read
# by `scenes/living._look()` and `._camera()` respectively, and a value put
# anywhere else is silently ignored -- which is exactly what happened when this
# module first wrote everything into `params`.
LOOK_KEYS = (
    "vignette",
    "grain",
    "bloom",
    "saturation",
    "warmth",
    "focus",
    "aperture",
    "haze",
    "haze_color",
    "grade",
    "grade_amount",
    "scanlines",
    "fringing",
    "letterbox",
    "leak",
    "leak_color",
)
CAMERA_KEYS = ("push", "drift", "parallax")


def split_for_shot(params):
    """Sort a look into the two dicts a shot actually stores it in.

    Returns (look, camera, leftover). `leftover` is anything that belongs to
    the scene rather than the shot -- `sky_clouds` is the only one today -- and
    the caller decides what to do with it rather than it being dropped
    silently."""
    look, camera, leftover = {}, {}, {}
    for k, v in (params or {}).items():
        if k in LOOK_KEYS:
            look[k] = v
        elif k in CAMERA_KEYS:
            camera[k] = v
        else:
            leftover[k] = v
    return look, camera, leftover


__all__ = [
    "look_from_image",
    "measure",
    "light_direction",
    "dominant_colours",
    "read_mood",
    "MOODS",
    "split_for_shot",
    "LOOK_KEYS",
    "CAMERA_KEYS",
]
