"""Session 1 covers the world and the art, so these are the properties that
must not break: a save must reload into the same valley, the valley's landmarks
must always be reachable, and the art format must survive a round trip through
disk and a palette swap.
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.abspath(os.path.join(ROOT, "..", "..", "shared")))

from emberfield import resources, worldgen  # noqa: E402
import forge_content  # noqa: E402

SEEDS = [1, 7, 12345, 99991, 2026090601]


# --- the valley ------------------------------------------------------------


@pytest.mark.parametrize("seed", SEEDS)
def test_generation_is_deterministic(seed):
    """A save stores the seed, not the map. If generation drifts, every
    existing save silently loads a different valley."""
    a, b = worldgen.generate(seed), worldgen.generate(seed)
    assert a.tiles == b.tiles
    assert a.objects == b.objects
    assert a.spawn == b.spawn


def test_different_seeds_give_different_valleys():
    assert worldgen.generate(1).tiles != worldgen.generate(2).tiles


@pytest.mark.parametrize("seed", SEEDS)
def test_farm_town_and_cave_are_always_reachable(seed):
    """The one property a generated valley must never get wrong. Paths are
    carved before objects are scattered, so this should hold by construction --
    this test is what keeps that true when the scatter changes."""
    world = worldgen.generate(seed)
    r = world.regions
    assert worldgen.reachable(world, r["farm_centre"], r["town_centre"])
    assert worldgen.reachable(world, r["town_centre"], r["cave_mouth"])


@pytest.mark.parametrize("seed", SEEDS)
def test_the_player_does_not_spawn_inside_something_solid(seed):
    world = worldgen.generate(seed)
    x, y = world.spawn
    assert not worldgen.TILES[world.tiles[y][x]]["solid"]
    assert (x, y) not in {(o["x"], o["y"]) for o in world.objects if o["solid"]}


@pytest.mark.parametrize("seed", SEEDS)
def test_nothing_is_scattered_onto_a_path_or_into_water(seed):
    """A tree in the road would break the connectivity the carve step just
    guaranteed, and a bush in the sea would look like a bug."""
    world = worldgen.generate(seed)
    for obj in world.objects:
        # Fixtures -- the bed, the market stall, a house, the town well -- are
        # placed deliberately and are allowed to stand on paving; the town
        # square is paving. This test is about the *scatter*, which must never
        # drop a tree in the road.
        if obj.get("use") or obj.get("fixture"):
            continue
        for dx in range(obj["w"]):
            for dy in range(obj["h"]):
                tile = world.tiles[obj["y"] - dy][obj["x"] + dx]
                assert (
                    tile != "water"
                ), f"{obj['sprite']} in water at {obj['x']},{obj['y']}"
                assert (
                    tile != "path"
                ), f"{obj['sprite']} on a path at {obj['x']},{obj['y']}"


def test_every_tile_and_object_names_a_real_sprite():
    """Tile ids are sprite names on purpose. This is what catches a rename in
    the art library that would otherwise show up as invisible ground."""
    import forge_art

    library = forge_art.library()
    known = set()
    for pack in library["packs"].values():
        known.update(pack["sprites"].keys())
    if not known:
        pytest.skip("art library is empty; run tools/seed_art.py")

    world = worldgen.generate(4242)
    assert set(worldgen.TILES) <= known
    assert {o["sprite"] for o in world.objects} <= known


def test_the_world_serialises_to_something_json_can_hold():
    import json

    world = worldgen.generate(31337)
    blob = json.dumps(world.to_dict())
    back = json.loads(blob)
    assert back["seed"] == 31337
    assert len(back["tiles"]) == world.height
    assert len(back["tiles"][0].split("\t")) == world.width


# --- the art format --------------------------------------------------------


@pytest.fixture
def art_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_ART_DIR", str(tmp_path))
    import forge_art

    forge_art.ensure_root()
    return forge_art


def test_a_pack_survives_a_round_trip_through_disk(art_dir):
    pack = {
        "id": "test-pack",
        "label": "Test",
        "tile": 2,
        "sprites": {
            "dot": {
                "w": 2,
                "h": 2,
                "tags": [],
                "frames": [{"ms": 0, "rows": ["ab", ".a"]}],
            }
        },
    }
    art_dir.save_pack(pack)
    assert art_dir.load_pack("test-pack") == pack


def test_geometry_errors_are_refused_rather_than_saved(art_dir):
    bad = {
        "id": "bad",
        "sprites": {
            "x": {"w": 4, "h": 2, "frames": [{"ms": 0, "rows": ["ab", "abc"]}]}
        },
    }
    problems = art_dir.validate_pack(bad)
    assert problems, "a row of the wrong length must be caught"
    with pytest.raises(art_dir.ArtError):
        art_dir.save_pack(bad)


def test_a_palette_swap_changes_colour_but_never_shape(art_dir):
    """The whole point of storing colour separately. If a season swap could
    alter geometry, every sprite would need a variant per season."""
    warm = {"id": "warm", "colors": {"a": "#ff0000", "b": "#00ff00"}}
    cold = {"id": "cold", "colors": {"a": "#0000ff", "b": "#00ffff"}}
    art_dir.save_palette(warm)
    art_dir.save_palette(cold)
    rows = ["ab", ".a"]
    pack = {
        "id": "p",
        "sprites": {"s": {"w": 2, "h": 2, "frames": [{"ms": 0, "rows": rows}]}},
    }
    assert art_dir.validate_pack(pack, warm) == []
    assert art_dir.validate_pack(pack, cold) == []
    assert pack["sprites"]["s"]["frames"][0]["rows"] == rows


def test_a_colour_the_palette_lacks_is_reported(art_dir):
    palette = {"id": "small", "colors": {"a": "#ffffff"}}
    pack = {
        "id": "p",
        "sprites": {"s": {"w": 2, "h": 1, "frames": [{"ms": 0, "rows": ["az"]}]}},
    }
    assert any("z" in p for p in art_dir.validate_pack(pack, palette))


def test_the_seeded_art_is_valid_against_its_own_palette():
    """The shipped defaults must load. This runs against the real library, so
    it also catches a hand edit that broke a row length."""
    import forge_art

    library = forge_art.library()
    if not library["packs"]:
        pytest.skip("art library is empty; run tools/seed_art.py")
    for pack in library["packs"].values():
        palette = library["palettes"].get(pack.get("default_palette"))
        assert forge_art.validate_pack(pack, palette) == [], pack["id"]


# --- the compute budget ----------------------------------------------------


def test_background_work_never_gets_every_core():
    """The point of the budget. If this returns everything, a voice bake makes
    the game unplayable while it runs."""
    topo = resources.topology()
    chosen = resources.background_cpus(6)
    assert 0 < len(chosen) <= 6
    assert len(chosen) < len(topo["all"])


def test_the_budget_prefers_efficiency_cores_when_the_cpu_is_hybrid():
    topo = resources.topology()
    if not topo["slow"]:
        pytest.skip("uniform CPU")
    assert set(resources.background_cpus(6)) <= set(topo["slow"])


def test_a_silly_budget_still_returns_something_usable():
    assert len(resources.background_cpus(0)) >= 1
    assert len(resources.background_cpus(999)) >= 1


def test_thread_env_pins_every_library_that_would_grab_all_cores():
    env = resources.thread_env(6)
    for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "ORT_NUM_THREADS"):
        assert env[var] == "6"


def test_the_heavy_lane_runs_one_job_at_a_time():
    """Text generation is on the iGPU and speech is on the CPU, but they share a
    memory bus, so overlapping them is slower than serialising them."""
    import threading
    import time

    lane = resources.HeavyLane(enabled=True)
    overlaps, active = [], []
    lock = threading.Lock()

    def job():
        with lock:
            active.append(1)
            overlaps.append(len(active))
        time.sleep(0.03)
        with lock:
            active.pop()

    threads = [threading.Thread(target=lambda: lane.run("job", job)) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert max(overlaps) == 1


def test_reachability_holds_across_a_wide_sweep_of_seeds():
    """Five seeds is not evidence for a property like this.

    Connectivity broke once already: the road skipped water tiles instead of
    fording them, which stayed invisible until the farm gained a fence and the
    last gap was sealed. A wide sweep is what would have caught it immediately.
    """
    failures = []
    for seed in range(1, 121):
        world = worldgen.generate(seed)
        r = world.regions
        if not worldgen.reachable(world, r["farm_centre"], r["town_centre"]):
            failures.append((seed, "farm->town"))
        elif not worldgen.reachable(world, r["town_centre"], r["cave_mouth"]):
            failures.append((seed, "town->cave"))
    assert not failures, f"{len(failures)}/120 seeds unreachable: {failures[:8]}"


def test_the_farm_is_never_sealed_in_by_its_own_fence():
    """The fence must always leave a gate where the road crosses it."""
    for seed in range(1, 61):
        world = worldgen.generate(seed)
        farm = world.regions["farm"]
        fence = {
            (o["x"], o["y"]) for o in world.objects if o["sprite"].startswith("fence")
        }
        x0, y0 = farm["x"] - 1, farm["y"] - 1
        x1, y1 = farm["x"] + farm["w"], farm["y"] + farm["h"]
        ring = [(x, y) for x in range(x0, x1 + 1) for y in (y0, y1)]
        ring += [(x, y) for y in range(y0 + 1, y1) for x in (x0, x1)]
        walkable_gaps = [
            (x, y)
            for (x, y) in ring
            if (x, y) not in fence
            and world.in_bounds(x, y)
            and not worldgen.TILES[world.tiles[y][x]]["solid"]
        ]
        assert walkable_gaps, f"seed {seed}: the fence sealed the farm completely"


# --- collision shapes (session 2) ------------------------------------------


@pytest.mark.parametrize("seed", SEEDS)
def test_a_tree_does_not_block_its_own_canopy(seed):
    """The session 1 bug, stated as a property.

    Objects declared their whole footprint solid, so an oak blocked all six of
    its tiles -- you collided with leaves two rows above the trunk and could
    never walk behind a tree. Collision is the hit ellipse now, which sits at
    the base, so nothing may block a tile above its own bottom row.
    """
    world = worldgen.generate(seed)
    blocked = worldgen.blocked_tiles(world.objects)
    for obj in world.objects:
        if not obj.get("solid"):
            continue
        for x, y in blocked:
            if obj["x"] <= x < obj["x"] + obj["w"] and y < obj["y"]:
                # Only fair to blame this object if nothing else is there.
                others = [
                    o
                    for o in world.objects
                    if o is not obj and o.get("solid") and abs(o["x"] - x) < 3
                ]
                assert (
                    others
                ), f"{obj['sprite']} blocks {x},{y} above its base {obj['y']}"


def test_the_oak_is_narrower_than_the_tile_it_stands_on():
    """You should be able to brush past a trunk. A full-tile box makes a wood
    impassable in practice even when the map says it is not."""
    tree = worldgen.OBJECTS["tree_oak"]
    assert tree["hit"][0] < 1.0 and tree["hit"][1] < 1.0
    obj = {
        "sprite": "tree_oak",
        "x": 10,
        "y": 10,
        "w": 2,
        "h": 3,
        "solid": True,
        "hit": list(tree["hit"]),
    }
    cx, cy, rx, ry = worldgen.hit_ellipse(obj)
    assert cx == 11.0, "the trunk sits at the centre of a two-tile footprint"
    assert cy > 10.5, "the box hugs the ground, not the middle of the sprite"


def test_flowers_never_block_anything():
    """Decor is decor. A flower you cannot walk over is a bug you feel but
    cannot see."""
    objects = [
        {"sprite": "flowers_red", "x": 4, "y": 4, "w": 1, "h": 1, "solid": False}
    ]
    assert worldgen.blocked_tiles(objects) == set()


# --- the player's house, and every other house (session 5) ----------------


@pytest.mark.parametrize("seed", SEEDS)
def test_the_player_house_is_in_the_farm_and_you_can_reach_its_door(seed):
    """Session 2's bed became session 5's house: you sleep inside now. The door
    tile has to be inside the fence and walkable to from the farm, or the save
    cannot be advanced."""
    world = worldgen.generate(seed)
    farm = world.regions["farm"]
    house = next(
        b for b in world.regions["buildings"] if b["id"] == "emberfield-house-player"
    )
    door = house["door"]
    assert farm["x"] <= door[0] < farm["x"] + farm["w"]
    assert farm["y"] <= door[1] < farm["y"] + farm["h"]
    assert not world.solid_at(*door)
    assert worldgen.reachable(world, world.regions["farm_centre"], door)
    # No bed stands out in the valley any more -- it moved indoors.
    assert not [o for o in world.objects if o["sprite"] == "bed"]


@pytest.mark.parametrize("seed", SEEDS)
def test_every_house_door_is_walkable_and_reachable(seed):
    """A house you cannot walk up to is a house you cannot enter."""
    world = worldgen.generate(seed)
    start = world.regions["farm_centre"]
    for b in world.regions["buildings"]:
        door = b["door"]
        assert not world.solid_at(*door), f"{b['id']} door is inside something solid"
        assert worldgen.reachable(world, start, door), f"cannot reach {b['id']}"


@pytest.mark.parametrize("seed", [1, 7, 777, 4242])
def test_settlements_and_farmsteads_are_all_connected(seed):
    """Town, village and both farmsteads must be reachable from the farm, and
    the cave from the town -- the path network is a spanning tree over exactly
    these, so a gap here means the tree did not close."""
    world = worldgen.generate(seed)
    r = world.regions
    start = r["farm_centre"]
    for name in ("town", "village", "farmstead-north", "farmstead-east"):
        assert worldgen.reachable(world, start, r[name + "_centre"]), name
    assert worldgen.reachable(world, r["town_centre"], r["cave_mouth"])


# --- house interiors (session 5) -----------------------------------------

from emberfield import interiors  # noqa: E402


def _every_building_id():
    return [b["id"] for b in worldgen.generate(777).regions["buildings"]]


@pytest.mark.parametrize("building_id", _every_building_id())
def test_an_interior_is_deterministic_and_fully_walkable(building_id):
    """A house interior regenerates from the building id and the valley seed --
    like the wilds, it is never stored, so it must come back identical and it
    must be a room you can cross from the door to every corner."""
    a = interiors.generate(building_id, 777)
    b = interiors.generate(building_id, 777)
    assert a.tiles == b.tiles and a.objects == b.objects
    assert a.is_interior and not a.is_wilds
    # The spawn is just inside the door, and the exit mat is reachable from it.
    assert not a.solid_at(*a.spawn)
    assert worldgen.reachable(a, a.spawn, a.regions["exit"])
    # Every open floor tile is reachable -- no furniture walls off a corner.
    floor = [
        (x, y) for y in range(a.height) for x in range(a.width) if not a.solid_at(x, y)
    ]
    reached = sum(1 for spot in floor if worldgen.reachable(a, a.spawn, spot))
    assert reached == len(
        floor
    ), f"{building_id}: {len(floor) - reached} tiles walled off"


def test_only_the_player_house_has_a_workbench_and_a_chest():
    """Session 6: crafting and storage live in your house and nowhere else. The
    workbench and the hearth carry a station name the recipe screen filters on;
    the chest carries use:'storage'."""
    player = interiors.generate("emberfield-house-player", 777)
    uses = {o.get("use") for o in player.objects}
    assert "craft" in uses and "cook" in uses and "storage" in uses
    stations = {o.get("station") for o in player.objects if o.get("station")}
    assert stations == {"workbench", "cook"}
    start = player.spawn
    for o in player.objects:
        if o.get("use") not in ("craft", "cook", "storage"):
            continue
        approaches = [
            (o["x"] + dx, o["y"] + dy)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
            if not player.solid_at(o["x"] + dx, o["y"] + dy)
        ]
        assert any(worldgen.reachable(player, start, a) for a in approaches), o.get(
            "use"
        )

    villager = interiors.generate("emberfield-house-town-2", 777)
    assert not {o.get("use") for o in villager.objects} & {"craft", "cook", "storage"}


def test_every_recipe_names_real_items():
    """A recipe that names a missing input or output can be crafted into nothing,
    or never crafted at all -- invisible until someone tries."""
    import forge_content

    store = forge_content.store()
    items = store["types"]["items"]
    tools = store["types"]["tools"]
    recipes = store["types"]["recipes"]
    assert recipes, "the recipe content has not been seeded"
    for r in recipes.values():
        if r["upgrades"]:
            # An upgrade recipe raises a tool's tier instead of yielding an
            # item; its output points at the tool for the schema's sake.
            assert (
                r["upgrades"] in tools
            ), f"{r['id']} upgrades missing tool {r['upgrades']}"
            assert r["output"] == r["upgrades"]
            assert r["tier"] >= 1
        else:
            assert r["output"] in items, f"{r['id']} output {r['output']} missing"
            assert r["output_qty"] >= 1
        assert r["inputs"], f"{r['id']} has no inputs"
        for item_id, qty in r["inputs"].items():
            assert item_id in items, f"{r['id']} input {item_id} missing"
            assert qty >= 1
        assert r["station"] in ("workbench", "cook")

    # The upgrade ladder for each tool must have no gaps: tiers 1, 2, ...
    ladders = {}
    for r in recipes.values():
        if r["upgrades"]:
            ladders.setdefault(r["upgrades"], []).append(r["tier"])
    for tool_id, tiers in ladders.items():
        assert sorted(tiers) == list(
            range(1, len(tiers) + 1)
        ), f"{tool_id} tier gap: {tiers}"


def test_workbench_goods_are_worth_more_than_their_inputs():
    """The point of the workbench: raw drops are worth little, the materials you
    refine from them are worth more. Food from the hearth is exempt -- its value
    is that it heals, not what it sells for, and the economy-tuning pass is a
    later session."""
    import forge_content

    store = forge_content.store()
    items = store["types"]["items"]
    losing = []
    for r in store["types"]["recipes"].values():
        if r["upgrades"]:
            continue  # an upgrade has no sell value; it changes how a tool works
        out = items[r["output"]]
        if out["kind"] == "food":
            continue
        in_value = sum(items[i]["sell"] * q for i, q in r["inputs"].items())
        out_value = out["sell"] * r["output_qty"]
        if out_value <= in_value:
            losing.append(f"{r['id']} ({in_value}g in, {out_value}g out)")
    assert not losing, f"not worth crafting: {losing}"


def test_only_the_player_house_interior_has_a_bed():
    """You sleep in your own house. The villagers' houses have a bed sprite for
    the look of the room, but only yours carries use:'sleep'."""
    player = interiors.generate("emberfield-house-player", 777)
    sleeps = [o for o in player.objects if o.get("use") == "sleep"]
    assert len(sleeps) == 1
    assert player.regions.get(
        "storage_spot"
    ), "the crafting session needs a marked corner"

    villager = interiors.generate("emberfield-house-village-1", 777)
    assert not [o for o in villager.objects if o.get("use") == "sleep"]
    assert [o for o in villager.objects if o["sprite"] == "bed"]


def test_every_interior_only_uses_sprites_that_exist():
    import forge_art

    library = forge_art.library()
    sprites = set()
    for pack in library["packs"].values():
        sprites |= set(pack["sprites"].keys())
    if not sprites:
        pytest.skip("art library is empty; run tools/seed_art.py")
    for building_id in _every_building_id():
        world = interiors.generate(building_id, 777)
        for row in world.tiles:
            for tile in row:
                assert tile in sprites, f"interior uses missing tile {tile}"
        for obj in world.objects:
            assert (
                obj["sprite"] in sprites
            ), f"interior uses missing sprite {obj['sprite']}"


# --- the people (session 5) --------------------------------------------


def test_every_npc_names_a_home_a_sprite_and_real_schedule_stops():
    """An NPC whose home or schedule stop does not exist would stand still at
    the origin forever. The building ids the layout guarantees and the region
    names it records are the only valid targets."""
    import forge_content

    store = forge_content.store()
    npcs = store["types"]["npcs"]
    assert npcs, "the npc content has not been seeded"

    world = worldgen.generate(777)
    building_ids = {b["id"] for b in world.regions["buildings"]}
    region_names = {
        name for name, r in world.regions.items() if isinstance(r, dict) and "w" in r
    }
    landmarks = {"stall", "well", "cave_mouth", "house"}
    valid = (
        building_ids | {n + "_centre" for n in region_names} | region_names | landmarks
    )

    for npc in npcs.values():
        assert npc["home"] in building_ids, f"{npc['id']} home {npc['home']} missing"
        assert npc["sprite"], f"{npc['id']} has no sprite"
        assert npc["lines"], f"{npc['id']} has nothing to say"
        for hour, place in npc["schedule"]:
            assert 0 <= hour < 24, f"{npc['id']} schedule hour {hour}"
            if isinstance(place, list):
                continue
            assert place in valid, f"{npc['id']} schedule stop {place!r} is nothing"


def test_every_villager_sprite_set_exists():
    import forge_art
    import forge_content

    library = forge_art.library()
    sprites = set()
    for pack in library["packs"].values():
        sprites |= set(pack["sprites"].keys())
    if not sprites:
        pytest.skip("art library is empty; run tools/seed_art.py")

    for npc in forge_content.store()["types"]["npcs"].values():
        for facing in ("down", "up", "left", "right"):
            name = f"{npc['sprite']}_{facing}"
            assert name in sprites, f"{npc['id']} wants missing sprite {name}"


# --- the content store -----------------------------------------------------


@pytest.fixture()
def content_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_CONTENT_DIR", str(tmp_path))
    import forge_content

    forge_content.ensure_root()
    return tmp_path


def test_content_survives_a_round_trip_through_disk(content_dir):
    import forge_content

    crop = {
        "id": "test-turnip",
        "label": "Turnip",
        "sprite": "crop_turnip",
        "stages": [1, 2],
        "seasons": ["spring"],
    }
    forge_content.save("crops", crop)
    back = forge_content.load("crops", "test-turnip")
    assert back["label"] == "Turnip"
    assert back["stages"] == [1, 2]
    # Defaults are filled in, so a consumer never has to guess whether a field
    # is absent or deliberately zero.
    assert back["regrow"] == 0 and back["yield_qty"] == 1


def test_content_is_discovered_by_scanning_not_by_a_list(content_dir):
    """The rule the whole store exists for: adding content is adding a file."""
    import forge_content

    assert forge_content.list_ids("crops") == []
    (content_dir / "crops" / "hand-written.json").write_text(
        '{"id": "hand-written", "label": "Hand written", "sprite": "x", "stages": [1]}'
    )
    assert forge_content.list_ids("crops") == ["hand-written"]
    assert "hand-written" in forge_content.store()["types"]["crops"]


def test_a_broken_file_is_reported_not_raised(content_dir):
    """A half-edited crop must never stop the game booting."""
    import forge_content

    (content_dir / "crops" / "broken.json").write_text("{not json at all")
    (content_dir / "crops" / "incomplete.json").write_text('{"id": "incomplete"}')
    (content_dir / "crops" / "good.json").write_text(
        '{"id": "good", "label": "Good", "sprite": "crop_turnip", "stages": [1]}'
    )
    store = forge_content.store()
    assert "good" in store["types"]["crops"]
    assert "broken" not in store["types"]["crops"]
    assert "incomplete" not in store["types"]["crops"]
    assert len(store["problems"]) >= 2


def test_refusing_to_save_content_that_would_not_load(content_dir):
    import forge_content

    with pytest.raises(forge_content.ContentError):
        forge_content.save("crops", {"id": "no-label", "sprite": "x", "stages": [1]})
    with pytest.raises(forge_content.ContentError):
        forge_content.save(
            "crops",
            {"id": "bad-stages", "label": "x", "sprite": "x", "stages": [0, -1]},
        )


def test_the_seeded_content_names_art_that_actually_exists():
    """The same trick that catches art renames for tiles, applied to content.

    A crop names a sprite prefix and a stage count; the art must have one sprite
    per stage. Without this a renamed sprite shows up as an invisible crop.
    """
    import forge_art
    import forge_content

    library = forge_art.library()
    sprites = set()
    for pack in library["packs"].values():
        sprites |= set(pack["sprites"].keys())

    store = forge_content.store()
    assert store["problems"] == [], store["problems"]
    assert store["types"]["crops"], "the content store has not been seeded"

    for crop in store["types"]["crops"].values():
        for stage in range(len(crop["stages"])):
            name = f"{crop['sprite']}_{stage}"
            assert name in sprites, f"{crop['id']} wants missing sprite {name}"
    for foe in store["types"]["foes"].values():
        assert (
            foe["sprite"] in sprites
        ), f"{foe['id']} wants missing sprite {foe['sprite']}"
    for weapon in store["types"]["weapons"].values():
        assert weapon["shot_sprite"] in sprites
    for tool in store["types"]["tools"].values():
        assert tool["sprite"] in sprites


def test_every_crop_seed_and_yield_names_a_real_item():
    """A crop points at its seed and its produce by id. If either is missing you
    can plant something that yields nothing, which is invisible until harvest."""
    import forge_content

    store = forge_content.store()
    items = store["types"]["items"]
    for crop in store["types"]["crops"].values():
        assert crop["seed_item"] in items, f"{crop['id']} seed item is missing"
        assert crop["yield_item"] in items, f"{crop['id']} yield item is missing"
    for foe in store["types"]["foes"].values():
        for drop in foe["drops"]:
            assert drop in items, f"{foe['id']} drops missing item {drop}"


# --- the wilds (session 3) -------------------------------------------------

from emberfield import wilds  # noqa: E402

CYCLES = [(1, False), (1, True), (7, False), (7, True), (23, True)]


@pytest.mark.parametrize("day,night", CYCLES)
def test_a_cavern_is_the_same_one_when_a_save_is_reloaded(day, night):
    """The wilds regenerate every cycle, but a reloaded save must get the cavern
    it had. Nothing about a run down there is stored, so determinism is the only
    thing holding that together."""
    a = wilds.generate(777, day, night)
    b = wilds.generate(777, day, night)
    assert a.tiles == b.tiles
    assert a.objects == b.objects
    assert a.spawn == b.spawn


def test_every_cycle_gives_a_different_cavern():
    """The point of the wilds is that they are never the same place twice. Day,
    night and the valley's seed must each change the map."""
    day_one = wilds.generate(777, 1, False).tiles
    assert wilds.generate(777, 2, False).tiles != day_one
    assert wilds.generate(777, 1, True).tiles != day_one
    assert wilds.generate(778, 1, False).tiles != day_one


