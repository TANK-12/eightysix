"""Particles that suit the wallpaper: "Match the wallpaper" and its settings.

WHY THIS EXISTS
    forge_theme.ambience() picks a particle kind for the wallpaper from the
    user's own pick for that file, then a word in its name, then its colours.
    A kind it can return that the hub does not draw would silently fall back
    to soft motes, so every kind is checked against the hub's KINDS too.

HOW TO RUN
    python3 tests/test_hub_ambience.py
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shared"))

import forge_theme  # noqa: E402


def hub_kinds():
    # the kinds moved to the shared script the hub and the desktop both load
    with open(
        os.path.join(ROOT, "shared", "forge_particles.js"), encoding="utf-8"
    ) as fh:
        hub = fh.read()
    block = hub[hub.index("KINDS: {") : hub.index("  init() {", hub.index("KINDS: {"))]
    return set(re.findall(r"^\s+(\w+): \{ count", block, re.M))


def test_every_setting_choice_is_drawn_by_the_hub():
    choices = set(forge_theme.SETTINGS["particles"]["choices"]) - {"off", "auto"}
    assert choices == hub_kinds(), (choices, hub_kinds())


def test_name_words_win_over_colours():
    assert forge_theme.ambience("sakura-path.jpg", ["#101010"], {}) == (
        "petals",
        "its name",
    )
    assert forge_theme.ambience("winter_lake.png", ["#ff00aa"], {}) == (
        "snow",
        "its name",
    )


def test_the_users_pick_wins_over_everything():
    assert forge_theme.ambience("sakura.jpg", [], {"sakura.jpg": "rain"})[0] == "rain"
    # a pick naming no real kind is ignored
    assert forge_theme.ambience("sakura.jpg", [], {"sakura.jpg": "lava"})[0] == "petals"


def test_colours():
    f = forge_theme.ambience_from_colours
    assert f(["#ffc6d9", "#f7a1bd", "#ffffff"]) == "petals"
    assert f(["#eef2f6", "#dde3ea", "#f8f8fa"]) == "snow"
    assert f(["#10183a", "#1a2450", "#0c1020"]) == "rain"
    assert f(["#2f6b3a", "#4a8a3c", "#9fc07a"]) == "fireflies"
    assert f([]) == "soft"
    for kind in (f(p) for p in (["#c08040"], ["#f0c070", "#fff0c0"], ["#808080"])):
        assert kind in hub_kinds()


def test_the_theme_carries_the_pick_and_the_new_settings():
    spec = forge_theme.SETTINGS
    assert spec["particles"]["default"] == "soft"  # nobody's current look changes
    assert spec["visualiser"]["default"] == "off"
    assert forge_theme._clean("particle_amount", 99) == 2.5
    assert forge_theme._clean("visualiser", "disco") == "off"


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                failed += 1
                print(f"FAIL {name}: {exc}")
    sys.exit(1 if failed else 0)


def test_the_most_named_kind_wins_not_the_first_listed():
    # S12 (2026-09-27): "make the match the wallpaper option a bit smarter".
    # One word for petals (japan) against three for leaves.
    assert forge_theme.ambience("japan-autumn-maple-leaves.jpg", [], {})[0] == "leaves"


def test_new_kinds_come_from_names():
    assert forge_theme.ambience("ocean-underwater.png", [], {})[0] == "bubbles"
    assert forge_theme.ambience("galaxy_space.jpg", [], {})[0] == "stars"


def test_new_kinds_come_from_colours():
    f = forge_theme.ambience_from_colours
    assert f(["#05060a", "#0a0c14", "#101218"]) == "stars"
    assert f(["#c2571a", "#d9822b", "#8f4a1c"]) == "leaves"
    assert f(["#1a8a9a", "#2aa8b0", "#0f6a7a"]) == "bubbles"


def test_new_kinds_are_matched_by_name():
    assert forge_theme.ambience("summer-festival-lantern.jpg", [], {})[0] == "lanterns"
    assert forge_theme.ambience("magical-girl-sparkle.png", [], {})[0] == "glitter"


def test_every_wallpaper_gets_particles_unless_picked_off():
    # Emerson: "make sure that none of the wallpapers have no particles"
    f = forge_theme.ambience_from_colours
    for pal in (
        ["#ffffff"] * 6,
        ["#000000"] * 6,
        ["#808080"],
        [],
        ["#ff0000", "#00ff00"],
    ):
        assert f(pal) in forge_theme.PARTICLE_LABELS and f(pal) not in ("off", "auto")
    # a wallpaper picked Off still has a matching kind worked out for later
    assert forge_theme.ambience("sakura.jpg", [], {"sakura.jpg": "off"})[0] == "petals"


def test_wallpaper_picks_are_saved_and_cleared(tmp_path, monkeypatch):
    monkeypatch.setattr(forge_theme, "AMBIENCE_FILE", tmp_path / "ambience.json")
    assert forge_theme.wallpaper_particle_picks() == {}
    forge_theme.set_wallpaper_particles("sea.jpg", "bubbles")
    forge_theme.set_wallpaper_particles("moon.png", "off")
    assert forge_theme.wallpaper_particle_picks() == {
        "sea.jpg": "bubbles",
        "moon.png": "off",
    }
    forge_theme.set_wallpaper_particles("sea.jpg", "")
    assert forge_theme.wallpaper_particle_picks() == {"moon.png": "off"}
    try:
        forge_theme.set_wallpaper_particles("sea.jpg", "lava")
        raise AssertionError("an unknown kind was saved")
    except ValueError:
        pass


def test_wall_light():
    assert forge_theme.wall_light(["#ffffff", "#ffffff"]) == 1.0
    assert forge_theme.wall_light(["#000000"]) == 0.0
    assert forge_theme.wall_light([]) == 0.0


def test_the_command_line_reads_and_changes_a_group(tmp_path, monkeypatch, capsys):
    # the GNOME extension's settings page is built from these rows
    monkeypatch.setattr(forge_theme, "CONFIG", tmp_path / "settings.json")
    monkeypatch.setattr(forge_theme, "apply", lambda hub: {})
    rows = forge_theme.settings_rows([forge_theme.DESKTOP_PARTICLES])
    keys = [r["key"] for r in rows]
    assert "desktop_particle_kind" in keys and "desktop_particle_fps" in keys
    kind = next(r for r in rows if r["key"] == "desktop_particle_kind")
    assert kind["value"] == "same" and "glitter" in kind["choices"]
    assert forge_theme.main(["--set", "desktop_particle_fps=45"]) == 0
    assert forge_theme.load()["desktop_particle_fps"] == 45
    assert forge_theme.main(["--set", "desktop_particle_kind=lanterns"]) == 0
    assert forge_theme.load()["desktop_particle_kind"] == "lanterns"
    capsys.readouterr()
    forge_theme.main(["--rows", forge_theme.DESKTOP_PARTICLES])
    out = json.loads(capsys.readouterr().out)
    assert {r["key"]: r["value"] for r in out}["desktop_particle_fps"] == 45
