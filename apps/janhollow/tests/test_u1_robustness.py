"""Bad input that used to reach the world (U1 sweep, 2026-10-08): a NaN walking
direction, non-finite settings, and save slot names too long for a file."""

import json
import math
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from janhollow import content, saves, sim, station  # noqa: E402


@pytest.fixture(scope="module")
def store():
    return content.store()


@pytest.fixture(scope="module")
def built(store):
    return station.build(store)


def make_world(built, store):
    crew = list(store["types"]["npcs"].values())
    world = sim.World(built, crew, settings={}, content=store)
    world.saw_page(True)
    return world


@pytest.mark.parametrize(
    "dx,dy",
    [(math.nan, 0.0), (0.0, math.nan), (math.inf, 0.0), (-math.inf, math.inf)],
)
def test_a_direction_that_is_not_a_number_counts_as_letting_go(built, store, dx, dy):
    world = make_world(built, store)
    world.player.join()
    x, y = world.player.x, world.player.y
    world.player.hold(dx, dy)
    for _ in range(10):
        world.player.step(0.1)
    assert world.player.input == (0.0, 0.0)
    assert (world.player.x, world.player.y) == (x, y)
    # the snapshot still serialises the way the API sends it
    json.dumps(world.snapshot(), allow_nan=False)


def test_a_finite_direction_still_walks(built, store):
    world = make_world(built, store)
    world.player.join()
    before = world.player.x
    world.player.hold(1.0, 0.0)
    for _ in range(10):
        world.player.step(0.05)
    assert world.player.x > before


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, "nan", "inf"])
def test_non_finite_settings_keep_the_last_good_value(bad):
    current = sim.clamp_settings({"day_minutes": 90, "start_hour": 6})
    after = sim.clamp_settings({"day_minutes": bad, "start_hour": bad}, base=current)
    assert after["day_minutes"] == 90.0
    assert after["start_hour"] == 6.0


def test_a_very_long_slot_name_still_saves(tmp_path, monkeypatch):
    monkeypatch.setattr(saves, "saves_dir", lambda: str(tmp_path))
    slot = "a" * 500
    path = saves.write(slot, {"day": 3})
    assert len(os.path.basename(path)) == saves.SLOT_MAX + len(".json")
    state = saves.read(slot)
    assert state is not None and state["day"] == 3
    assert saves.delete(slot)


def test_a_slot_name_cannot_leave_the_saves_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(saves, "saves_dir", lambda: str(tmp_path))
    for slot in ("../../etc/passwd", "..", "/", "é😀"):
        assert os.path.dirname(saves.path_for(slot)) == str(tmp_path)


def test_a_bad_value_in_an_update_keeps_the_current_setting(built, store):
    world = make_world(built, store)
    world.update_settings({"day_minutes": 90, "chatter": "quiet"})
    after = world.update_settings(
        {"day_minutes": "abc", "chatter": 5, "away_mode": "bogus", "zzz": 1}
    )
    assert after["day_minutes"] == 90.0
    assert after["chatter"] == "quiet"
    assert after["away_mode"] == sim.DEFAULT_SETTINGS["away_mode"]
    assert "zzz" not in after


@pytest.mark.parametrize(
    "values",
    [
        {"away_mode": {"a": 1}},
        {"chatter": ["lively"]},
        {"day_minutes": 10**400},
        {"start_hour": -(10**400)},
        {"day_minutes": True},
    ],
)
def test_wrong_types_and_huge_numbers_keep_the_current_setting(values):
    current = sim.clamp_settings({"day_minutes": 90, "chatter": "quiet"})
    assert sim.clamp_settings(values, base=current) == current
    assert sim.clamp_settings(values) == sim.DEFAULT_SETTINGS


def test_a_long_slot_name_in_four_byte_characters_still_saves(tmp_path, monkeypatch):
    monkeypatch.setattr(saves, "saves_dir", lambda: str(tmp_path))
    slot = "\U00020000" * 63
    path = saves.write(slot, {"day": 4})
    assert len(os.path.basename(path).encode("utf-8")) <= 255
    state = saves.read(slot)
    assert state is not None and state["day"] == 4
