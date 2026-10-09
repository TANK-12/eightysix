"""Turning a model's shape list into pixels, tested without a model.

Every malformed reply in here is one these models actually sent on 2026-09-16:
hex codes in the colour field, fenced code blocks, a legend where a palette was
asked for, and -- the reason the whole shape approach exists -- a grid of
sixteen transparent rows when asked to draw directly.
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import janart  # noqa: E402

TOOLBOX = """{"palette": {"k": "#8B0000", "m": "#D2691E", "n": "#F4A460"},
 "parts": [{"shape":"rect","x":2,"y":7,"w":12,"h":6,"color":"k","fill":true},
           {"shape":"rect","x":2,"y":7,"w":12,"h":6,"color":"m","fill":false},
           {"shape":"line","x":5,"y":6,"x2":10,"y2":6,"color":"n"},
           {"shape":"pixel","x":8,"y":10,"color":"n"}]}"""


def test_a_well_formed_reply_becomes_a_picture():
    rows, palette, problems = janart.make_sprite(TOOLBOX, 16, 16)
    assert problems == []
    assert len(rows) == 16 and all(len(r) == 16 for r in rows)
    assert set(palette) == {"k", "m", "n"}
    # The body is filled, the outline is a different colour, the handle is above it.
    assert rows[9][5] == "k"
    assert rows[7][2] == "m"
    assert "n" in rows[6]


def test_a_fenced_reply_is_unwrapped():
    fenced = "```json\n" + TOOLBOX + "\n```"
    rows, _, problems = janart.make_sprite(fenced, 16, 16)
    assert problems == []
    assert any("k" in row for row in rows)


def test_hex_in_the_colour_field_is_repaired():
    """The 4B put hex codes straight into `color` instead of its own keys."""
    raw = TOOLBOX.replace('"color":"k"', '"color":"#8B0000"')
    rows, palette, problems = janart.make_sprite(raw, 16, 16)
    assert problems == []
    assert "#8b0000" in palette.values()
    assert any(row.count("k") > 4 for row in rows)


def test_an_unknown_colour_key_is_skipped_not_drawn():
    raw = TOOLBOX.replace('"color":"n"', '"color":"zzz"')
    rows, palette, _ = janart.make_sprite(raw, 16, 16)
    assert "z" not in "".join(rows)


def test_coordinates_off_the_canvas_do_not_escape():
    raw = """{"palette": {"a": "#ffffff", "b": "#000000"},
     "parts": [{"shape":"rect","x":-5,"y":-5,"w":40,"h":6,"color":"a"},
               {"shape":"rect","x":2,"y":2,"w":4,"h":4,"color":"b"}]}"""
    rows, _, _ = janart.make_sprite(raw, 16, 16)
    assert len(rows) == 16 and all(len(r) == 16 for r in rows)


@pytest.mark.parametrize(
    "raw,why",
    [
        ("no json here at all", "no JSON object"),
        ('{"palette": {"a": "#fff000"}}', "no parts"),
        ('{"palette": {}, "parts": []}', "parts could be drawn"),
    ],
)
def test_a_reply_that_is_not_art_is_refused(raw, why):
    with pytest.raises(janart.ArtError) as caught:
        janart.make_sprite(raw, 16, 16)
    assert why in str(caught.value)


def test_an_empty_drawing_is_judged_not_shown():
    """Asked for a grid the 4B returned sixteen transparent rows; the guard has
    to catch the same thing arriving as shapes."""
    raw = """{"palette": {"a": "#ffffff", "b": "#101010"},
     "parts": [{"shape":"pixel","x":1,"y":1,"color":"a"},
               {"shape":"pixel","x":2,"y":2,"color":"b"}]}"""
    rows, palette, problems = janart.make_sprite(raw, 16, 16)
    assert any("almost nothing" in p for p in problems)


def test_one_flat_colour_is_judged():
    raw = """{"palette": {"a": "#ffffff"},
     "parts": [{"shape":"rect","x":0,"y":0,"w":16,"h":16,"color":"a"},
               {"shape":"rect","x":0,"y":0,"w":16,"h":16,"color":"a"}]}"""
    rows, palette, problems = janart.make_sprite(raw, 16, 16)
    assert any("single flat colour" in p for p in problems)
    assert any("whole canvas" in p for p in problems)


# --- floor plans ------------------------------------------------------------

CABIN = """{"legend": {"a": "floor_metal", "b": "wall_metal", "c": "not_a_real_tile"},
 "parts": [{"shape":"rect","x":0,"y":0,"w":10,"h":7,"color":"a","fill":true},
           {"shape":"rect","x":0,"y":0,"w":10,"h":7,"color":"b","fill":false},
           {"shape":"pixel","x":5,"y":6,"color":"c"}]}"""


def test_a_floor_plan_keeps_only_tiles_that_exist():
    rows, legend, problems = janart.make_structure(
        CABIN, 10, 7, allowed={"floor_metal", "wall_metal"}
    )
    assert legend == {"a": "floor_metal", "b": "wall_metal"}
    assert "c" not in "".join(
        rows
    ), "a tile the library does not have must not be drawn"
    assert problems == []


def test_a_full_floor_plan_is_not_treated_as_a_runaway_rectangle():
    """A room covers every tile it occupies. That rule is for sprites only."""
    rows, _, problems = janart.make_structure(
        CABIN, 10, 7, allowed={"floor_metal", "wall_metal"}
    )
    assert not any("whole canvas" in p for p in problems)
    assert rows[0] == "b" * 10
    assert rows[3] == "b" + "a" * 8 + "b"


def test_a_plan_of_tiles_nobody_has_says_so():
    raw = CABIN.replace("floor_metal", "nope_a").replace("wall_metal", "nope_b")
    rows, legend, problems = janart.make_structure(raw, 10, 7, allowed={"floor_metal"})
    assert legend == {}
    assert any("none of its tiles exist" in p for p in problems)


def test_the_tile_list_offered_to_the_model_comes_from_the_library():
    tiles = janart.tile_choices()
    assert tiles, "the prompt needs real tile ids to offer"
    assert all(isinstance(t, str) for t in tiles)
    assert "floor_metal" in tiles


def test_the_prompts_carry_the_size_and_the_tiles():
    assert "24 wide and 12 tall" in janart.sprite_prompt(24, 12).replace(
        "The canvas is ", ""
    ).replace("canvas is ", "")
    plan = janart.structure_prompt(9, 6, ["floor_metal", "wall_metal"])
    assert "9 tiles wide" in plan and "6 tiles tall" in plan
    assert "floor_metal, wall_metal" in plan


# --- ships --------------------------------------------------------------
# A ship is a sprite with a different prompt: same rasteriser, same guard.

SHIP = """{"palette": {"a": "#6b7280", "b": "#334155", "c": "#f59e0b"},
 "parts": [{"shape":"rect","x":10,"y":2,"w":12,"h":28,"color":"a","fill":true},
           {"shape":"rect","x":8,"y":24,"w":4,"h":6,"color":"b","fill":true},
           {"shape":"rect","x":20,"y":24,"w":4,"h":6,"color":"b","fill":true},
           {"shape":"rect","x":13,"y":4,"w":6,"h":5,"color":"c","fill":true},
           {"shape":"rect","x":11,"y":14,"w":10,"h":8,"color":"b","fill":false},
           {"shape":"pixel","x":16,"y":10,"color":"c"}]}"""


def test_a_ship_is_drawn_like_a_sprite():
    rows, palette, problems = janart.make_ship(SHIP, 32, 32)
    assert problems == []
    assert len(rows) == 32 and all(len(r) == 32 for r in rows)
    assert set(palette) == {"a", "b", "c"}


def test_the_ship_prompt_carries_the_size_and_mentions_the_parts():
    prompt = janart.ship_prompt(48, 64)
    assert "48 wide and 64 tall" in prompt
    for part in ("hull", "engines", "bridge", "cargo", "airlock"):
        assert part in prompt


# --- worlds ---------------------------------------------------------------
# Not pixels: six fields matching janhollow/content.py's worlds type.

WORLD = """{"label": "Kessleron", "kind": "planet", "distance": "far",
 "colour": "#3a5f7a", "description": "a rust-banded gas giant with two rings.",
 "tags": ["gas giant", "uninhabited"]}"""


def test_a_well_formed_world_reply_is_accepted():
    entry, problems = janart.make_world(WORLD)
    assert problems == []
    assert entry == {
        "label": "Kessleron",
        "kind": "planet",
        "distance": "far",
        "colour": "#3a5f7a",
        "description": "a rust-banded gas giant with two rings.",
        "tags": ["gas giant", "uninhabited"],
    }


def test_a_fenced_world_reply_is_unwrapped():
    fenced = "```json\n" + WORLD + "\n```"
    entry, problems = janart.make_world(fenced)
    assert problems == []
    assert entry["label"] == "Kessleron"


def test_short_and_uppercase_hex_is_repaired_for_a_world():
    raw = WORLD.replace('"#3a5f7a"', '"#ABC"')
    entry, problems = janart.make_world(raw)
    assert problems == []
    assert entry["colour"] == "#aabbcc"


def test_a_world_kind_that_is_not_allowed_is_refused():
    raw = WORLD.replace('"kind": "planet"', '"kind": "spaceship"')
    entry, problems = janart.make_world(raw)
    assert entry["kind"] == ""
    assert any("kind" in p for p in problems)


def test_a_world_colour_in_the_wrong_place_is_refused():
    """Hex belongs in `colour`; the model sometimes puts a hex string, or
    nothing at all, where a word was asked for."""
    raw = WORLD.replace('"distance": "far"', '"distance": "#3a5f7a"')
    entry, problems = janart.make_world(raw)
    assert entry["distance"] == ""
    assert any("distance" in p for p in problems)


def test_a_malformed_world_colour_is_refused():
    raw = WORLD.replace('"#3a5f7a"', '"not-a-colour"')
    entry, problems = janart.make_world(raw)
    assert entry["colour"] == ""
    assert any("colour" in p for p in problems)


def test_a_world_missing_fields_reports_every_one():
    entry, problems = janart.make_world('{"label": "Empty Hulk"}')
    assert entry["label"] == "Empty Hulk"
    assert len(problems) == 4  # kind, distance, colour, description
    assert entry["kind"] == "" and entry["colour"] == "" and entry["tags"] == []


def test_a_world_reply_that_is_not_json_raises():
    with pytest.raises(janart.ArtError) as caught:
        janart.make_world("just some words, no object here")
    assert "no JSON object" in str(caught.value)


def test_world_tags_that_are_not_a_list_are_refused():
    raw = WORLD.replace('"tags": ["gas giant", "uninhabited"]', '"tags": "gas giant"')
    entry, problems = janart.make_world(raw)
    assert entry["tags"] == []
    assert any("tags" in p for p in problems)
