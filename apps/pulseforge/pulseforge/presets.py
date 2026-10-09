"""
Preset looks -- a whole shot in one click.

Each preset is a partial shot: a grade, a camera move, some emitters, and a
note of which auto-detected regions it wants and what to run on them. Applying
one to a background gives something finished to react to, which beats starting
from an empty region list and a wall of sliders.

Adding a built-in preset is one entry in `BUILTIN`; the user's own saved looks
are folders under `~/PulseForgeData/presets/` and appear in the same list. Nothing else changes -- the picker
in the editor is generated from this list, same as everything else here.

`auto` names the regions from `autoregions.suggest()` this preset wants, mapped
to the effect and parameters it wants on them. A region that is not found is
simply skipped, so a preset never fails on an image that does not suit it -- it
just does less.
"""

import copy
import json
import re
import shutil
import time
from pathlib import Path

from . import config

BUILTIN = [
    {
        "id": "lofi_lake",
        "label": "Lofi lake",
        "description": "Clouds crossing the sky, the water breathing, a few "
        "birds and some dust in the light. The default warm "
        "study-beats look.",
        "auto": {
            "sky": ("sky_clouds", {"amount": 0.45, "speed": 0.2, "coverage": 0.5}),
            "water": ("water", {"strength": 0.3, "speed": 0.25, "glint": 0.25}),
            "foliage": ("sway", {"strength": 0.2, "speed": 0.25}),
        },
        "shot": {
            "camera": {"push": 0.06, "drift": 0.35, "parallax": 0.5},
            "look": {
                "vignette": 0.3,
                "grain": 0.07,
                "bloom": 0.18,
                "saturation": 1.04,
                "warmth": 0.18,
            },
            "emitters": [
                {
                    "id": "birds",
                    "depth": 0.3,
                    "params": {"count": 7, "size": 0.35, "height": 0.25, "speed": 0.25},
                },
                {
                    "id": "dust",
                    "depth": 0.85,
                    "params": {"count": 70, "size": 0.15, "opacity": 0.4},
                },
            ],
        },
    },
    {
        "id": "rainy_window",
        "label": "Rainy window",
        "description": "Steady rain, a cool desaturated grade and a soft bloom. "
        "Indoors looking out.",
        "auto": {"lights": ("glow_pulse", {"strength": 0.35, "speed": 0.12})},
        "shot": {
            "camera": {"push": 0.03, "drift": 0.15, "parallax": 0.3},
            "look": {
                "vignette": 0.42,
                "grain": 0.12,
                "bloom": 0.3,
                "saturation": 0.82,
                "warmth": -0.12,
            },
            "emitters": [
                {
                    "id": "rain",
                    "depth": 0.9,
                    "params": {"count": 260, "speed": 0.62, "opacity": 0.3},
                },
                {
                    "id": "rain",
                    "depth": 0.2,
                    "params": {
                        "count": 90,
                        "speed": 0.35,
                        "length": 0.5,
                        "opacity": 0.16,
                    },
                },
            ],
        },
    },
    {
        "id": "night_sky",
        "label": "Night sky",
        "description": "Stars turning slowly overhead with fireflies below. "
        "Deep and quiet.",
        "auto": {
            "sky": ("sky_clouds", {"amount": 0.18, "speed": 0.1, "coverage": 0.25}),
            "water": ("water", {"strength": 0.18, "speed": 0.15, "glint": 0.4}),
        },
        "shot": {
            "camera": {"push": 0.05, "drift": 0.2, "parallax": 0.4},
            "look": {
                "vignette": 0.45,
                "grain": 0.09,
                "bloom": 0.25,
                "saturation": 0.9,
                "warmth": -0.2,
            },
            "emitters": [
                {
                    "id": "stars",
                    "depth": 0.05,
                    "params": {"count": 220, "twinkle": 0.6, "size": 0.2},
                    "region": {
                        "kind": "polygon",
                        "points": [[0, 0], [1, 0], [1, 0.55], [0, 0.55]],
                        "feather": 0.1,
                    },
                },
                {
                    "id": "fireflies",
                    "depth": 0.8,
                    "params": {"count": 22, "blink": 0.8},
                },
            ],
        },
    },
    {
        "id": "forest",
        "label": "Forest light",
        "description": "Leaves stirring, motes hanging in the shafts of light. "
        "Green and close.",
        "auto": {
            "foliage": ("sway", {"strength": 0.3, "speed": 0.3, "gust": 0.5}),
            "lights": ("shimmer", {"strength": 0.25, "speed": 0.3}),
        },
        "shot": {
            "camera": {"push": 0.08, "drift": 0.3, "parallax": 0.6},
            "look": {
                "vignette": 0.38,
                "grain": 0.08,
                "bloom": 0.28,
                "saturation": 1.1,
                "warmth": 0.12,
            },
            "emitters": [
                {
                    "id": "dust",
                    "depth": 0.85,
                    "params": {
                        "count": 120,
                        "size": 0.2,
                        "twinkle": 0.6,
                        "opacity": 0.55,
                    },
                },
            ],
        },
    },
    {
        "id": "snowfall",
        "label": "Snowfall",
        "description": "Slow flakes and a cold, soft grade.",
        "auto": {"sky": ("sky_clouds", {"amount": 0.3, "speed": 0.15})},
        "shot": {
            "camera": {"push": 0.05, "drift": 0.25, "parallax": 0.45},
            "look": {
                "vignette": 0.34,
                "grain": 0.08,
                "bloom": 0.3,
                "saturation": 0.78,
                "warmth": -0.15,
            },
            "emitters": [
                {
                    "id": "snow",
                    "depth": 0.9,
                    "params": {"count": 170, "speed": 0.2, "sway": 0.6},
                },
                {
                    "id": "snow",
                    "depth": 0.15,
                    "params": {
                        "count": 60,
                        "speed": 0.12,
                        "size": 0.15,
                        "opacity": 0.4,
                    },
                },
            ],
        },
    },
    {
        "id": "autumn",
        "label": "Autumn",
        "description": "Leaves tumbling down through a warm amber grade.",
        "auto": {"foliage": ("sway", {"strength": 0.3, "speed": 0.32, "gust": 0.6})},
        "shot": {
            "camera": {"push": 0.06, "drift": 0.3, "parallax": 0.5},
            "look": {
                "vignette": 0.34,
                "grain": 0.09,
                "bloom": 0.2,
                "saturation": 1.12,
                "warmth": 0.3,
            },
            "emitters": [
                {
                    "id": "leaves",
                    "depth": 0.85,
                    "params": {
                        "shape": "leaf",
                        "count": 34,
                        "speed": 0.3,
                        "tumble": 0.75,
                    },
                },
            ],
        },
    },
    {
        "id": "sakura",
        "label": "Blossom",
        "description": "Petals drifting, branches stirring, soft pink light.",
        "auto": {"foliage": ("sway", {"strength": 0.24, "speed": 0.25})},
        "shot": {
            "camera": {"push": 0.05, "drift": 0.3, "parallax": 0.55},
            "look": {
                "vignette": 0.3,
                "grain": 0.06,
                "bloom": 0.3,
                "saturation": 1.06,
                "warmth": 0.2,
            },
            "emitters": [
                {
                    "id": "leaves",
                    "depth": 0.85,
                    "params": {
                        "shape": "petal",
                        "count": 46,
                        "speed": 0.26,
                        "color": "#ffc7dd",
                        "sway": 0.7,
                    },
                },
            ],
        },
    },
    {
        "id": "underwater",
        "label": "Underwater",
        "description": "Bubbles rising, fish crossing, light rippling over "
        "everything.",
        "auto": {},
        "shot": {
            "camera": {"push": 0.09, "drift": 0.4, "parallax": 0.5},
            "look": {
                "vignette": 0.45,
                "grain": 0.05,
                "bloom": 0.25,
                "saturation": 1.05,
                "warmth": -0.25,
            },
            "layers": [
                {
                    "name": "everything",
                    "effect": "shimmer",
                    "region": {"kind": "all", "feather": 0.0},
                    "params": {
                        "strength": 0.2,
                        "distort": 0.35,
                        "speed": 0.3,
                        "radius": 0.4,
                    },
                },
            ],
            "emitters": [
                {"id": "bubbles", "depth": 0.8, "params": {"count": 50}},
                {
                    "id": "fish",
                    "depth": 0.4,
                    "params": {"count": 8, "speed": 0.22, "size": 0.28},
                },
            ],
        },
    },
    {
        "id": "city_night",
        "label": "City night",
        "description": "Signs pulsing, rain falling, heavy bloom on the lights.",
        "auto": {"lights": ("glow_pulse", {"strength": 0.45, "speed": 0.25})},
        "shot": {
            "camera": {"push": 0.07, "drift": 0.3, "parallax": 0.55},
            "look": {
                "vignette": 0.5,
                "grain": 0.13,
                "bloom": 0.42,
                "saturation": 1.18,
                "warmth": -0.05,
            },
            "emitters": [
                {
                    "id": "rain",
                    "depth": 0.9,
                    "params": {"count": 200, "speed": 0.7, "opacity": 0.24},
                },
            ],
        },
    },
    {
        "id": "sunset",
        "label": "Sunset",
        "description": "Long clouds, glinting water, birds heading home.",
        "auto": {
            "sky": (
                "sky_clouds",
                {"amount": 0.55, "speed": 0.14, "scale": 0.75, "tint": "#ffd9b3"},
            ),
            "water": ("water", {"strength": 0.34, "speed": 0.22, "glint": 0.45}),
        },
        "shot": {
            "camera": {"push": 0.05, "drift": 0.25, "parallax": 0.45},
            "look": {
                "vignette": 0.32,
                "grain": 0.06,
                "bloom": 0.35,
                "saturation": 1.15,
                "warmth": 0.4,
            },
            "emitters": [
                {
                    "id": "birds",
                    "depth": 0.3,
                    "params": {
                        "count": 12,
                        "formation": 0.5,
                        "size": 0.3,
                        "height": 0.22,
                    },
                },
            ],
        },
    },
    {
        "id": "minimal",
        "label": "Barely there",
        "description": "No particles, no effects -- just a very slow push, a "
        "vignette and some grain. The most restrained option, and "
        "often the right one.",
        "auto": {},
        "shot": {
            "camera": {"push": 0.05, "drift": 0.2, "parallax": 0.3},
            "look": {
                "vignette": 0.28,
                "grain": 0.06,
                "bloom": 0.1,
                "saturation": 1.0,
                "warmth": 0.05,
            },
            "emitters": [],
        },
    },
]

