"""The 32-pixel art: the upscaler and the autotile set.

The deck art is generated rather than drawn, so the things worth pinning are
that the generator is deterministic, that the autotile set is complete (a
missing variant is an invisible hole in a wall), and that EPX does what it
claims -- rounds a diagonal rather than doubling a block.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from janhollow import content  # noqa: E402  (puts shared/ on sys.path)

import forge_art  # noqa: E402
import make_art32  # noqa: E402

_ = content


def test_epx_doubles_a_flat_block_exactly():
    rows = ["aa", "aa"]
    assert make_art32.epx(rows) == ["aaaa", "aaaa", "aaaa", "aaaa"]


def test_epx_rounds_a_diagonal_instead_of_squaring_it():
    """The whole reason for using EPX over nearest-neighbour doubling."""
    rows = [
        "b...",
        ".b..",
        "..b.",
        "...b",
    ]
    out = make_art32.epx(rows)
    assert len(out) == 8 and all(len(r) == 8 for r in out)
    # A plain 2x doubling would leave the corner between two steps empty; EPX
    # fills it, which is what makes the edge read as a line.
    plain = [ch for row in rows for ch in row for _ in (0, 1)]
    assert "".join(out) != "".join(plain * 2)
    assert out[1].count("b") >= 1


def test_epx_keeps_transparency_transparent():
    rows = ["..", ".."]
    assert set("".join(make_art32.epx(rows))) == {"."}


def test_every_autotile_variant_exists_and_is_the_right_size():
    for mask in range(16):
        grid = make_art32.wall_tile(mask)
        assert len(grid) == make_art32.TILE
        assert all(len(row) == make_art32.TILE for row in grid)


def test_a_wall_lights_the_sides_that_face_a_room():
    """Mask bits mean 'another wall is on that side', so an unset bit is an
    exposed face and must get its lit lip."""
    alone = make_art32.wall_tile(0)
    assert alone[0][5] == "C", "an exposed north face needs its bright lip"
    boxed = make_art32.wall_tile(15)
    assert boxed[0][5] != "C", "a wall with a wall above it must not be lit there"


def test_the_generator_is_deterministic():
    assert make_art32.floor_plate("floor_plate") == make_art32.floor_plate(
        "floor_plate"
    )
    assert make_art32.wall_tile(6) == make_art32.wall_tile(6)


def test_the_palette_and_packs_on_disk_are_valid():
    library = forge_art.library()
    assert make_art32.PALETTE_ID in library["palettes"]
    deck = library["packs"].get(make_art32.DECK_PACK)
    crew = library["packs"].get(make_art32.CREW_PACK)
    assert deck and crew, "run tools/make_art32.py"
    assert deck["tile"] == 32
    assert (
        forge_art.validate_pack(deck, library["palettes"][make_art32.PALETTE_ID]) == []
    )
    for mask in range(16):
        assert f"wall_{mask}" in deck["sprites"]
    for name in ("floor_plate", "floor_grate", "floor_garden", "door", "lift"):
        assert name in deck["sprites"]
    # The crew came through the upscaler at twice their original size.
    assert crew["sprites"]["person1_idle"]["w"] == 32
    assert crew["sprites"]["person1_idle"]["h"] == 48


def test_every_tile_in_the_deck_pack_uses_colours_the_palette_has():
    library = forge_art.library()
    colours = set(library["palettes"][make_art32.PALETTE_ID]["colors"]) | {
        forge_art.TRANSPARENT
    }
    for name, sprite in library["packs"][make_art32.DECK_PACK]["sprites"].items():
        used = {ch for frame in sprite["frames"] for row in frame["rows"] for ch in row}
        assert used <= colours, f"{name} uses colours the palette does not have"
