"""Carrying things and giving them away.

Emerson picked the shape on 2026-09-17: four slots, things placed around the
station, put down anywhere and it stays, and gifts that land better when the
crew member actually likes what you bring. None of it needs Jan.
"""

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from janhollow import carry, content, sim, station  # noqa: E402

ART_ROOT = os.path.expanduser("~/ForgeArtData/packs")


@pytest.fixture(scope="module")
def store():
    return content.store()


@pytest.fixture(scope="module")
def built(store):
    return station.build(store)


def make_world(built, store):
    crew = list(store["types"]["npcs"].values())
    world = sim.World(built, crew, content=store)
    world.saw_page(True)
    world.player.join()
    return world


def stand_on(world, deck, x, y):
    world.player.deck = deck
    world.player.x, world.player.y = float(x), float(y)


def stand_by(world, member):
    """Put yourself next to a crew member, on a walkable tile."""
    deck = world.station.decks[member.deck]
    mx, my = member.tile()
    for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1), (0, 0)):
        if deck.walkable(mx + ox, my + oy):
            stand_on(world, member.deck, mx + ox, my + oy)
            return
    stand_on(world, member.deck, mx, my)


def pick_up_first(world):
    thing = world.floor_items[0]
    stand_on(world, thing["deck"], thing["x"], thing["y"])
    return carry.pick_up(world)


# --- the data ---------------------------------------------------------------


def test_items_are_content_and_every_sprite_exists(store):
    items = store["types"].get("items") or {}
    assert len(items) >= 5
    packs = {}
    for item in items.values():
        pack = item["pack"]
        if pack not in packs:
            with open(os.path.join(ART_ROOT, pack + ".json"), encoding="utf-8") as fh:
                packs[pack] = json.load(fh)["sprites"]
        assert item["sprite"] in packs[pack], item["id"]
        for where in item["starts_in"]:
            assert where in store["types"]["locations"], (item["id"], where)


def test_every_like_names_a_real_item(store):
    items = store["types"]["items"]
    liked = 0
    for npc in store["types"]["npcs"].values():
        for thing in npc.get("likes", []):
            assert thing in items, (npc["id"], thing)
            liked += 1
    assert liked >= len(store["types"]["npcs"])


def test_a_new_life_finds_things_in_their_rooms(built, store):
    world = make_world(built, store)
    items = store["types"]["items"]
    expected = sum(len(item["starts_in"]) for item in items.values())
    assert len(world.floor_items) == expected
    for thing in world.floor_items:
        deck = built.decks[thing["deck"]]
        assert deck.walkable(int(thing["x"]), int(thing["y"]))
        room = built.locations[items[thing["item"]]["starts_in"][0]]
        assert room["deck"] == thing["deck"]


# --- carrying ---------------------------------------------------------------


def test_picking_up_takes_it_off_the_floor(built, store):
    world = make_world(built, store)
    before = len(world.floor_items)
    uid = world.floor_items[0]["uid"]
    result = pick_up_first(world)
    assert result["ok"]
    assert len(world.floor_items) == before - 1
    assert [slot["uid"] for slot in world.player.inventory] == [uid]
    assert world.player.held == 0


def test_nothing_to_pick_up_far_away(built, store):
    world = make_world(built, store)
    world.floor_items = []
    assert carry.pick_up(world)["ok"] is False


def test_four_slots_and_no_more(built, store):
    world = make_world(built, store)
    first = world.floor_items[0]
    for n in range(carry.SLOTS + 1):
        world.floor_items.append(dict(first, uid=f"extra-{n}"))
    for _ in range(carry.SLOTS):
        assert pick_up_first(world)["ok"]
    assert len(world.player.inventory) == carry.SLOTS
    full = pick_up_first(world)
    assert full["ok"] is False
    assert len(world.player.inventory) == carry.SLOTS


def test_putting_down_leaves_it_where_you_stand(built, store):
    world = make_world(built, store)
    pick_up_first(world)
    stand_on(world, world.player.deck, world.player.x + 0.4, world.player.y)
    uid = world.player.inventory[0]["uid"]
    result = carry.put_down(world)
    assert result["ok"]
    assert world.player.inventory == []
    dropped = [t for t in world.floor_items if t["uid"] == uid][0]
    assert (dropped["x"], dropped["y"]) == world.player.tile()
    assert dropped["deck"] == world.player.deck