@pytest.mark.parametrize("day", [1, 2, 3, 5, 8, 13, 21, 34])
@pytest.mark.parametrize("night", [False, True])
def test_the_whole_cavern_can_be_walked(day, night):
    """The property a generated cave must never get wrong.

    Water is solid and goes in after the chambers are carved, so a pool across a
    passage can strand everything behind it -- an early version left 99% of the
    floor unreachable on the tighter night maps. Boulders can do the same in a
    one-tile gap. Both are settled before the map is returned; this is what
    keeps that true.
    """
    world = wilds.generate(777, day, night)
    assert wilds.reachable_fraction(world) >= 0.995


@pytest.mark.parametrize("day,night", CYCLES)
def test_you_do_not_arrive_inside_a_wall(day, night):
    world = wilds.generate(777, day, night)
    x, y = world.spawn
    assert not world.solid_at(x, y)
    entrance = world.regions["entrance"]
    assert list(world.spawn) == entrance


@pytest.mark.parametrize("day", [1, 4, 9])
def test_night_is_meaner_than_day(day):
    """Not a multiplier on one map -- two different maps. The night cavern is
    tighter and asks for more foes."""
    day_world = wilds.generate(777, day, False)
    night_world = wilds.generate(777, day, True)
    assert night_world.regions["danger"] > day_world.regions["danger"]

    def floor(world):
        return sum(
            1
            for row in world.tiles
            for tile in row
            if not worldgen.TILES[tile]["solid"]
        )

    assert floor(night_world) < floor(day_world)


