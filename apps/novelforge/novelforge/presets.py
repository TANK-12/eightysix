"""Genre presets: how a Korean hunter web novel, a rofan or a cozy mystery
should sound and be shaped.

One JSON file per preset in `novelforge/presets/`, found by scanning the
folder, so adding a genre is one new file and nothing else. `_common.json`
(files starting with "_" are not presets) holds the voice rules and worn
phrases that apply to every genre.

A preset's `structure` is a list of anchors: `at` is a position in the book
from 0.0 (first chapter) to 1.0 (last), `role` and `guide` say what that
chapter must do, `then` says what the chapters after it do until the next
anchor, and `key` marks anchors that must survive in a short book. The code,
not the model, maps these onto chapter numbers (`chapter_roles`), which is what
lets a small model write a usable outline: it only has to fill in one
chapter's job at a time.
"""

from __future__ import annotations

import json
import os
import re

PRESETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "presets")
DEFAULT_ID = "general"
REQUIRED = ("id", "label", "voice", "structure")
DEFAULT_BUILD = (
    "Escalate: a new obstacle, a gain that costs something, or a relationship "
    "that shifts. Something concrete must change by the end of the chapter."
)

_FIELDS = {
    "group": "Other",
    "description": "",
    "keywords": [],
    "words_per_chapter": 3000,
    "voice": [],
    "structure": [],
    "outline_guidance": "",
    "outline_example": "",
    "scene_guidance": [],
    "worldbuilding": [],
    "naming": "",
    "cliches": [],
    "sample": "",
}


def _read(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def load_presets(folder: str = PRESETS_DIR) -> dict[str, dict]:
    """Every valid preset in the folder, by id. A broken file is skipped, so
    one bad edit never takes the whole list down."""
    common = _read(os.path.join(folder, "_common.json")) or {}
    out: dict[str, dict] = {}
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return out
    for name in names:
        if not name.endswith(".json") or name.startswith("_"):
            continue
        data = _read(os.path.join(folder, name))
        if not isinstance(data, dict) or any(k not in data for k in REQUIRED):
            continue
        preset = {**_FIELDS, **data}
        preset["common_voice"] = list(common.get("voice") or [])
        preset["common_cliches"] = list(common.get("cliches") or [])
        out[str(preset["id"])] = preset
    return out


def summaries(folder: str = PRESETS_DIR) -> list[dict]:
    """What the Story tab's picker needs, grouped and in a stable order."""
    rows = [
        {
            "id": p["id"],
            "label": p["label"],
            "group": p["group"],
            "description": p["description"],
            "words_per_chapter": p["words_per_chapter"],
        }
        for p in load_presets(folder).values()
    ]
    return sorted(rows, key=lambda r: (r["group"], r["label"]))


def guess_preset_id(text: str, presets: dict[str, dict]) -> str:
    """The preset whose keywords best match a genre/title line, else general."""
    words = set(re.findall(r"[a-z]+", (text or "").lower()))
    best, best_hits = DEFAULT_ID, 0
    for pid, preset in presets.items():
        hits = sum(1 for k in preset.get("keywords") or [] if k.lower() in words)
        if hits > best_hits:
            best, best_hits = pid, hits
    return best


def preset_for_bible(bible: dict, folder: str = PRESETS_DIR) -> dict:
    """The bible's chosen preset; blank means 'guess from the genre'."""
    presets = load_presets(folder)
    pid = (bible.get("preset") or "").strip()
    if pid not in presets:
        pid = guess_preset_id(
            f"{bible.get('genre', '')} {bible.get('title', '')}", presets
        )
    return presets.get(pid) or presets.get(DEFAULT_ID) or {**_FIELDS, "id": DEFAULT_ID}


def all_cliches(preset: dict) -> list[str]:
    seen, out = set(), []
    for phrase in list(preset.get("common_cliches") or []) + list(
        preset.get("cliches") or []
    ):
        key = phrase.lower().strip()
        if key and key not in seen:
            seen.add(key)
            out.append(phrase.strip())
    return out


def chapter_roles(structure: list[dict], n: int) -> list[dict]:
    """Map a preset's anchors onto chapters 1..n.

    Each anchor claims the chapter nearest its position; key anchors choose
    first so a 5-chapter book still gets its hook, climax and ending. A
    non-key anchor that finds no free chapter within two of its place is
    dropped. Chapters no anchor claimed take the previous anchor's `then`."""
    n = max(1, int(n))
    anchors = sorted(
        (a for a in structure or [] if isinstance(a, dict) and a.get("role")),
        key=lambda a: float(a.get("at", 0.0)),
    )
    order = sorted(range(len(anchors)), key=lambda i: (not anchors[i].get("key"), i))
    claimed: dict[int, dict] = {}
    for i in order:
        anchor = anchors[i]
        at = min(1.0, max(0.0, float(anchor.get("at", 0.0))))
        want = 1 + round(at * (n - 1))
        reach = n if anchor.get("key") else 2
        for dist in range(reach + 1):
            slot = next(
                (
                    c
                    for c in (want + dist, want - dist)
                    if 1 <= c <= n and c not in claimed
                ),
                None,
            )
            if slot is not None:
                claimed[slot] = anchor
                break
    roles, last = [], None
    for c in range(1, n + 1):
        anchor = claimed.get(c)
        if anchor:
            roles.append(
                {"chapter": c, "role": anchor["role"], "guide": anchor.get("guide", "")}
            )
            last = anchor
        else:
            roles.append(
                {
                    "chapter": c,
                    "role": "build",
                    "guide": (last or {}).get("then") or DEFAULT_BUILD,
                }
            )
    return roles