BY_ID = {p["id"]: p for p in BUILTIN}


# --------------------------------------------------------------------------
# looks the user saved themselves
#
# A saved preset is a folder, not a file, because a shot's regions are painted
# PNGs: storing them alongside the JSON and copying them into whichever project
# the preset is applied to is what makes a saved look actually portable rather
# than a set of dangling filenames.
# --------------------------------------------------------------------------
def user_dir():
    d = config.PRESETS_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _slug(name):
    s = re.sub(r"[^a-zA-Z0-9 _-]", "", str(name)).strip().lower()
    return re.sub(r"[ _]+", "-", s) or f"preset-{int(time.time())}"


def load_user():
    """Every saved preset, newest first. A broken one is skipped, not fatal."""
    out = []
    for folder in sorted(user_dir().iterdir() if user_dir().exists() else []):
        meta = folder / "preset.json"
        if not folder.is_dir() or not meta.exists():
            continue
        try:
            data = json.loads(meta.read_text("utf-8"))
        except Exception:
            continue
        data["id"] = f"user:{folder.name}"
        data["user"] = True
        data["_dir"] = str(folder)
        out.append(data)
    return sorted(out, key=lambda d: d.get("saved", 0), reverse=True)


def save_user_preset(name, shot, mask_dir=None):
    """Store a shot as a reusable look, bringing its painted regions along."""
    folder = user_dir() / _slug(name)
    n = 2
    while folder.exists():
        folder = user_dir() / f"{_slug(name)}-{n}"
        n += 1
    (folder / "masks").mkdir(parents=True, exist_ok=True)

    keep = {
        k: copy.deepcopy(v)
        for k, v in (shot or {}).items()
        if k in ("layers", "images", "emitters", "camera", "look", "loop_seconds")
    }
    for layer in keep.get("layers") or []:
        region = layer.get("region") or {}
        brush = region.get("brush")
        if brush and mask_dir:
            src = Path(mask_dir) / brush
            if src.exists():
                shutil.copyfile(src, folder / "masks" / brush)
    # a stacked image points at a file in its own project; the reference is
    # kept so it reconnects if the same filename is there, but it is not copied
    (folder / "preset.json").write_text(
        json.dumps(
            {
                "label": str(name),
                "description": "Saved from a shot you built.",
                "shot": keep,
                "auto": {},
                "saved": time.time(),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return f"user:{folder.name}"


def delete_user_preset(preset_id):
    if not str(preset_id).startswith("user:"):
        raise KeyError("only your own presets can be deleted")
    folder = user_dir() / str(preset_id).split(":", 1)[1]
    if folder.exists() and folder.parent == user_dir():
        shutil.rmtree(folder, ignore_errors=True)
        return True
    return False


def get(preset_id):
    if preset_id in BY_ID:
        return BY_ID[preset_id]
    for p in load_user():
        if p["id"] == preset_id:
            return p
    raise KeyError(f"no such preset: {preset_id}")


def presets_as_list():
    out = [{k: v for k, v in p.items() if k not in ("shot", "auto")} for p in BUILTIN]
    out += [
        {k: v for k, v in p.items() if k not in ("shot", "auto", "_dir")}
        for p in load_user()
    ]
    return out


def apply_to(preset_id, shot, suggestions=None, mask_dir=None):
    """A new shot: `shot`'s image and framing, the preset's look and motion.

    `suggestions` is what `autoregions.suggest()` found, already saved as brush
    regions by the caller. Regions the preset does not ask for are left alone,
    and regions it asks for but that were not found are skipped.
    """
    preset = get(preset_id)

    out = dict(shot or {})
    template = preset["shot"]
    for key in ("camera", "look"):
        merged = dict(out.get(key) or {})
        merged.update(template.get(key) or {})
        out[key] = merged
    out["emitters"] = [dict(e) for e in (template.get("emitters") or [])]

    if preset.get("loop_seconds"):
        out.setdefault("loop_seconds", preset["loop_seconds"])
    if template.get("images"):
        out["images"] = copy.deepcopy(template["images"])

    layers = [copy.deepcopy(layer) for layer in (template.get("layers") or [])]
    # a saved preset brings its painted regions with it -- copy them into this
    # project so editing them here cannot change the preset or another project
    src_masks = Path(preset["_dir"]) / "masks" if preset.get("_dir") else None
    if src_masks and mask_dir:
        Path(mask_dir).mkdir(parents=True, exist_ok=True)
        for layer in layers:
            region = layer.get("region") or {}
            brush = region.get("brush")
            if not brush:
                continue
            src = src_masks / brush
            if not src.exists():
                continue
            dst_name = f"{_slug(preset.get('label', 'preset'))}-{brush}"
            shutil.copyfile(src, Path(mask_dir) / dst_name)
            region["brush"] = dst_name
    wanted = preset.get("auto") or {}
    for found in suggestions or []:
        rule = wanted.get(found.get("name"))
        if not rule:
            continue
        effect, params = rule
        layers.append(
            {
                "name": found["name"],
                "effect": effect,
                "params": dict(params),
                "region": found["region"],
                "depth": {"sky": 0.0, "water": 0.1, "foliage": 0.4}.get(
                    found["name"], 0.2
                ),
            }
        )
    out["layers"] = layers
    out["preset"] = preset_id
    return out