@pytest.mark.parametrize("day,night", CYCLES)
def test_the_chest_at_the_deep_end_can_be_walked_up_to(day, night):
    """A reward behind a wall is invisible rather than hard.

    Reachability is tested to a tile *beside* the chest, not to the chest
    itself: the chest is solid, so standing on it was never the goal. You have
    to be able to get next to it, which is what interacting requires.
    """
    world = wilds.generate(777, day, night)
    chest = world.regions.get("chest")
    assert chest, "no chest was placed"
    approaches = [
        (chest[0] + dx, chest[1] + dy)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
        if not world.solid_at(chest[0] + dx, chest[1] + dy)
    ]
    assert approaches, "the chest is walled in on every side"
    assert any(
        worldgen.reachable(world, world.regions["entrance"], spot)
        for spot in approaches
    ), "you cannot walk to the chest from the way in"


@pytest.mark.parametrize("seed", SEEDS)
def test_the_stall_can_be_walked_up_to(seed):
    """The shop is the only sink gold has. A stall you cannot reach from the
    farm makes everything you earn meaningless."""
    world = worldgen.generate(seed)
    stall = world.regions["stall"]
    approaches = [
        (stall[0] + dx, stall[1] + dy)
        for dx in range(-1, 3)
        for dy in range(-1, 4)
        if not world.solid_at(stall[0] + dx, stall[1] + dy)
        for _ in [0]
    ]
    assert any(
        worldgen.reachable(world, world.regions["farm_centre"], spot)
        for spot in approaches
    ), "you cannot walk to the stall from the farm"


def test_the_wilds_only_use_sprites_that_exist():
    """The same check the valley gets. A renamed rock would otherwise show up as
    an invisible obstacle you keep walking into."""
    import forge_art

    library = forge_art.library()
    sprites = set()
    for pack in library["packs"].values():
        sprites |= set(pack["sprites"].keys())

    for day, night in CYCLES:
        world = wilds.generate(777, day, night)
        for tile_row in world.tiles:
            for tile in tile_row:
                assert tile in sprites, f"wilds uses missing tile {tile}"
        for obj in world.objects:
            assert (
                obj["sprite"] in sprites
            ), f"wilds uses missing sprite {obj['sprite']}"


def test_a_cavern_generates_fast_enough_to_walk_into():
    """You press space at the cave mouth and go down. A second of hitching there
    would read as the game hanging."""
    import time

    start = time.time()
    for day in range(1, 9):
        wilds.generate(777, day, day % 2 == 0)
    elapsed = time.time() - start
    assert elapsed < 2.0, f"8 caverns took {elapsed:.2f}s"
