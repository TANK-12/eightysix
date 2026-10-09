"""What has to be true for Janhollow to be a place rather than a diagram.

The station is built from data, so the tests are mostly about the build being
right whatever the data says: every room reachable, every schedule pointing
somewhere real, the clock running at the speed the setting asks for, and the
away modes doing what Emerson picked them to do.
"""

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from janhollow import content, saves, sim, station  # noqa: E402


@pytest.fixture(scope="module")
def store():
    return content.store()


@pytest.fixture(scope="module")
def built(store):
    return station.build(store)


# --- the station ------------------------------------------------------------


def test_content_has_no_problems(store):
    assert store["problems"] == []
    assert len(store["types"]["npcs"]) >= 8
    assert len(store["types"]["decks"]) >= 2


def test_every_room_has_a_door(built):
    for location_id in built.locations:
        assert (
            location_id in built.decks[built.locations[location_id]["deck"]].doors
        ), f"{location_id} has no door onto a corridor"


def test_every_room_is_reachable_from_the_lift(built):
    """The lift is the only way between decks, so a room you cannot walk to from
    it is a room no crew member can ever reach."""
    for location_id, location in built.locations.items():
        deck = built.decks[location["deck"]]
        spot = built.standing_spot(location_id)
        assert spot, f"{location_id} has nowhere to stand"
        assert deck.path(
            tuple(deck.lift), spot
        ), f"{location_id} is cut off from the lift"


def test_walls_are_derived_not_declared(built):
    """No file says where a wall is: hull next to floor becomes wall."""
    deck = built.decks["habitat"]
    assert any(tile == station.WALL for row in deck.grid for tile in row)
    assert deck.at(*deck.lift) == station.LIFT


def test_a_deck_survives_a_room_being_moved(store):
    """Moving a room two tiles is a data edit and nothing else: it still gets a
    door, and it is still reachable."""
    types = json.loads(json.dumps(store["types"]))
    moved = types["locations"]["galley"]
    moved["rect"] = [
        moved["rect"][0] + 1,
        moved["rect"][1],
        moved["rect"][2],
        moved["rect"][3],
    ]
    rebuilt = station.Station(types["decks"], types["locations"])
    assert rebuilt.problems == []
    deck = rebuilt.decks["habitat"]
    assert deck.path(tuple(deck.lift), rebuilt.standing_spot("galley"))


# --- schedules --------------------------------------------------------------


def test_schedules_point_at_real_locations(store, built):
    for npc_id, npc in store["types"]["npcs"].items():
        for entry in npc["schedule"]:
            assert (
                entry["goto"] in built.locations
            ), f"{npc_id} is scheduled to go to {entry['goto']!r}, which is not a room"


def test_scheduled_entry_wraps_past_midnight():
    entries = [
        {"at": "07:00", "goto": "mess_hall", "activity": "breakfast"},
        {"at": "22:00", "goto": "quarters_port", "activity": "sleep"},
    ]

    def where(minute):
        entry = sim.scheduled(entries, minute)
        assert entry is not None
        return entry["goto"]

    assert where(8 * 60) == "mess_hall"
    assert where(23 * 60) == "quarters_port"
    # Before the first entry of the day they are still living last night's.
    assert where(3 * 60) == "quarters_port"


