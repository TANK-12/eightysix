"""
The region-effect registry.

A motion effect is one file in this folder that defines `EFFECT` (id, label,
family, description and a parameter schema) and `apply(frame, mask, box, tl, p,
ctx)`, plus one line in `_MODULES` below. Nothing else changes: the API, the
editor's effect picker and its parameter form are all generated from this
table, so adding "leaves rustling" is a new file and a new line, never an edit
to five call sites.

The contract:

    frame   (H, W, 3) float32 in [0, 255] -- modify in place
    mask    (H, W)    float32 in [0, 1]   -- how much of the frame is yours
    box     (y0, y1, x0, x1)              -- the mask's bounding box; stay in it
    tl      looping.LoopClock             -- ask it for phases, never use raw t
    p       params, already merged with the schema's defaults
    ctx     the scene context (size, fps, assets, quality)

Families: "geometry" (moves pixels) | "light" (changes brightness or colour) |
"custom" (plays the user's own artwork).
"""

import importlib

from .. import modulation

_MODULES = [
    "pulseforge.motion.water",
    "pulseforge.motion.sway",
    "pulseforge.motion.flow",
    "pulseforge.motion.sky_clouds",
    "pulseforge.motion.shimmer",
    "pulseforge.motion.rays",
    "pulseforge.motion.glass_rain",
    "pulseforge.motion.reflection",
    "pulseforge.motion.fog",
    "pulseforge.motion.glow_pulse",
    "pulseforge.motion.flicker",
    "pulseforge.motion.breathe",
    "pulseforge.motion.frames",
]

EFFECTS = {}
_APPLY_FNS = {}

for _mod_name in _MODULES:
    try:
        _m = importlib.import_module(_mod_name)
        EFFECTS[_m.EFFECT["id"]] = _m.EFFECT
        _APPLY_FNS[_m.EFFECT["id"]] = _m.apply
    except Exception as e:  # pragma: no cover - one broken effect must not kill the app
        print(f"[pulseforge] motion effect {_mod_name} failed to load: {e}")


def get_effect(effect_id):
    if effect_id not in EFFECTS:
        raise KeyError(f"no such motion effect: {effect_id}")
    return EFFECTS[effect_id], _APPLY_FNS[effect_id]


def defaults_for(effect_id):
    meta = EFFECTS.get(effect_id) or {}
    return {p["key"]: p.get("default") for p in meta.get("params", [])}


def merge_params(effect_id, params, tl=None):
    """Schema defaults, the user's values on top, then modulation resolved.

    A saved layer never has to carry every key, so adding a parameter to an
    effect does not break old projects. Any value may also be a modulation
    object rather than a number -- this is the one place that gets unpacked,
    which is why `modulation.py` works for everything in the registry without a
    line of per-effect code.
    """
    merged = defaults_for(effect_id)
    for k, v in (params or {}).items():
        if v is not None:
            merged[k] = v
    specs = {p["key"]: p for p in (EFFECTS.get(effect_id) or {}).get("params", [])}
    return modulation.resolve_all(merged, tl, specs)


def apply_effect(effect_id, frame, mask, box, tl, params, ctx):
    _meta, fn = get_effect(effect_id)
    return fn(frame, mask, box, tl, merge_params(effect_id, params, tl), ctx)


def effects_as_list():
    order = {"geometry": 0, "light": 1, "custom": 2}
    return sorted(
        ({"id": k, **v} for k, v in EFFECTS.items()),
        key=lambda e: (order.get(str(e.get("family") or ""), 9), e["id"]),
    )
