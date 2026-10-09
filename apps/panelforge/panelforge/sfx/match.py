"""Maps a drawn sound word (bubble kind "sfx", or scene.json sfx_text) to a
synth recipe, with fuzzy matching and an onomatopoeia rule: repeated letters
mean a longer or more-repeated hit ("BOOOOOM" is a longer boom, "RATATATATA"
is more shots than "RATATA").
"""

from __future__ import annotations

import difflib
import re

from . import recipes

# canonical word -> recipe name. Several spellings point at the same recipe.
KEYWORDS: dict[str, str] = {
    "clank": "clank",
    "clang": "clank",
    "klank": "clank",
    "boom": "boom",
    "kaboom": "boom",
    "budoom": "boom",
    "blam": "blam",
    "bang": "bang",
    "bam": "bang",
    "ratata": "ratatata",
    "ratatat": "ratatata",
    "ratatata": "ratatata",
    "tatata": "ratatata",
    "whoosh": "whoosh",
    "fwish": "whoosh",
    "swoosh": "whoosh",
    "woosh": "whoosh",
    "fsssh": "fsssh",
    "hiss": "fsssh",
    "sssh": "fsssh",
    "psssh": "fsssh",
    "clap": "clap",
    "slap": "clap",
    "ting": "ting",
    "ding": "ting",
    "chink": "ting",
    "slash": "slash",
    "shing": "slash",
    "shink": "slash",
    "stomp": "stomp",
    "thump": "stomp",
    "lunge": "lunge",
    "dash": "lunge",
    "zip": "lunge",
    "hum": "glow_hum",
    "buzz": "glow_hum",
    "vwoom": "glow_hum",
    "glow": "glow_hum",
    "crash": "crash",
    "smash": "crash",
    "shatter": "crash",
    "footsteps": "footsteps",
    "steps": "footsteps",
    "patter": "footsteps",
    "tap": "footsteps",
    "thud": "thud",
    "thunk": "thud",
}

_RUN = re.compile(r"([A-Za-z])\1{1,}")
_WORD = re.compile(r"[A-Za-z]+")


def collapse_repeats(word: str) -> tuple[str, int]:
    """'BOOOOOM' -> ('bom', 5): the longest run of a repeated letter, and the
    word with runs collapsed to one letter (for keyword matching)."""
    max_run = 1

    def _sub(m: re.Match) -> str:
        nonlocal max_run
        max_run = max(max_run, len(m.group(0)))
        return m.group(1)

    collapsed = _RUN.sub(_sub, word.lower())
    return collapsed, max_run


def match_word(word: str) -> tuple[str | None, float, int]:
    """-> (recipe_name or None, stretch, repeat_hint). repeat_hint is a
    suggested repeat count for multi-hit recipes, from word length."""
    collapsed, run_len = collapse_repeats(word)
    stretch = min(2.5, 1.0 + 0.18 * (run_len - 1))

    name = KEYWORDS.get(collapsed)
    if name is None:
        close = difflib.get_close_matches(collapsed, KEYWORDS.keys(), n=1, cutoff=0.6)
        name = KEYWORDS.get(close[0]) if close else None
    if name is None:
        return None, stretch, 1

    repeat_hint = max(1, round(len(collapsed) / 3))
    return name, stretch, repeat_hint


def match_text(text: str) -> tuple[str, dict]:
    """Match a whole sfx bubble/sfx_text string, e.g. 'RATATATATA!!' or
    'clank clank'. Falls back to 'thud' (a generic impact) if nothing
    matches, so auto-placement always produces something rather than
    silently skipping the panel."""
    words = _WORD.findall(text) or [text]
    best = None
    for w in words:
        name, stretch, repeat_hint = match_word(w)
        if name:
            best = (name, stretch, repeat_hint)
            break
    if best is None:
        return "thud", {"stretch": 1.0}
    name, stretch, repeat_hint = best
    _, def_repeat, _ = recipes.RECIPES[name]
    params: dict = {"stretch": round(stretch, 3)}
    if def_repeat > 1:
        params["repeat"] = repeat_hint
    return name, params
