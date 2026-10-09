"""Bad input to Acchan's API gets a calm 4xx and never writes outside the
conversations folder (U1 sweep, 2026-10-08). No test here runs a model."""

from __future__ import annotations

import json
import queue
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCHAN_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("FORGE_JAN_SETTINGS_DIR", str(tmp_path / "jan"))
    monkeypatch.setenv("JAN_MODELS_DIR", str(tmp_path / "jan-models"))
    import acchan.conversation as conversation

    monkeypatch.setattr(conversation, "DATA", tmp_path / "data")
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    import web_app

    return TestClient(web_app.app)


def test_settings_refuse_wrong_types_and_keep_good_ones(client, tmp_path):
    assert client.post("/api/settings", json={"persona": "cat"}).status_code == 200
    for bad in (
        {"thinking": "yes"},
        {"speak": 1},
        {"reply_limit": "lots"},
        {"reply_limit": -5},
        {"reply_limit": True},
        {"persona": "pirate"},
        {"terminal_view": None},
        {"voice": "x" * 500},
        {"voice": 7},
    ):
        r = client.post("/api/settings", json=bad)
        assert r.status_code == 400, bad
        assert isinstance(r.json()["detail"], str)
    assert client.post("/api/settings", json=[1, 2]).status_code == 422
    assert client.post("/api/settings", json={"no_such": 1}).status_code == 200
    saved = client.get("/api/settings").json()
    assert saved["persona"] == "cat" and saved["thinking"] is False
    assert "no_such" not in saved


def test_a_hand_broken_settings_file_falls_back_to_defaults(tmp_path):
    from acchan import settings

    path = tmp_path / "data" / "settings.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"reply_limit": "huge", "thinking": "no", "persona": "cat"})
    )
    loaded = settings.load()
    assert loaded["reply_limit"] == 0 and loaded["thinking"] is False
    assert loaded["persona"] == "cat"
    path.write_text("[1, 2, 3]")
    assert settings.load() == settings.DEFAULTS


@pytest.mark.parametrize(
    "cid", ["../settings", "../../x", "a/b", "", 5, {"a": 1}, "ü" * 200]
)
def test_odd_conversation_ids_start_a_fresh_chat_inside_the_folder(cid, tmp_path):
    import web_app
    from acchan.conversation import Conversation, folder

    conv = web_app._conversation(cid, "web")
    assert conv.id != cid
    conv.save()
    assert conv.path.parent == folder()
    assert not (tmp_path / "data" / "settings.json").exists()
    with pytest.raises(ValueError):
        Conversation.load(cid)  # type: ignore[arg-type]


def test_a_corrupt_conversation_file_is_a_404_not_a_500(client):
    from acchan.conversation import folder

    (folder() / "broken.json").write_text("[1, 2]")
    (folder() / "noid.json").write_text("{}")
    assert client.get("/api/conversations/broken").status_code == 404
    assert client.get("/api/conversations/noid").status_code == 404
    assert client.delete("/api/conversations/broken").status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        {"messages": "hello"},
        {"messages": [1, "two", None]},
        {"messages": [{"role": "user", "content": "   "}]},
        {"messages": [{"role": "user", "content": {"x": 1}}]},
        {},
    ],
)
def test_openai_route_refuses_malformed_messages(client, body):
    r = client.post("/v1/chat/completions", json=body)
    assert r.status_code == 400
    assert isinstance(r.json()["detail"], str)


def test_openai_caller_name_cannot_steer_the_stored_chat_path(client, monkeypatch):
    import web_app

    seen = []

    class FakeAgent:
        def __init__(self, conv, **kw):
            seen.append(conv.id)

    def fake_events(agent, text):
        q: queue.Queue = queue.Queue()
        q.put({"type": "text", "delta": "ok"})
        q.put(None)
        return q

    monkeypatch.setattr(web_app, "Agent", FakeAgent)
    monkeypatch.setattr(web_app, "_events", fake_events)
    r = client.post(
        "/v1/chat/completions",
        json={
            "user": "../../evil/../x",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert r.status_code == 200
    assert r.json()["choices"][0]["message"]["content"] == "ok"
    assert seen == ["api-evilx"]


def test_odd_files_in_the_folder_never_break_the_chat_list(client):
    from acchan.conversation import Conversation, folder

    good = Conversation(source="web")
    good.save()
    (folder() / "list.json").write_text("[]")
    (folder() / "empty.json").write_text("{}")
    (folder() / "weird.json").write_text(
        json.dumps({"id": "weird", "updated": "soon", "messages": 5, "title": 3})
    )
    r = client.get("/api/conversations")
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()["conversations"]]
    assert good.id in ids and "weird" in ids and len(ids) == 2


def test_a_stored_id_that_is_a_path_is_refused(tmp_path):
    from acchan.conversation import Conversation, folder

    (folder() / "sneaky.json").write_text(json.dumps({"id": "../settings"}))
    with pytest.raises(ValueError):
        Conversation.load("sneaky")
    assert not (tmp_path / "data" / "settings.json").exists()


def test_an_unknown_voice_is_refused(client):
    assert client.post("/api/settings", json={"voice": "nobody"}).status_code == 400
    assert client.post("/api/settings", json={"voice": "af_heart"}).status_code == 200
