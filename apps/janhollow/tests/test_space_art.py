"""The space art pack: ships, planets, moons, stars and event props.

Mirrors test_art32.py's checks: the generator is deterministic, every
sprite is the declared size, the pack validates against the janhollow
palette, and no sprite uses a colour key that palette doesn't have.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from janhollow import content  # noqa: E402  (puts shared/ on sys.path)

import forge_art  # noqa: E402
import make_space_art  # noqa: E402

_ = content


def test_the_generator_is_deterministic():
    assert make_space_art.ship_shuttle(
        "ship_shuttle_64", 64
    ) == make_space_art.ship_shuttle("ship_shuttle_64", 64)
    assert make_space_art.planet_gas("planet_gas", 64) == make_space_art.planet_gas(
        "planet_gas", 64
    )
    assert make_space_art.build_sprites() == make_space_art.build_sprites()


def test_every_sprite_is_the_declared_size():
    sprites = make_space_art.build_sprites()
    for name, sprite in sprites.items():
        w, h = sprite["w"], sprite["h"]
        for frame in sprite["frames"]:
            rows = frame["rows"]
            assert len(rows) == h, f"{name}: expected {h} rows, got {len(rows)}"
            assert all(len(r) == w for r in rows), f"{name}: row width != {w}"


def test_expected_sprites_are_present():
    sprites = make_space_art.build_sprites()
    for base in make_space_art.SHIPS:
        for size in make_space_art.SHIP_SIZES:
            assert f"{base}_{size}" in sprites
    for name in make_space_art.PLANETS:
        assert name in sprites
    for name in make_space_art.MOONS:
        assert name in sprites
    for base in make_space_art.STARS:
        for size in make_space_art.STAR_SIZES:
            assert f"{base}_{size}" in sprites
    for name in make_space_art.STAR_POINTS:
        assert name in sprites
    for name in make_space_art.PROPS:
        assert name in sprites
    assert 20 <= len(sprites) <= 40


def test_the_pack_and_palette_on_disk_are_valid():
    library = forge_art.library()
    assert make_space_art.PALETTE_ID in library["palettes"]
    pack = library["packs"].get(make_space_art.PACK_ID)
    assert pack, "run tools/make_space_art.py"
    palette = library["palettes"][make_space_art.PALETTE_ID]
    assert forge_art.validate_pack(pack, palette) == []


def test_every_sprite_uses_colours_the_palette_has():
    library = forge_art.library()
    colours = set(library["palettes"][make_space_art.PALETTE_ID]["colors"]) | {
        forge_art.TRANSPARENT
    }
    pack = library["packs"][make_space_art.PACK_ID]
    for name, sprite in pack["sprites"].items():
        used = {ch for frame in sprite["frames"] for row in frame["rows"] for ch in row}
        assert (
            used <= colours
        ), f"{name} uses colours the palette does not have: {used - colours}"


def test_no_existing_palette_keys_were_touched():
    """This generator must not have edited the janhollow palette other tools
    depend on -- it only reads it."""
    library = forge_art.library()
    palette = library["palettes"][make_space_art.PALETTE_ID]
    for ramp in (
        make_space_art.HULL,
        make_space_art.FLOOR,
        make_space_art.TEAL,
        make_space_art.WARM,
        make_space_art.RUST,
    ):
        for key in ramp:
            assert key in palette["colors"]
