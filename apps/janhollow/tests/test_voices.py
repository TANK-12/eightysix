"""The model layer, tested without a model.

Everything here runs with Jan switched off: the guard is pure functions, the
client is exercised against a fake urlopen, and the chatter and the director
are driven by a fake client that returns whatever a test wants. That matters
because the real models are slow and non-deterministic, and because the rules
that keep bad output off the screen are exactly the ones a test should pin
down.

The samples in the guard tests are real output from the 0.8B on 2026-09-16,
kept verbatim -- they are the failures that made each rule exist.
"""

import json
import os
import random
import sys
import threading
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from janhollow import content as _content  # noqa: E402  (puts shared/ on sys.path)

_ = _content

import forge_jan  # noqa: E402  (janhollow/content.py puts shared/ on the path)

from janhollow import (
    chatter,
    content,
    director,
    guard,
    janclient,
    roles,
    sim,
    station,
)  # noqa: E402


@pytest.fixture(scope="module")
def store():
    return content.store()


@pytest.fixture(scope="module")
def built(store):
    return station.build(store)


def make_world(built, store, **settings):
    crew = list(store["types"]["npcs"].values())
    return sim.World(built, crew, settings=settings, content=store)


class FakeResponse:
    """Just enough of an HTTP response for urllib's `with` block."""

    def __init__(self, payload):
        self._data = json.dumps(payload).encode()

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeClient:
    """Stands in for Jan. `replies` is a list; each call pops the next one."""

    def __init__(self, replies=(), fail=False):
        self.replies = list(replies)
        self.fail = fail
        self.calls = []
        self.stats = {"calls": 0}

    def chat(self, role, system, user, **kwargs):
        self.calls.append({"role": role, "system": system, "user": user, **kwargs})
        if self.fail:
            raise janclient.JanError("no Jan here")
        if not self.replies:
            raise janclient.JanError("nothing left to say")
        return self.replies.pop(0)

    def model_for(self, role, fallback=""):
        return "fake-model"

    def online(self):
        return not self.fail


# --- getting the line out ---------------------------------------------------


def test_extract_handles_what_the_model_actually_sends():
    cases = [
        ('{"line": "Sit down, I made extra."}', "Sit down, I made extra.", "json"),
        ('```json\n{"line": "Morning."}\n```', "Morning.", "json"),
        ('"Just a bare quoted line."', "Just a bare quoted line.", "bare"),
        ("Plain text with no wrapper", "Plain text with no wrapper", "bare"),
        ('{"text": "The only field it filled."}', "The only field it filled.", "json"),
        # Cut off at the token limit, so the brace never closes. This one put
        # raw JSON in a speech bubble before the guard learned to salvage it.
        (
            '{"line": "I am glad you are here, Vessa, but it is quiet',
            "I am glad you are here, Vessa, but it is quiet",
            "json",
        ),
        ('{"line": ""}', "", "none"),
        ("", "", "none"),
    ]
    for raw, expected, how in cases:
        line, kind = guard.extract(raw)
        assert line == expected, raw
        assert kind == how, raw


def test_an_empty_shape_is_never_treated_as_speech():
    line, problems = guard.check('{"line": ""}', {"speaker": "Bo Ferreira"})
    assert line == ""
    assert any(p.startswith("empty") for p in problems)


# --- the rules --------------------------------------------------------------


def test_a_good_line_passes_every_rule():
    context = {"speaker": "Bo Ferreira", "listener": "Mira Song", "recent": []}
    assert guard.judge("Sit down before it goes cold, I made extra.", context) == []


@pytest.mark.parametrize(
    "line,rule",
    [
        ("", "empty"),
        ("...", "no_letters"),
        (" ".join(["word"] * 40), "too_long"),
        ("早上好，米拉，吃点东西吧", "not_english"),
        ("*wipes hands on apron* Morning!", "narration"),
        ('{"line": "leaked"', "narration"),
        ("Bo: eat up while it is hot", "name_label"),
        # The commonest slip of all: the speaker narrating themselves.
        (
            "Ready, Mira, or am I? Bo is certainly looking for a good start.",
            "self_third_person",
        ),
        ("coffee coffee coffee please", "repetition"),
    ],
)
def test_each_rule_fires_on_the_sample_that_made_it_exist(line, rule):
    context = {"speaker": "Bo Ferreira", "listener": "Mira Song", "recent": []}
    problems = guard.judge(line, context)
    assert any(p.startswith(rule) for p in problems), f"{rule} missed: {problems}"


