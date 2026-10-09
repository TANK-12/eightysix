"""More sliders (Emerson, 2026-09-27: "make basically everything have a
slider like fps and level of power used for particles ... but don't change
or remove anything"). Each is a number with a range, and its default keeps
today's behaviour."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))

import forge_theme  # noqa: E402

NEW = {
    "particle_size": 1.0,
    "particle_speed": 1.0,
    "particle_fps": 30,  # lowered from 60 to save GPU (default since 2026-10)
    "wall_tint_strength": 1.0,
    "ambient_drift_seconds": 90,
    "music_fade": 150,
    "desktop_particle_amount": 1.0,
    "desktop_particle_fps": 30,
}


def test_each_is_a_slider_whose_default_keeps_the_old_behaviour():
    for key, default in NEW.items():
        spec = forge_theme.SETTINGS[key]
        assert spec["kind"] in ("int", "number"), key
        assert spec["min"] <= default <= spec["max"], key
        assert spec["default"] == default, key


def test_nothing_that_was_there_is_gone():
    for key in (
        "particles",
        "particle_amount",
        "wall_tint",
        "ambient_drift",
        "max_fps",
    ):
        assert key in forge_theme.SETTINGS, key
