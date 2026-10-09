"""The Crew Room's rooms and sprites, kept in the shared Forge art library.

Sprites are ordinary packs (packs/crewroom-*.json) and a palette
(palettes/crewroom.json), so PixelForge edits them like any other art. Rooms
are layout JSON in packs/crewroom/rooms/<room>.json; a subfolder, so the pack
scanner ignores them. Adding a room is one new file there.

The app ships defaults in seed/, laid out the same way. A missing file is
copied in at startup; one that exists is never overwritten, because it may
hold Emerson's edits.
"""

from __future__ import annotations

import json
import os
import shutil

import forge_art

ROOT = os.path.dirname(os.path.abspath(__file__))
SEED_DIR = os.path.join(ROOT, "seed")
PREFIX = "crewroom"


def rooms_dir() -> str:
    return os.path.join(forge_art.packs_dir(), PREFIX, "rooms")


def ensure_seeded(seed_dir: str | None = None) -> list[str]:
    """Copy seed files that are missing from the art library. Returns the
    relative paths copied."""
    seed_dir = seed_dir or SEED_DIR
    copied = []
    root = forge_art.art_root()
    for folder, _dirs, files in os.walk(seed_dir):
        for name in files:
            if not name.endswith(".json"):
                continue
            source = os.path.join(folder, name)
            relative = os.path.relpath(source, seed_dir)
            target = os.path.join(root, relative)
            if os.path.exists(target):
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            tmp = target + ".tmp"
            shutil.copyfile(source, tmp)
            os.replace(tmp, target)
            copied.append(relative)
    return sorted(copied)


def list_rooms() -> list[dict]:
    rooms = []
    folder = rooms_dir()
    if not os.path.isdir(folder):
        return rooms
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".json"):
            continue
        try:
            room = load_room(name[:-5])
        except (OSError, ValueError):
            continue
        rooms.append(
            {
                "id": room.get("id") or name[:-5],
                "label": room.get("label") or name[:-5],
                "order": room.get("order", 50),
            }
        )
    rooms.sort(key=lambda r: (r["order"], r["label"]))
    return rooms


def load_room(room_id: str) -> dict:
    path = os.path.join(rooms_dir(), f"{forge_art.slug(room_id)}.json")
    with open(path, encoding="utf-8") as fh:
        room = json.load(fh)
    if not isinstance(room, dict):
        raise ValueError(f"room {room_id} is not an object")
    return room


def library() -> dict:
    """Only this app's packs and palettes: the renderer has no use for the
    rest of the library."""
    lib = forge_art.library()
    return {
        "root": lib["root"],
        "packs": {k: v for k, v in lib["packs"].items() if k.startswith(PREFIX)},
        "palettes": {k: v for k, v in lib["palettes"].items() if k.startswith(PREFIX)},
    }