def test_the_parrot_rule_catches_a_reworded_echo():
    context = {
        "speaker": "Mira Song",
        "recent": ["I'll check Vessa, but I won't let the crew know."],
    }
    problems = guard.judge(
        "I'll check Vessa, Dez, though we'd better have a drink.", context
    )
    assert any(p.startswith("parrot") for p in problems)
    # Replying about the same subject in different words is fine.
    assert guard.judge("We should have a drink before you go in, Dez.", context) == []


def test_copying_the_example_is_caught():
    context = {
        "speaker": "Bo",
        "example": "Sit down before it goes cold, I made extra for you.",
    }
    assert any(
        p.startswith("echo")
        for p in guard.judge(
            "Sit down before it goes cold, I made extra for you.", context
        )
    )


def test_rejected_samples_are_logged_and_capped(tmp_path):
    for i in range(guard.REJECT_LOG_CAP + 10):
        guard.log_rejection(
            str(tmp_path), f"raw {i}", "line", ["empty: nothing"], {"speaker": "Bo"}
        )
    lines = (
        (tmp_path / "rejected.jsonl").read_text(encoding="utf-8").strip().split("\n")
    )
    assert len(lines) == guard.REJECT_LOG_CAP
    assert json.loads(lines[-1])["raw"].endswith(str(guard.REJECT_LOG_CAP + 9))


# --- the client -------------------------------------------------------------


def test_the_client_always_turns_thinking_off(monkeypatch):
    """Measured: with thinking on, the 0.8B returns nothing but reasoning."""
    sent = {}

    def fake_urlopen(request, timeout=None):
        sent["body"] = json.loads(request.data.decode())
        return FakeResponse({"choices": [{"message": {"content": "hello"}}]})

    monkeypatch.setattr(forge_jan.urllib.request, "urlopen", fake_urlopen)
    client = janclient.Client(preferences={"chatter": "m"})
    assert client.chat("chatter", "sys", "user") == "hello"
    assert sent["body"]["chat_template_kwargs"] == {"enable_thinking": False}


def test_an_empty_reply_is_an_error_not_an_empty_line(monkeypatch):

    def fake_urlopen(request, timeout=None):
        return FakeResponse(
            {"choices": [{"message": {"content": "", "reasoning_content": "x" * 600}}]}
        )

    monkeypatch.setattr(forge_jan.urllib.request, "urlopen", fake_urlopen)
    client = janclient.Client(preferences={"chatter": "m"})
    with pytest.raises(janclient.JanError) as caught:
        client.chat("chatter", "sys", "user")
    assert "600 characters" in str(caught.value)


