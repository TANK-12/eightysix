"""The hub's Now playing popup, the Python half (S7 A9/A27/A30, finished by S10).

The bar's music button controls whatever plays in Forge and on the desktop,
and the background music may go past 100% and is evened out (A27: "so quiet
even at max, but when I turn it up it makes all my other stuff too loud").
The page itself is checked by tests/browser/hub_media_harness.js.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "shared"))

import forge  # noqa: E402
import forge_theme  # noqa: E402


def test_music_volume_goes_past_100():
    spec = forge_theme.SETTINGS["music_volume"]
    assert spec["max"] == 200 and spec["default"] == 35


def test_levelling_and_stepping_aside_are_settings_that_default_on():
    for key in ("music_level", "music_duck"):
        spec = forge_theme.SETTINGS[key]
        assert spec["kind"] == "bool" and spec["default"] is True, key


def test_music_fade_is_a_fast_ms_slider():
    # Emerson 2026-09-27: pausing and stepping aside took too long (a fixed
    # 1.5 s fade); now a slider, short by default
    spec = forge_theme.SETTINGS["music_fade"]
    assert spec["kind"] == "int" and spec["unit"] == "ms"
    assert spec["min"] == 0 and spec["max"] >= 1500
    assert 0 < spec["default"] <= 200


def test_the_popup_may_save_the_music_volume_and_nothing_else_new():
    path = Path(tempfile.mkdtemp()) / "settings.json"
    picked = forge.save_hub_settings(
        {"music_volume": 150, "music_folder": "/etc", "wallpaper": "/etc/passwd"}, path
    )
    assert set(picked) == {"music_volume"}
    stored = json.loads(path.read_text())
    assert stored["music_volume"] == 150
    assert forge_theme.load(path)["music_folder"] == "~/Music"


def test_music_volume_is_clamped():
    path = Path(tempfile.mkdtemp()) / "settings.json"
    forge.save_hub_settings({"music_volume": 900}, path)
    assert json.loads(path.read_text())["music_volume"] == 200


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except (AssertionError, AttributeError, TypeError, KeyError) as exc:
                failed += 1
                print(f"FAIL {name}: {exc!r}")
    sys.exit(1 if failed else 0)
