"""
Film grades -- whole colour looks, as one choice.

The `Look` pass already has saturation, warmth, bloom and the analogue pack, but
those are ingredients. What actually makes footage feel like something is the
*relationship* between shadows, midtones and highlights, and nobody wants to
dial that in from five sliders every time.

So each grade here is a small function over a float32 RGB frame. They work on
lifts and gains per channel rather than a lookup table, which keeps them exact
at any bit depth, costs a couple of multiplies, and means the strength dial can
blend continuously from nothing to the full look.

Adding one is a function and one entry in `GRADES`. The picker in the editor and
the parameter's option list are both generated from that table.
"""

import numpy as np

_LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def _split(frame):
    """Normalised frame plus a 0..1 luma, which most of these need."""
    x = frame / 255.0
    return x, (x @ _LUMA)[..., None]


def _faded(frame):
    """Lifted blacks and softer highlights -- an old print left in the sun."""
    x, _ = _split(frame)
    x = x * 0.82 + 0.11
    x[..., 2] += 0.03  # a touch of blue in the shadows
    return x * 255.0


def _teal_orange(frame):
    x, luma = _split(frame)
    shadow = 1.0 - luma
    x[..., 0] += (luma * 0.10 - shadow * 0.05)[..., 0]
    x[..., 1] += (luma * 0.02)[..., 0]
    x[..., 2] += (shadow * 0.12 - luma * 0.06)[..., 0]
    return x * 255.0


def _kodak(frame):
    """Warm, creamy, slightly green in the shadows."""
    x, luma = _split(frame)
    x[..., 0] *= 1.07
    x[..., 1] *= 1.01
    x[..., 2] *= 0.93
    x[..., 1] += ((1.0 - luma) * 0.03)[..., 0]
    return np.clip(x, 0.0, 1.2) * 255.0


def _bleach(frame):
    """Desaturated and contrasty, the way bypassed film goes."""
    x, luma = _split(frame)
    x = luma * 0.55 + x * 0.45
    x = np.clip((x - 0.5) * 1.35 + 0.5, 0.0, 1.2)
    x[..., 2] *= 1.04
    return x * 255.0


def _night(frame):
    """Cool and dim, with the highlights pulled down. Day for night."""
    x, luma = _split(frame)
    x = x * 0.72
    x[..., 0] *= 0.88
    x[..., 2] *= 1.18
    x += (1.0 - luma) * 0.04
    return x * 255.0


def _sepia(frame):
    x, luma = _split(frame)
    tone = np.array([1.07, 0.94, 0.74], dtype=np.float32)
    x = luma * tone * 1.05
    return np.clip(x, 0.0, 1.1) * 255.0


def _vhs(frame):
    """Magenta lift, green midtones, crushed blacks -- tape."""
    x, luma = _split(frame)
    x[..., 0] += 0.05 * (1.0 - luma)[..., 0]
    x[..., 1] += 0.03 * luma[..., 0]
    x[..., 2] += 0.06 * (1.0 - luma)[..., 0]
    x = np.clip((x - 0.03) * 1.08, 0.0, 1.15)
    return x * 255.0


def _dream(frame):
    """Pale, soft and slightly pink. The one most of these videos actually use."""
    x, luma = _split(frame)
    x = x * 0.88 + 0.09
    x[..., 0] += 0.03
    x[..., 2] += 0.015
    x = luma * 0.18 + x * 0.82
    return x * 255.0


GRADES = [
    {
        "id": "none",
        "label": "None",
        "description": "Leave the colour alone.",
        "fn": None,
    },
    {
        "id": "faded",
        "label": "Faded",
        "description": "Lifted blacks, soft highlights, sun-bleached.",
        "fn": _faded,
    },
    {
        "id": "teal_orange",
        "label": "Teal & orange",
        "description": "Cool shadows, warm skin and light.",
        "fn": _teal_orange,
    },
    {
        "id": "kodak",
        "label": "Warm film",
        "description": "Creamy and warm, green in the shadows.",
        "fn": _kodak,
    },
    {
        "id": "bleach",
        "label": "Bleach bypass",
        "description": "Desaturated and contrasty.",
        "fn": _bleach,
    },
    {
        "id": "night",
        "label": "Night",
        "description": "Cool, dim, highlights pulled down.",
        "fn": _night,
    },
    {"id": "sepia", "label": "Sepia", "description": "Single warm tone.", "fn": _sepia},
    {
        "id": "vhs",
        "label": "Tape",
        "description": "Magenta lift, green mids, crushed blacks.",
        "fn": _vhs,
    },
    {
        "id": "dream",
        "label": "Dream",
        "description": "Pale, soft and slightly pink.",
        "fn": _dream,
    },
]
BY_ID = {g["id"]: g for g in GRADES}


def grades_as_list():
    return [{k: v for k, v in g.items() if k != "fn"} for g in GRADES]


def ids():
    return [g["id"] for g in GRADES]


def apply_grade(frame, grade_id, amount=1.0):
    """Blend a grade over the frame in place. `amount` 0 leaves it untouched."""
    grade = BY_ID.get(str(grade_id or "none"))
    if not grade or grade["fn"] is None:
        return frame
    a = max(0.0, min(1.0, float(amount)))
    if a <= 0.001:
        return frame
    graded = np.clip(grade["fn"](frame.copy()), 0.0, 255.0)
    frame *= 1.0 - a
    frame += graded * a
    return frame
