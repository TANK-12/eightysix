"""Acchan's own preferences, shared by the page, the terminal and Nyarch.

Stored as one small JSON file next to the conversations. Unknown or missing
keys fall back to DEFAULTS, so an old file never breaks a newer Acchan.
"""

from __future__ import annotations

import json

from . import conversation, voice

# speak: read replies aloud; voice: an id from acchan.voice.VOICES
# terminal_view: "headless" (Emerson's default, 2026-09-27) runs shells out of
# sight; "visible" also opens a window that follows each shell as it works.
# browser_view: "headless" sends page_* tools with no account to Acchan's own
# headless Firefox; "visible" sends them to your main Firefox.
DEFAULTS = {
    "persona": "plain",
    "thinking": False,
    "speak": False,
    "voice": "am_michael",
    "terminal_view": "headless",
    "browser_view": "headless",
    # tokens per reply; 0 = no cap, the model's own window is the limit
    # (Emerson, 2026-09-27: "reply cap limitless")
    "reply_limit": 0,
}


# Values a setting may take; anything else is refused (save) or dropped (load).
CHOICES = {
    "persona": ("plain", "cat"),
    "terminal_view": ("headless", "visible"),
    "browser_view": ("headless", "visible"),
}


def _ok(key: str, value) -> bool:
    default = DEFAULTS[key]
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, int):
        return type(value) is int and 0 <= value <= 1_000_000
    if key in CHOICES:
        return value in CHOICES[key]
    if key == "voice":
        return value in voice.VOICES
    return isinstance(value, str) and 0 < len(value) <= 80


def _path():
    return conversation.DATA / "settings.json"


def load() -> dict:
    try:
        stored = json.loads(_path().read_text())
    except (OSError, ValueError):
        stored = {}
    if not isinstance(stored, dict):
        stored = {}
    return {
        **DEFAULTS,
        **{k: v for k, v in stored.items() if k in DEFAULTS and _ok(k, v)},
    }


def save(changes: dict) -> dict:
    """Unknown keys are ignored; a known key with a wrong value raises
    ValueError, so a bad request never lands in the file."""
    for k, v in changes.items():
        if k in DEFAULTS and not _ok(k, v):
            raise ValueError(f"{k} cannot be {str(v)[:40]!r}")
    merged = {**load(), **{k: v for k, v in changes.items() if k in DEFAULTS}}
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, indent=1))
    return merged
