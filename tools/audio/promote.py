#!/usr/bin/env python3
"""Puts reviewed sounds into the game (lane B4).

Reads the listening page's decisions (assets/audio/review/review.json: {"<file>": "keep" | "drop"}),
copies every kept take of each recipe into assets/audio/sfx/, and writes one data/sounds.json entry per
recipe with its takes and the playback defaults of its bus. A take with no decision counts as kept, so
the game has sound before anything is reviewed; a recipe with every take dropped is left out.

Usage: tools/audio/promote.py [--dry]
"""

import json
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
RECIPES = ROOT / "tools/audio/recipes.json"
REVIEW = ROOT / "assets/audio/review"
SFX = ROOT / "assets/audio/sfx"
SOUNDS = ROOT / "data/sounds.json"

# Playback defaults per bus: how far a sound carries and how it falls off. unit_size is the distance
# (m) at which it plays at full volume; max_distance_m is where it is cut. Guns and impacts carry
# across the valley; mech noises are local. "2d" sounds are not placed in the world.
BUS_DEFAULTS = {
    "weapons": {
        "unit_size": 40.0,
        "max_distance_m": 2500.0,
        "attenuation": "inverse",
        "delay_by_distance": True,
    },
    "impacts": {
        "unit_size": 20.0,
        "max_distance_m": 1500.0,
        "attenuation": "inverse",
        "delay_by_distance": True,
    },
    "mech": {
        "unit_size": 8.0,
        "max_distance_m": 400.0,
        "attenuation": "inverse",
        "delay_by_distance": False,
    },
    "ambience": {"2d": True},
    "ui": {"2d": True},
}


def decisions() -> dict:
    path = REVIEW / "review.json"
    return json.loads(path.read_text()) if path.exists() else {}


def build(dry: bool) -> dict:
    recipes = json.loads(RECIPES.read_text())["entries"]
    picks = decisions()
    entries = {}
    for rid, recipe in recipes.items():
        files = []
        for v in range(int(recipe.get("variants", 1))):
            name = f"{rid}_{v + 1}.wav"
            if picks.get(f"synth/{name}", "keep") != "keep":
                continue
            files.append(f"res://assets/audio/sfx/{name}")
            if not dry:
                SFX.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REVIEW / "synth" / name, SFX / name)
        if not files:
            continue
        entry = {
            "label": recipe.get("label", rid),
            "files": files,
            "bus": recipe["bus"],
            "volume_db": float(recipe.get("volume_db", 0.0)),
            "pitch_jitter": 0.04,
        }
        entry.update(BUS_DEFAULTS.get(recipe["bus"], {}))
        if recipe.get("max_voices"):
            entry["max_voices"] = int(recipe["max_voices"])
        if recipe.get("loop"):
            entry["loop"] = True
            entry["pitch_jitter"] = 0.0
        entries[rid] = entry
    return entries


def main() -> None:
    dry = "--dry" in sys.argv
    data = json.loads(SOUNDS.read_text())
    data["entries"] = build(dry)
    if dry:
        print(json.dumps(data["entries"], indent=1)[:2000])
        return
    SOUNDS.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"{len(data['entries'])} sounds in data/sounds.json")


if __name__ == "__main__":
    main()
