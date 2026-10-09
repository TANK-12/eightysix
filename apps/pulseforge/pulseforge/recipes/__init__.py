"""
The Autopilot recipe registry.

A recipe is a whole channel style in one small file: which scene renders it,
which output format it targets, the scene params tuned to look good with no
further editing, and the mood words used when Jan drafts the upload text. This
module only auto-discovers the recipe modules under this package and exposes
them as one table — adding a recipe is one new file plus one line in
`_MODULES` below, nothing else in the app changes.

Each recipe module sets a module-level `RECIPE` dict:

    {
        "id": "lofi_drift",              # stable id, used as a key everywhere
        "label": "Lofi Drift",           # shown in the picker
        "description": "...",            # one line, shown under the label
        "scene": "drift",                # must be a real pulseforge.scenes id
        "format": "long_1080p",          # must be a real pulseforge.formats id
        "params": {...},                 # scene params, pre-tuned
        "preset": "lofi_lake",           # optional — a pulseforge.presets id
        "minutes": 60,                   # optional — repeat the finished pass to this length
        "mood": "warm, unhurried, ...",  # fed to jan.write_upload_text
        "thumb_subtitle": "lofi beats",  # small text under the thumbnail title
        "tagline": "...",                # optional -- template title after "|"; {length}
        "per": "song",                   # optional -- "folder" makes one mix of the inbox
        "needs_art": False,              # optional -- refuse a run with no pictures
        "look": {...},                   # optional -- living scenes: preset, grade
        "ambience": {...},               # optional -- living scenes: {"bed", "level"}
    }

A recipe that fails to import is skipped and logged rather than taking the
whole registry down with it, the same rule the scene registry follows.
"""

import importlib

_MODULES = [
    "pulseforge.recipes.lofi_radio",
    "pulseforge.recipes.lofi_drift",
    "pulseforge.recipes.visualiser_bars",
    "pulseforge.recipes.shorts_pulse",
]

RECIPES = {}

for _mod_name in _MODULES:
    try:
        _m = importlib.import_module(_mod_name)
        RECIPES[_m.RECIPE["id"]] = _m.RECIPE
    except Exception as e:  # pragma: no cover - a broken recipe shouldn't kill the app
        print(f"[pulseforge] recipe {_mod_name} failed to load: {e}")


def get_recipe(recipe_id):
    if recipe_id not in RECIPES:
        raise KeyError(f"no such recipe: {recipe_id}")
    return RECIPES[recipe_id]


def recipes_as_list():
    return [{"id": k, **v} for k, v in RECIPES.items()]
