"""
The sprite / particle registry.

An emitter is one file in this folder defining `EMITTER` (id, label, family,
description, param schema) and `draw(frame, tl, p, ctx, mask, offset)`, plus one
line in `_MODULES`. Same deal as the motion effects: the picker and the
parameter form in the editor are generated from this table.

Two rules every emitter follows:

* **Deterministic from time.** A particle's identity comes from a seeded RNG
  drawn once, and its position from a loop-wrapped phase -- never from state
  carried between frames. That is what lets a shot be rendered as a short bed
  and repeated without anything jumping.
* **It may be confined.** If a mask is passed, the emitter draws only inside it,
  which is how fish stay in the pond.

Families: "particles" (many small marks) | "creatures" (a few moving things) |
"custom" (the user's own artwork).
"""

import importlib

from .. import modulation

_MODULES = [
    "pulseforge.emitters.particles",
    "pulseforge.emitters.rain",
    "pulseforge.emitters.snow",
    "pulseforge.emitters.dust",
    "pulseforge.emitters.fireflies",
    "pulseforge.emitters.bubbles",
    "pulseforge.emitters.stars",
    "pulseforge.emitters.leaves",
    "pulseforge.emitters.birds",
    "pulseforge.emitters.fish",
    "pulseforge.emitters.sprites",
]

EMITTERS = {}
_DRAW_FNS = {}

for _mod_name in _MODULES:
    try:
        _m = importlib.import_module(_mod_name)
        EMITTERS[_m.EMITTER["id"]] = _m.EMITTER
        _DRAW_FNS[_m.EMITTER["id"]] = _m.draw
    except (
        Exception
    ) as e:  # pragma: no cover - one broken emitter must not kill the app
        print(f"[pulseforge] emitter {_mod_name} failed to load: {e}")


def get_emitter(emitter_id):
    if emitter_id not in EMITTERS:
        raise KeyError(f"no such emitter: {emitter_id}")
    return EMITTERS[emitter_id], _DRAW_FNS[emitter_id]


def defaults_for(emitter_id):
    meta = EMITTERS.get(emitter_id) or {}
    return {p["key"]: p.get("default") for p in meta.get("params", [])}


def merge_params(emitter_id, params, tl=None):
    """Schema defaults, the user's values on top, then modulation resolved.

    A saved layer never has to carry every key, so adding a parameter to an
    emitter does not break old projects. Any value may also be a modulation
    object rather than a number -- this is the one place that gets unpacked,
    which is why `modulation.py` works for everything in the registry without a
    line of per-emitter code.
    """
    merged = defaults_for(emitter_id)
    for k, v in (params or {}).items():
        if v is not None:
            merged[k] = v
    specs = {p["key"]: p for p in (EMITTERS.get(emitter_id) or {}).get("params", [])}
    return modulation.resolve_all(merged, tl, specs)


def draw_emitter(emitter_id, frame, tl, params, ctx, mask=None, offset=(0.0, 0.0)):
    _meta, fn = get_emitter(emitter_id)
    return fn(frame, tl, merge_params(emitter_id, params, tl), ctx, mask, offset)


def emitters_as_list():
    order = {"particles": 0, "creatures": 1, "custom": 2}
    return sorted(
        ({"id": k, **v} for k, v in EMITTERS.items()),
        key=lambda e: (order.get(str(e.get("family") or ""), 9), e["id"]),
    )
