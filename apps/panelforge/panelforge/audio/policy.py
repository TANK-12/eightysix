"""The sound policy: what the film does with echo, sound effects and music
unless a person placed them by hand.

Emerson (2026-09-20): the guessed acoustics put "the cool echo but in no
context" on voices, the synth sound effects "were too random and often
didn't make sense", and the music "didn't really happen". So by default the
voices are dry, no sound effect plays and no music plays; anything set by
hand (a line's room in the editor, a sound or music block with
source "user") still does. Stored in `<data root>/sound.json`.
"""

from __future__ import annotations

from .. import paths, store

ECHO_MODES = ("none", "comms", "scene")
# none: dry voices; comms: only the radio filter on comms lines; scene: the
# scene's guess (hall, void, vehicle ...) as before
DEFAULTS = {"echo": "none", "sfx": False, "music": False}


def path():
    return paths.DATA_ROOT / "sound.json"


def read() -> dict:
    doc = store.read(path(), {}) or {}
    out = dict(DEFAULTS)
    if doc.get("echo") in ECHO_MODES:
        out["echo"] = doc["echo"]
    for k in ("sfx", "music"):
        if isinstance(doc.get(k), bool):
            out[k] = doc[k]
    return out


def write(doc: dict) -> dict:
    cur = read()
    if doc.get("echo") in ECHO_MODES:
        cur["echo"] = doc["echo"]
    for k in ("sfx", "music"):
        if isinstance(doc.get(k), bool):
            cur[k] = doc[k]
    store.write(path(), cur)
    return cur


def by_hand(item: dict) -> bool:
    return item.get("source") == "user" or bool(item.get("edited"))


def apply_echo(em: dict, mode: str | None = None) -> dict:
    """The delivery with the policy's echo applied. A delivery set by hand
    (`source: "user"`) is left exactly as it is."""
    mode = mode or read()["echo"]
    if mode == "scene" or em.get("source") == "user":
        return em
    out = dict(em)
    keep_radio = mode == "comms" and out.get("eq") == "radio"
    if not keep_radio:
        out.pop("eq", None)
        out.pop("grit", None)
    out.pop("room", None)
    out["reverb"] = 0.0
    return out


def plays(item: dict, kind: str, pol: dict | None = None) -> bool:
    """Whether a sound effect or music block (`kind` "sfx" or "music") is
    heard under the policy."""
    pol = pol or read()
    return bool(pol.get(kind)) or by_hand(item)
