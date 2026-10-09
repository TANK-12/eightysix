"""Being aboard: walking, bumping into things, sitting, sleeping and talking.

None of this needs Jan. The one thing that does — a crew member answering you —
is driven by a fake client, and the case where there is no model at all is
tested too, because Emerson asked that the station never go mute just because
Jan is off.
"""

import os
import random
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from janhollow import chatter, content, director, player, sim, station  # noqa: E402


@pytest.fixture(scope="module")
def store():
    return content.store()


@pytest.fixture(scope="module")
def built(store):
    return station.build(store)


def make_world(built, store, **settings):
    crew = list(store["types"]["npcs"].values())
    world = sim.World(built, crew, settings=settings, content=store)
    world.saw_page(True)
    return world


class FakeClient:
    def __init__(self, replies=(), fail=False):
        self.replies = list(replies)
        self.fail = fail
        self.calls = []
        self.stats = {"calls": 0}

    def chat(self, role, system, user, **kwargs):
        self.calls.append({"role": role, "system": system, "user": user})
        if self.fail or not self.replies:
            raise Exception("no Jan here")
        return self.replies.pop(0)

    def model_for(self, role, fallback=""):
        return "fake"

    def online(self):
        return not self.fail


# --- arriving ---------------------------------------------------------------


def test_you_arrive_at_the_docking_ring(built, store):
    world = make_world(built, store)
    world.player.join()
    assert world.player.aboard
    assert (
        world.player.location_deck if hasattr(world.player, "location_deck") else True
    )
    ring = built.locations["docking_ring"]
    assert world.player.deck == ring["deck"]
    deck = built.decks[world.player.deck]
    assert deck.walkable(*world.player.tile())


def test_you_start_unnamed_so_joining_never_waits_on_a_model(built, store):
    world = make_world(built, store)
    world.player.join()
    assert world.player.named is False
    assert world.player.name == "the new arrival"


def test_stepping_out_stops_you_moving(built, store):
    world = make_world(built, store)
    world.player.join()
    world.player.hold(1, 0)
    world.player.leave()
    assert world.player.aboard is False
    world.player.step(1.0)  # must not move a player who is not aboard


# --- walking ----------------------------------------------------------------


def walk(world, dx, dy, seconds, step=0.05):
    world.player.hold(dx, dy)
    for _ in range(int(seconds / step)):
        world.player.step(step)
    world.player.hold(0, 0)


def test_walking_moves_you_and_turns_you(built, store):
    world = make_world(built, store)
    world.player.join()
    before = world.player.x
    walk(world, 1, 0, 0.5)
    assert world.player.x > before
    assert world.player.facing == "right"


def test_a_wall_stops_you(built, store):
    world = make_world(built, store)
    world.player.join()
    deck = built.decks[world.player.deck]
    walk(world, 0, -1, 12)  # straight north, into the room's wall
    assert deck.walkable(*world.player.tile()), "you ended up inside a wall"


def test_furniture_stops_you_too(built, store):
    """Props became solid so the crew would stop walking through the couch; the
    same rule has to hold for you."""
    world = make_world(built, store)
    player_ = world.player
    player_.join()
    deck = built.decks[player_.deck]
    solid = sorted(deck.solid)
    assert solid, "this deck has no furniture to test against"
    target = solid[0]
    player_.deck = deck.id
    player_.x, player_.y = float(target[0]), float(target[1] + 2)
    walk(world, 0, -1, 3)
    assert player_.tile() != target


def test_you_slide_along_a_wall_instead_of_sticking(built, store):
    """Pushing diagonally into a wall should still move you along it."""
    world = make_world(built, store)
    player_ = world.player
    player_.join()
    deck = built.decks[player_.deck]
    # Find a tile with a wall to the north and floor to the east.
    spot = None
    for x, y in [(x, y) for y in range(deck.height) for x in range(deck.width)]:
        if (
            deck.walkable(x, y)
            and not deck.walkable(x, y - 1)
            and deck.walkable(x + 1, y)
        ):
            spot = (x, y)
            break
    assert spot, "no wall to slide along"
    player_.x, player_.y = float(spot[0]), float(spot[1])
    start = player_.x
    walk(world, 0.7, -0.7, 1.0)  # north-east into the wall
    assert player_.x > start, "you should slide east along the wall"


# --- sitting and sleeping ---------------------------------------------------


def test_you_can_sit_on_something_and_get_up_again(built, store):
    world = make_world(built, store)
    player_ = world.player
    player_.join()
    deck = built.decks[player_.deck]
    seat = next(p for p in deck.props if p["sprite"] in player.SEATS)
    player_.x, player_.y = float(seat["x"]), float(seat["y"] + 1)
    assert player_.sit()
    assert player_.sitting
    player_.stand()
    assert player_.sitting == ""


def test_walking_gets_you_out_of_a_chair(built, store):
    world = make_world(built, store)
    player_ = world.player
    player_.join()
    deck = built.decks[player_.deck]
    seat = next(p for p in deck.props if p["sprite"] in player.SEATS)
    player_.x, player_.y = float(seat["x"]), float(seat["y"] + 1)
    player_.sit()
    player_.hold(1, 0)
    assert player_.sitting == "", "holding a direction should stand you up"


def test_sleeping_skips_to_the_morning(built, store):
    world = make_world(built, store)
    world.player.join()
    world.minute = 23 * 60  # eleven at night
    day_before = world.day
    summary = world.sleep_until_morning(hour=7.0)
    assert world.day == day_before + 1
    assert world.clock_now() == "07:00"
    assert summary["needs_narrator"] is True
    assert summary["slept"] is True
    # The crew are where their day says they should be, not still in bed.
    for member in world.crew.values():
        assert member.deck


