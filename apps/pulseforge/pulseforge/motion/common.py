"""
Shared parameter builders.

Every effect reaches for the same handful of controls -- strength, speed,
direction, radius -- and they should feel identical everywhere: the same range,
the same slider, the same wording. Building them here rather than retyping a
dict in nine files is what keeps that true.

`speed` is exposed as a 0..1 dial and converted to a period in seconds by
`period_from_speed()`, because "how fast" is what you actually want to think
about, while the renderer needs a period it can snap to the loop.
"""


def strength(default=0.35, label="Strength", maximum=1.0):
    return {
        "key": "strength",
        "label": label,
        "type": "range",
        "default": default,
        "min": 0.0,
        "max": maximum,
        "step": 0.01,
    }


def speed(default=0.35, label="Speed"):
    return {
        "key": "speed",
        "label": label,
        "type": "range",
        "default": default,
        "min": 0.0,
        "max": 1.0,
        "step": 0.01,
        "help": "Snapped to the nearest whole number of cycles in the loop.",
    }


def direction(default=90, label="Direction"):
    return {
        "key": "direction",
        "label": label,
        "type": "angle",
        "default": default,
        "min": 0,
        "max": 359,
        "step": 1,
    }


def radius(default=0.3, label="Radius", maximum=1.0):
    return {
        "key": "radius",
        "label": label,
        "type": "range",
        "default": default,
        "min": 0.0,
        "max": maximum,
        "step": 0.01,
    }


def length(default=120.0, label="Wave length", minimum=8.0, maximum=600.0):
    return {
        "key": "wave_length",
        "label": label,
        "type": "range",
        "default": default,
        "min": minimum,
        "max": maximum,
        "step": 1,
        "unit": "px",
    }


def amount(key, default, label, maximum=1.0, step=0.01):
    return {
        "key": key,
        "label": label,
        "type": "range",
        "default": default,
        "min": 0.0,
        "max": maximum,
        "step": step,
    }


def period_from_speed(sp, slowest=18.0, fastest=1.2):
    """0 = barely moving, 1 = brisk. Returns a period in seconds."""
    sp = min(1.0, max(0.0, float(sp)))
    return slowest + (fastest - slowest) * sp