def test_only_one_request_reaches_jan_at_a_time(monkeypatch):
    """Two concurrent Jan requests once froze this laptop."""
    overlap = {"now": 0, "max": 0}
    lock = threading.Lock()

    def fake_urlopen(request, timeout=None):
        with lock:
            overlap["now"] += 1
            overlap["max"] = max(overlap["max"], overlap["now"])
        time.sleep(0.05)
        with lock:
            overlap["now"] -= 1
        return FakeResponse({"choices": [{"message": {"content": "hi"}}]})

    monkeypatch.setattr(forge_jan.urllib.request, "urlopen", fake_urlopen)
    client = janclient.Client(preferences={"chatter": "m"})
    threads = [
        threading.Thread(target=lambda: client.chat("chatter", "s", "u", wait=5))
        for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert overlap["max"] == 1


def test_the_app_prefers_its_own_models_over_whatever_jan_lists_first():
    """Without this the app picked an unrelated 2B that leaked thinking."""
    client = janclient.Client(preferences=roles.preferences())
    assert client.model_for("chatter") == roles.ROLES["chatter"]["prefer"]
    assert client.model_for("narrator") == roles.ROLES["narrator"]["prefer"]


# --- who talks --------------------------------------------------------------


def test_only_still_co_located_crew_are_picked(built, store):
    world = make_world(built, store)
    rng = random.Random(7)
    for member in world.crew.values():
        member.place_at("mess_hall")
    pair = chatter.pick_pair(world, rng)
    assert pair and pair[0].location == pair[1].location == "mess_hall"

    for member in world.crew.values():
        member.path = [(1, 1)]  # everybody is walking
    assert chatter.pick_pair(world, rng) is None

    for member in world.crew.values():
        member.path = []
        member.saying = "already talking"
    assert chatter.pick_pair(world, rng) is None


def test_the_prompt_carries_the_persona_and_the_relationship(built, store):
    world = make_world(built, store)
    bo = world.crew["bo-ferreira"]
    mira = world.crew["mira-song"]
    bo.place_at("mess_hall")
    mira.place_at("mess_hall")
    system = chatter.system_prompt(world, bo, mira)
    assert "Bo Ferreira" in system and "cook" in system
    assert bo.record["personality"][:20] in system
    assert chatter.warmth(bo.relationships.get("mira-song", 0)) in system
    assert "Mess hall" in system
    user = chatter.user_prompt(world, bo, mira, [("Mira Song", "Morning.")])
    assert "Mira Song: Morning." in user
    assert "do not repeat" in user.lower()


def test_a_conversation_is_applied_to_the_world(built, store):
    world = make_world(built, store)
    for member in world.crew.values():
        member.place_at("mess_hall")
    client = FakeClient(
        [
            '{"line": "Sit down, the coffee is fresh."}',
            '{"line": "You spoil us on a Tuesday."}',
            '{"line": "There is bread coming out in ten minutes."}',
        ]
    )
    conversation = chatter.converse(world, client, random.Random(3))
    assert conversation and len(conversation["lines"]) >= 2
    speakers = conversation["speakers"]
    a, b = world.crew[speakers[0]], world.crew[speakers[1]]
    assert a.relationships[b.id] >= 1, "talking to someone should warm them to you"
    assert a.memories, "a conversation should be remembered"
    assert any(entry["kind"] == "said" for entry in world.log)
    assert a.saying or b.saying, "the last line should still be in a bubble"


def test_a_rejected_line_is_retried_then_dropped(built, store):
    world = make_world(built, store)
    for member in world.crew.values():
        member.place_at("mess_hall")
    # Two bad replies: one retry, then the conversation ends rather than
    # showing junk.
    client = FakeClient(['{"line": "*shrugs*"}', '{"line": "*shrugs again*"}'])
    assert chatter.converse(world, client, random.Random(3)) is None
    assert world.model_status["rejected"] == 2
    assert world.model_status["lines"] == 0


def test_jan_being_down_is_quiet_not_fatal(built, store):
    world = make_world(built, store)
    for member in world.crew.values():
        member.place_at("mess_hall")
    assert chatter.converse(world, FakeClient(fail=True), random.Random(1)) is None
    assert "no Jan here" in world.model_status["last_error"]


# --- when anything happens --------------------------------------------------


def test_the_chatter_setting_sets_the_interval(built, store):
    world = make_world(built, store, chatter="moderate")
    boss = director.Director(world, FakeClient(), seed=1)
    assert boss.interval() == pytest.approx(60.0)
    world.update_settings({"chatter": "lively"})
    assert boss.interval() == pytest.approx(30.0)
    world.update_settings({"chatter": "off"})
    assert boss.interval() == 0.0
    assert boss.due(time.monotonic()) is False, "off means off"


def test_the_away_mode_can_forbid_every_model(built, store):
    world = make_world(built, store, away_mode="idle_closed", chatter="moderate")
    world.last_seen = -10000.0  # the tab is gone
    boss = director.Director(world, FakeClient(), seed=1)
    assert world.models_allowed() is False
    assert boss.step() == "not allowed"


def test_a_waiting_time_skip_is_narrated_before_anything_else(built, store):
    world = make_world(built, store, away_mode="time_skip", chatter="moderate")
    world.saw_page(True)
    world.pending_summary = {
        "minutes": 300,
        "from": "day 1, 08:00",
        "to": "day 1, 13:00",
        "needs_narrator": True,
    }
    world.new_day_pending = True  # a new day is waiting too, and must not win
    client = FakeClient(['{"story": "The station hummed along without you."}'])
    boss = director.Director(world, client, seed=1)
    assert boss.step() == "time-skip summary"
    assert world.pending_summary["needs_narrator"] is False
    assert world.pending_summary["story"] == "The station hummed along without you."
    assert client.calls[0]["role"] == "narrator"


def test_a_new_day_is_narrated_once(built, store):
    world = make_world(built, store, away_mode="run_closed", chatter="moderate")
    world.saw_page(True)
    world.new_day_pending = True
    client = FakeClient(
        [
            '{"headline": "A quiet morning", "story": "The lights came up over the garden deck."}'
        ]
    )
    boss = director.Director(world, client, seed=1)
    assert boss.step() == "the day's event"
    assert world.day_story is not None
    assert world.day_story["headline"] == "A quiet morning"
    assert any(entry["kind"] == "story" for entry in world.log)
    # Everyone remembers the day, and the flag is spent.
    assert all(member.memories for member in world.crew.values())
    assert world.take_new_day() is False


def test_a_failure_backs_off_instead_of_hammering_jan(built, store):
    world = make_world(built, store, away_mode="run_closed", chatter="moderate")
    world.saw_page(True)
    world.new_day_pending = True
    boss = director.Director(world, FakeClient(fail=True), seed=1, log=lambda *a: None)

    # narrator.day_event swallows the JanError and returns None, so force a
    # failure through the director's own guard rail instead.
    def explode():
        raise RuntimeError("Jan fell over")

    boss.narrate_day = explode
    assert boss.step().endswith("failed")
    assert boss.failures == 1
    assert boss.step() == "backing off"


def test_the_narrator_only_uses_events_the_station_can_host(built, store):
    from janhollow import narrator

    world = make_world(built, store)
    kinds = {loc.get("kind") for loc in built.locations.values()}
    assert "dock" in kinds
    chosen = narrator.choose_event(world, random.Random(5))
    assert chosen is not None
    impossible = {
        "id": "spacewalk",
        "label": "x",
        "needs": ["nowhere-kind"],
        "weight": 9,
    }
    assert narrator._event_fits(impossible, kinds, set()) is False


def test_opening_the_app_does_not_touch_jan(built, store):
    """Emerson opened the game by accident and found it had started a model.

    A new world is silent: the chatter level defaults to off, and off gates the
    narrator too, so nothing here loads anything until it is asked to.
    """
    assert sim.DEFAULT_SETTINGS["chatter"] == "off"
    world = make_world(built, store, away_mode="run_closed")
    world.saw_page(True)
    world.new_day_pending = True
    world.pending_summary = {"minutes": 90, "needs_narrator": True}
    client = FakeClient(['{"line": "should never be asked for"}'])
    boss = director.Director(world, client, seed=1)
    assert boss.step() == "voices off"
    assert client.calls == [], "nothing may reach Jan with the voices off"
    # Turning it up is what starts it.
    world.update_settings({"chatter": "moderate"})
    assert boss.step() == "time-skip summary"


@pytest.mark.parametrize(
    "line",
    [
        # Every one of these is real 0.8B output that passed every other rule.
        "Mira's smile softened as she looked at your empty plate.",
        "You see her smiling back as Tamsin hands you the groceries.",
        'She asked, "What is the best dish for your stomach?"',
        "He nodded slowly and turned back to the console.",
    ],
)
def test_narration_dressed_as_speech_is_caught(line):
    problems = guard.judge(
        line, {"speaker": "Vessa Oduya", "listener": "Mira Song", "recent": []}
    )
    assert any(p.startswith("prose") for p in problems), f"slipped through: {line}"


@pytest.mark.parametrize(
    "line",
    [
        "Sit down before it goes cold, I made extra for you.",
        "The reactor sounds happier this morning.",
        "Have you seen Tamsin? She owes me a spanner.",
        "I told her the barge was late.",
    ],
)
def test_real_speech_still_passes_the_prose_rule(line):
    problems = guard.judge(
        line, {"speaker": "Bo Ferreira", "listener": "Mira Song", "recent": []}
    )
    assert not any(
        p.startswith("prose") for p in problems
    ), f"false positive: {line} -> {problems}"
