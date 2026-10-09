from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from conftest import SIDS

H = {"X-Mission": "1"}


@pytest.fixture
def client(laptop, monkeypatch):
    import web_app
    from mc import actions

    monkeypatch.setattr(web_app, "_sources", lambda: laptop["src"])
    monkeypatch.setattr(actions, "claude_names", lambda: {})
    return TestClient(web_app.app)


def test_overview_and_same_answer(client):
    first = client.get("/api/overview").json()
    assert first["sessions"] and first["sig"]
    again = client.get("/api/overview", params={"sig": first["sig"]}).json()
    assert again["same"] is True and set(again) == {"same", "sig", "now"}


def test_posts_need_the_header(client):
    assert client.post("/api/crews/wave/notes", json={"text": "hi"}).status_code == 403


def test_note_lands_on_the_board(client, laptop):
    r = client.post(
        "/api/crews/wave/notes",
        json={"text": "hello helper", "to": "helper-1"},
        headers=H,
    )
    assert r.status_code == 200, r.text
    board = json.loads((laptop["crew_home"] / "wave" / "board.json").read_text())
    note = board["notes"][-1]
    assert (
        note["from"] == "Emerson"
        and note["to"] == "helper-1"
        and note["text"] == "hello helper"
    )


def test_ack_closes_a_note_for_emerson(client, laptop):
    assert (
        client.post("/api/crews/wave/notes/1/ack", json={}, headers=H).status_code
        == 200
    )
    data = client.get("/api/overview").json()
    assert not any(
        n["kind"] == "note" and n.get("note") == 1 for n in data["needs_you"]
    )


@pytest.mark.parametrize(
    "path,body,code",
    [
        ("/api/crews/wave/notes", {"text": "   "}, 400),
        ("/api/crews/wave/notes", {"text": "x" * 5000}, 400),
        ("/api/crews/no-such-crew/notes", {"text": "hi"}, 404),
        ("/api/crews/..%2Fetc/notes", {"text": "hi"}, (404, 405)),
        ("/api/crews/.hidden/notes", {"text": "hi"}, 400),
        ("/api/crews/wave/notes", {"text": "hi", "to": "bad name!"}, 400),
        ("/api/sessions/not-a-session!/message", {"text": "hi"}, 400),
        ("/api/relay/explode", {}, 400),
        ("/api/crews/wave/notes", {"text": "hi", "to": "nobody"}, 404),
        ("/api/crews/wave/notes", {"text": "hi", "to": "Emerson"}, 400),
        ("/api/crews/wave/notes", {"text": "hi", "re": -5}, 404),
        (
            "/api/crews/wave/notes",
            {"text": "hi", "re": 99999999999999999999999},
            (404, 422),
        ),
    ],
)
def test_bad_inputs_are_refused(client, path, body, code):
    got = client.post(path, json=body, headers=H).status_code
    assert got in (code if isinstance(code, tuple) else (code,))


def test_message_to_session_without_board_name_is_404(client):
    r = client.post(
        f"/api/sessions/{'0' * 8}-0000-0000-0000-000000000000/message",
        json={"text": "hi"},
        headers=H,
    )
    assert r.status_code == 404


def test_conversation_and_bad_ids(client):
    r = client.get(f"/api/sessions/{SIDS['busy']}/conversation")
    assert r.status_code == 200 and [i["kind"] for i in r.json()["items"]][:2] == [
        "prompt",
        "tool",
    ]
    assert (
        client.get(
            f"/api/sessions/{SIDS['busy']}/conversation", params={"agent": "abc123"}
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/sessions/{SIDS['busy']}/conversation", params={"agent": "../x"}
        ).status_code
        == 400
    )
    assert (
        client.get(
            f"/api/sessions/{SIDS['busy']}/conversation", params={"agent": "nope"}
        ).status_code
        == 404
    )
    assert client.get("/api/sessions/zzzz/conversation").status_code == 400


def test_relay_pause_when_relay_page_is_down(client, monkeypatch):
    from mc import actions

    monkeypatch.setattr(actions, "manifest_port", lambda **_: 9)  # nothing listens on 9
    r = client.post("/api/relay/pause", headers=H)
    assert r.status_code == 503 and "not running" in r.json()["detail"]


def test_open_in_claude_when_claude_app_is_down(client, monkeypatch):
    from mc import actions

    monkeypatch.setattr(actions, "manifest_port", lambda **_: 9)
    r = client.post(
        f"/api/sessions/{SIDS['busy']}/open", json={"state": "working"}, headers=H
    )
    assert r.status_code == 503


def test_page_and_shared_files_are_served(client):
    assert "Mission Control" in client.get("/").text
    assert client.get("/shared/forge.css").status_code == 200
    assert client.get("/logic.js").status_code == 200


def test_answer_to_existing_note_is_posted(client, laptop):
    r = client.post(
        "/api/crews/wave/notes",
        json={"text": "blue", "to": "ejb-busy", "re": 1},
        headers=H,
    )
    assert r.status_code == 200, r.text


def test_negative_before_is_refused(client):
    assert (
        client.get(
            f"/api/sessions/{SIDS['busy']}/conversation", params={"before": -5}
        ).status_code
        == 400
    )


def test_port_override(monkeypatch):
    from mc import actions

    monkeypatch.setenv("MISSION_PORT_RELAY", "9")
    assert actions.manifest_port(name="relay") == 9
