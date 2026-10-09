"""User settings, one JSON file. Numeric settings carry their own range so the
page can draw a slider plus number field for each without a second list."""

from __future__ import annotations

import json
import os
from pathlib import Path

SETTINGS_FILE = Path(
    os.environ.get("COMIX_SETTINGS", Path.home() / ".config/forge-comix/settings.json")
)

# name -> (default, min, max, label)
NUMBERS = {
    "chapters_at_once": (1, 1, 2, "Chapters downloaded at once"),
    "pause_seconds": (5, 0, 120, "Pause between chapters (seconds)"),
    "page_passes": (4, 1, 10, "Passes over a chapter's missing pages"),
    "chapter_attempts": (6, 1, 20, "Tries per chapter before it is marked failed"),
}
DEFAULTS: dict = {
    "download_dir": str(Path.home() / "ComixData"),
    "library_url": "",
    "advanced_mode": False,
    **{k: v[0] for k, v in NUMBERS.items()},
}


def load() -> dict:
    data = dict(DEFAULTS)
    try:
        data.update(json.loads(SETTINGS_FILE.read_text()))
    except (OSError, ValueError):
        pass
    return data


TEXT_MAX = 4096  # a folder path or a link; anything longer is a mistake


def save(values: dict) -> dict:
    """Store the known keys; a number that is not a number raises ValueError
    before anything is written."""
    data = load()
    for key, value in values.items():
        if key not in DEFAULTS:
            continue
        if key in NUMBERS:
            _, lo, hi, label = NUMBERS[key]
            try:
                value = max(lo, min(hi, int(float(value))))
            except (TypeError, ValueError, OverflowError):
                raise ValueError(f"{label} must be a number") from None
        elif key == "advanced_mode":
            value = bool(value)
        elif not isinstance(value, str) or "\0" in value or len(value) > TEXT_MAX:
            raise ValueError(
                f"{key.replace('_', ' ')} must be plain text under {TEXT_MAX} characters"
            )
        else:
            value = value.strip()
        data[key] = value
    if not data["download_dir"]:
        data["download_dir"] = DEFAULTS["download_dir"]
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(data, indent=2))
    return data


def describe() -> list[dict]:
    return [
        {"key": k, "default": d, "min": lo, "max": hi, "label": label}
        for k, (d, lo, hi, label) in NUMBERS.items()
    ]