def test_select_changes_what_is_in_your_hands(built, store):
    world = make_world(built, store)
    first = world.floor_items[0]
    world.floor_items.append(dict(first, uid="extra"))
    pick_up_first(world)
    pick_up_first(world)
    assert world.player.held == 1
    assert carry.select(world, 0)["ok"]
    assert world.player.held == 0
    assert carry.select(world, 3)["ok"] is False


# --- giving -----------------------------------------------------------------


def someone_who_likes(world, store):
    items = store["types"]["items"]
    for member in world.crew.values():
        likes = member.record.get("likes") or []
        if likes:
            disliked = [i for i in items if i not in likes]
            return member, likes[0], disliked[0]
    raise AssertionError("nobody likes anything")


def give_item(world, member, item_id):
    world.player.inventory.append({"uid": f"gift-{item_id}", "item": item_id})
    world.player.held = len(world.player.inventory) - 1
    stand_by(world, member)
    return carry.give(world)


def test_a_liked_gift_warms_them_once_a_day(built, store):
    world = make_world(built, store)
    member, liked, _ = someone_who_likes(world, store)
    member.relationships.pop(world.player.id, None)
    first = give_item(world, member, liked)
    assert first["ok"] and first["liked"] and first["warmed"]
    assert member.relationships[world.player.id] == 1
    assert member.saying
    assert any("gave" in memory for memory in member.memories)
    assert world.player.inventory == []
    again = give_item(world, member, liked)
    assert again["ok"] and not again["warmed"]
    assert member.relationships[world.player.id] == 1
    world.day += 1
    assert give_item(world, member, liked)["warmed"]
    assert member.relationships[world.player.id] == 2


def test_something_they_do_not_like_is_only_polite(built, store):
    world = make_world(built, store)
    member, _, other = someone_who_likes(world, store)
    member.relationships.pop(world.player.id, None)
    result = give_item(world, member, other)
    assert result["ok"] and not result["liked"] and not result["warmed"]
    assert member.relationships.get(world.player.id, 0) == 0
    assert member.saying


def test_warmth_from_gifts_is_capped(built, store):
    world = make_world(built, store)
    member, liked, _ = someone_who_likes(world, store)
    member.relationships[world.player.id] = sim.RELATIONSHIP_CAP
    give_item(world, member, liked)
    assert member.relationships[world.player.id] == sim.RELATIONSHIP_CAP


def test_giving_needs_someone_next_to_you(built, store):
    world = make_world(built, store)
    world.player.inventory.append({"uid": "x", "item": "toolbox"})
    world.player.held = 0
    for member in world.crew.values():
        member.deck = "nowhere"
    assert carry.give(world)["ok"] is False
    assert len(world.player.inventory) == 1


# --- the menu and the save --------------------------------------------------


def test_actions_offer_pick_up_put_down_and_give(built, store):
    world = make_world(built, store)
    thing = world.floor_items[0]
    stand_on(world, thing["deck"], thing["x"], thing["y"])
    kinds = [a["kind"] for a in world.player.actions(world)]
    assert "pickup" in kinds
    carry.pick_up(world)
    member = next(iter(world.crew.values()))
    stand_by(world, member)
    labels = {a["kind"]: a["label"] for a in world.player.actions(world)}
    assert "drop" in labels and "give" in labels
    assert member.record["label"] in labels["give"]


def test_snapshot_shows_the_floor_and_your_hands(built, store):
    world = make_world(built, store)
    pick_up_first(world)
    snap = world.snapshot()
    assert "items" in snap and isinstance(snap["items"], list)
    carrying = snap["player"]["carrying"]
    assert carrying[0]["sprite"] and carrying[0]["label"]
    assert snap["player"]["held"] == 0


def test_save_and_load_keep_what_you_carry_and_what_is_on_the_floor(built, store):
    world = make_world(built, store)
    pick_up_first(world)
    member, liked, _ = someone_who_likes(world, store)
    give_item(world, member, liked)
    pick_up_first(world)
    state = json.loads(json.dumps(world.save_state()))
    again = make_world(built, store)
    again.load_state(state)
    assert again.player.inventory == world.player.inventory
    assert again.player.held == world.player.held
    assert again.floor_items == world.floor_items
    assert again.gifts_given == world.gifts_given


def test_an_old_save_without_items_keeps_the_seeded_floor(built, store):
    world = make_world(built, store)
    state = json.loads(json.dumps(world.save_state()))
    for key in ("floor_items", "gifts_given"):
        state.pop(key, None)
    state["player"].pop("inventory", None)
    state["player"].pop("held", None)
    again = make_world(built, store)
    seeded = list(again.floor_items)
    again.load_state(state)
    assert again.floor_items == seeded
    assert again.player.inventory == []