def test_a_broken_schedule_is_reported_not_raised(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_CONTENT_DIR", str(tmp_path))
    store_ = content.forge_content.Store(content.TYPES, game="janhollow")
    store_.ensure_root()
    store_.save(
        "npcs",
        {
            "id": "wrong-way",
            "label": "Wrong Way",
            "job": "Tester",
            "schedule": [{"at": "9:00", "goto": ""}],
        },
        strict=False,
    )
    result = store_.store()
    assert result["types"]["npcs"] == {}
    assert any("schedule time" in p for p in result["problems"])
    assert any("no goto location" in p for p in result["problems"])


# --- the clock and the away modes -------------------------------------------


def world(built, store, **settings):
    crew = list(store["types"]["npcs"].values())
    return sim.World(built, crew, settings=settings)


def run(w, seconds, step=0.1, start=0.0):
    now = start
    for _ in range(int(seconds / step)):
        now += step
        w.tick(now)
    return now


def test_a_day_takes_the_configured_real_minutes(built, store):
    w = world(built, store, day_minutes=40, away_mode="run_closed")
    w.day, w.minute, w.last_tick = 1, 0.0, 0.0
    run(w, 40 * 60)
    # 40 real minutes is one station day, so 1440 station minutes have passed.
    # Compared as a total rather than as "day 2, 00:00": a tick is a tenth of a
    # second of floating point, and landing exactly on midnight is luck.
    elapsed = (w.day - 1) * sim.DAY_MINUTES + w.minute
    assert elapsed == pytest.approx(sim.DAY_MINUTES, abs=2)

    quick = world(built, store, day_minutes=4, away_mode="run_closed")
    quick.day, quick.minute, quick.last_tick = 1, 0.0, 0.0
    run(quick, 4 * 60 + 5)
    assert quick.day == 2, "a shorter day setting must roll the date over sooner"


def test_pause_unfocused_holds_the_station_still(built, store):
    w = world(built, store, day_minutes=40, away_mode="pause_unfocused")
    w.minute, w.last_tick, w.last_seen = 600.0, 0.0, -1000.0
    w.presence = "open"
    run(w, 120)
    assert w.minute == pytest.approx(
        600.0
    ), "an unfocused tab must not advance the clock"
    w.saw_page(True, now=1000.0)
    w.last_tick = 1000.0
    run(w, 60, start=1000.0)
    assert w.minute > 600.0


def test_run_closed_keeps_going_with_the_tab_shut(built, store):
    w = world(built, store, day_minutes=40, away_mode="run_closed")
    w.minute, w.last_tick, w.last_seen = 600.0, 0.0, -1000.0
    run(w, 120)
    assert w.minute > 600.0


def test_idle_closed_runs_but_forbids_models(built, store):
    w = world(built, store, away_mode="idle_closed")
    w.last_seen = -1000.0  # the tab is gone
    assert "closed" in w.mode["runs_when"]
    assert not w.models_allowed()


def test_time_skip_jumps_forward_on_return(built, store):
    w = world(built, store, day_minutes=40, away_mode="time_skip")
    w.minute, w.last_tick, w.last_seen = 480.0, 0.0, -1000.0
    run(w, 60)  # away: nothing happens
    assert w.minute == pytest.approx(480.0)
    summary = w.saw_page(True, now=600.0)  # ten minutes of real time away
    assert summary and summary["minutes"] > 0
    assert w.minute > 480.0
    assert w.pending_summary is not None
    assert w.pending_summary["needs_narrator"] is True


def test_a_long_absence_is_capped(built, store):
    w = world(built, store, day_minutes=40, away_mode="time_skip")
    w.minute, w.last_tick, w.last_seen = 0.0, 0.0, -100000.0
    w.saw_page(True, now=7 * 24 * 3600.0)  # a week
    assert (w.day - 1) * sim.DAY_MINUTES + w.minute <= sim.MAX_SKIP_MINUTES + 1


# --- crew -------------------------------------------------------------------


def test_crew_start_where_their_schedule_says(built, store):
    w = world(built, store)
    w.minute = 7 * 60
    for member in w.crew.values():
        assert member.deck, f"{member.id} was never placed"
        assert built.decks[member.deck].walkable(*member.tile())


def test_a_crew_member_crosses_decks_by_lift(built, store):
    w = world(built, store, day_minutes=40, away_mode="run_closed")
    member = w.crew["ilya-novak"]
    member.place_at("hydroponics")
    assert member.deck == "garden"
    member.head_for("mess_hall")
    assert member.pending_deck == "habitat"
    now = 0.0
    for _ in range(3000):
        now += 0.1
        member.step(0.1)
        if member.deck == "habitat" and not member.moving:
            break
    assert member.deck == "habitat"
    assert member.tile() == built.standing_spot("mess_hall", member.index)


def test_the_log_records_the_day_and_is_capped(built, store):
    w = world(built, store, day_minutes=8, away_mode="run_closed")
    w.last_tick, w.last_seen = 0.0, -1000.0
    run(w, 8 * 60)  # a whole day
    assert any(line["kind"] == "move" for line in w.log)
    assert len(w.log) <= sim.LOG_CAP


# --- saving -----------------------------------------------------------------


def test_save_and_load_round_trips(built, store, tmp_path, monkeypatch):
    monkeypatch.setattr(saves, "saves_dir", lambda: str(tmp_path))
    w = world(built, store, day_minutes=40, away_mode="run_closed")
    w.last_tick, w.last_seen = 0.0, -1000.0
    run(w, 300)
    state = w.save_state()
    saves.write("slot1", state)

    fresh = world(built, store)
    fresh.load_state(saves.read("slot1"))
    assert fresh.day == w.day
    assert fresh.minute == pytest.approx(w.minute)
    for cid, member in w.crew.items():
        assert fresh.crew[cid].location == member.location
        assert fresh.crew[cid].x == pytest.approx(member.x)
    assert saves.listing()[0]["slot"] == "slot1"


def test_settings_are_clamped_not_trusted():
    values = sim.clamp_settings(
        {"day_minutes": "nonsense", "away_mode": "off", "chatter": "screaming"}
    )
    assert values == sim.DEFAULT_SETTINGS
    assert sim.clamp_settings({"day_minutes": 0.1})["day_minutes"] == 2.0
    # Emerson asked for "much longer game days", so the ceiling is four real
    # days to one station day rather than half a day.
    assert sim.clamp_settings({"day_minutes": 5000})["day_minutes"] == 5000.0
    assert sim.clamp_settings({"day_minutes": 99999})["day_minutes"] == 5760.0