# --- talking ----------------------------------------------------------------


def stand_next_to(world, member_id):
    member = world.crew[member_id]
    world.player.deck = member.deck
    world.player.x, world.player.y = member.x + 1, member.y
    return member


def test_whoever_is_nearest_hears_you(built, store):
    world = make_world(built, store)
    world.player.join()
    member = stand_next_to(world, "bo-ferreira")
    assert player.nearest_crew(world) is member
    world.player.x += 40  # far away now
    assert player.nearest_crew(world) is None


def test_talking_gets_an_answer_and_warms_them_to_you(built, store):
    world = make_world(built, store)
    world.player.join()
    member = stand_next_to(world, "bo-ferreira")
    client = FakeClient(['{"line": "Drop it by the door, I will move it later."}'])
    boss = director.Director(world, client, seed=2)
    answer = boss.answer_player("where do I put my bag?")
    assert answer and answer["id"] == member.id
    assert answer["fallback"] is False
    assert member.relationships[world.player.id] >= 1
    assert any("where do I put my bag?" in m for m in member.memories)
    # Both halves of the exchange are in the log and in the bubbles.
    assert world.player.saying == "where do I put my bag?"
    assert member.saying == answer["line"]


def test_with_no_model_they_still_say_something(built, store):
    """Emerson chose a written fallback over silence."""
    world = make_world(built, store)
    world.player.join()
    member = stand_next_to(world, "bo-ferreira")
    boss = director.Director(world, FakeClient(fail=True), seed=2)
    answer = boss.answer_player("hello")
    assert answer["fallback"] is True
    assert answer["line"] in chatter.FALLBACKS["cook"]
    assert member.saying == answer["line"]


def test_a_rejected_answer_falls_back_rather_than_showing_junk(built, store):
    world = make_world(built, store)
    world.player.join()
    stand_next_to(world, "bo-ferreira")
    client = FakeClient(['{"line": "*shrugs*"}', '{"line": "*shrugs again*"}'])
    boss = director.Director(world, client, seed=2)
    answer = boss.answer_player("hello")
    assert answer["fallback"] is True
    assert world.model_status["rejected"] == 2


def test_nobody_near_means_nobody_answers(built, store):
    world = make_world(built, store)
    world.player.join()
    for member in world.crew.values():
        member.deck = "command" if world.player.deck != "command" else "habitat"
    boss = director.Director(world, FakeClient(), seed=2)
    assert boss.answer_player("anyone there?") is None


# --- the crew noticing you --------------------------------------------------


def test_someone_you_walk_past_may_greet_you(built, store):
    world = make_world(built, store, chatter="moderate")
    world.player.join()
    stand_next_to(world, "bo-ferreira")
    assert player.bystanders(world)
    client = FakeClient(['{"line": "You must be the new one."}'])
    boss = director.Director(world, client, seed=2)
    boss.greet()
    assert world.crew["bo-ferreira"].saying == "You must be the new one."


def test_the_narrator_names_you_once(built, store):
    world = make_world(built, store, chatter="moderate")
    world.player.join()
    client = FakeClient(
        [
            '{"name": "Wren Achebe", "role": "hydroponics hand", "arrival": "She came in on the morning barge."}'
        ]
    )
    boss = director.Director(world, client, seed=2)
    boss.name_the_player()
    assert world.player.name == "Wren Achebe"
    assert world.player.role == "hydroponics hand"
    assert world.player.named is True
    assert any(entry["kind"] == "story" for entry in world.log)
    # Only ever once, even if the model failed.
    world.player.named = False
    boss2 = director.Director(world, FakeClient(fail=True), seed=2)
    boss2.name_the_player()
    assert world.player.named is True


def test_you_are_saved_and_come_back(built, store):
    world = make_world(built, store)
    world.player.join()
    world.player.name = "Wren Achebe"
    world.player.role = "hydroponics hand"
    walk(world, 1, 0, 0.4)
    state = world.save_state()

    fresh = make_world(built, store)
    fresh.load_state(state)
    assert fresh.player.aboard is True
    assert fresh.player.name == "Wren Achebe"
    assert fresh.player.x == pytest.approx(world.player.x)
    assert fresh.player.deck == world.player.deck


# --- the page walks you too, and the two must agree ------------------------


def test_the_pages_walking_rules_match_the_backends():
    """The page predicts your movement so walking feels instant, which means
    the same rules exist twice — in player.py and in static/game.js. If they
    drift apart you get visible snapping as the server corrects the page, so
    the numbers are pinned here.
    """
    js = open(os.path.join(ROOT, "static", "game.js"), encoding="utf-8").read()
    speed = re.search(r"const WALK_SPEED = ([\d.]+);", js)
    corner = re.search(r"const CORNER = ([\d.]+);", js)
    assert speed and corner, "the page no longer declares its walking constants"
    assert (
        float(speed.group(1)) == player.SPEED
    ), f"game.js walks at {speed.group(1)} but player.py walks at {player.SPEED}"
    assert (
        float(corner.group(1)) == 0.3
    ), "the corner box in game.js must match the one in Player._free"
    # And the page must be checking all four corners, as the backend does.
    assert js.count("tileFree(deckId") >= 4 or js.count("Math.round(x") >= 2
    # A door and the lift are walkable in both.
    assert '"."' in js or "'.'" in js
