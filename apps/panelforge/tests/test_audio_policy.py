"""The sound policy: dry voices, no sound effects, no music unless placed by
hand (Emerson, 2026-09-20)."""

import importlib

import pytest

from panelforge.audio import policy


@pytest.fixture()
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("PANELFORGE_DATA", str(tmp_path))
    from panelforge import paths

    importlib.reload(paths)
    paths.ensure_roots()
    return tmp_path


def test_defaults_are_dry_and_quiet(data):
    assert policy.read() == {"echo": "none", "sfx": False, "music": False}


def test_echo_none_strips_the_scenes_guess_but_not_a_hand_set_room():
    em = {"speed": 1.0, "room": "hall", "reverb": 0.9, "eq": "void", "grit": 0.1}
    dry = policy.apply_echo(em, "none")
    assert dry["reverb"] == 0.0 and "room" not in dry and "eq" not in dry
    assert dry["speed"] == 1.0
    by_hand = {**em, "source": "user"}
    assert policy.apply_echo(by_hand, "none") == by_hand


def test_echo_comms_keeps_only_the_radio_filter():
    radio = {"room": "comms", "reverb": 0.0, "eq": "radio", "grit": 0.1}
    out = policy.apply_echo(radio, "comms")
    assert out["eq"] == "radio" and "room" not in out
    hall = {"room": "hall", "reverb": 0.9}
    assert policy.apply_echo(hall, "comms")["reverb"] == 0.0
    assert policy.apply_echo(hall, "scene") == hall


def test_sound_and_music_play_only_when_asked_or_placed_by_hand(data):
    auto = {"id": "x1", "source": "auto"}
    user = {"id": "x2", "source": "user"}
    assert not policy.plays(auto, "sfx") and policy.plays(user, "sfx")
    assert not policy.plays(auto, "music") and policy.plays(user, "music")
    policy.write({"sfx": True})
    assert policy.plays(auto, "sfx") and not policy.plays(auto, "music")


def test_policy_route_round_trips_and_refuses_nonsense(data):
    from fastapi.testclient import TestClient

    import web_app

    importlib.reload(web_app)
    c = TestClient(web_app.app)
    assert c.get("/api/sound").json()["echo"] == "none"
    r = c.put("/api/sound", json={"echo": "comms", "music": True})
    assert r.json() == {"echo": "comms", "sfx": False, "music": True}
    assert c.put("/api/sound", json={"echo": "loud"}).status_code == 400
    assert c.get("/api/sound").json()["echo"] == "comms"
