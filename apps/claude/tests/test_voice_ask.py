"""Spoken questions for Claude: /api/voice/ask and /api/voice/reply run the
turn in one visible "Voice" conversation and hand back its final text.
Claude Code is tests/fake_claude.py, as in test_claude_panel.py; no real turn
is started. The avatar's /api/voice tries the voice service first."""

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import runner
import voice
import voice_ask
import web_app

FAKE = Path(__file__).with_name("fake_claude.py")
FORGE = {"X-Forge": "1"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_CLAUDE_BIN", f"{sys.executable} {FAKE}")
    monkeypatch.setenv("FAKE_CLAUDE_ARGS", str(tmp_path / "args.jsonl"))
    monkeypatch.setattr(web_app, "conversations", runner.Registry(tmp_path / "data"))
    monkeypatch.setattr(
        web_app, "desk", voice_ask.VoiceDesk(lambda: web_app.conversations)
    )
    yield TestClient(
        web_app.app, raise_server_exceptions=False, base_url="http://127.0.0.1:8445"
    )
    web_app.conversations.stop_all()


def ask(client, text):
    r = client.post(
        "/api/voice/ask", json={"text": text, "source": "voice"}, headers=FORGE
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_routes_need_the_forge_header(client):
    assert client.post("/api/voice/ask", json={"text": "hi"}).status_code == 403
    assert client.get("/api/voice/reply?id=x").status_code == 403
    foreign = {**FORGE, "Host": "rebind.example:8445"}
    assert (
        client.post("/api/voice/ask", json={"text": "hi"}, headers=foreign).status_code
        == 403
    )
    assert client.get("/api/voice/reply?id=x", headers=foreign).status_code == 403


def test_empty_question_and_unknown_id_are_refused(client):
    assert (
        client.post("/api/voice/ask", json={"text": "  "}, headers=FORGE).status_code
        == 400
    )
    assert client.get("/api/voice/reply?id=nope", headers=FORGE).status_code == 404


def test_a_question_gets_the_final_reply_in_one_visible_voice_conversation(client):
    first = ask(client, "what time is it")
    body = client.get(f"/api/voice/reply?id={first}&wait=20", headers=FORGE).json()
    assert body["done"] and not body["error"], body
    assert "echo:" in body["text"] and "what time is it" in body["text"]

    second = ask(client, "and the weather")
    again = client.get(f"/api/voice/reply?id={second}&wait=20", headers=FORGE).json()
    assert again["done"] and "and the weather" in again["text"]
    assert again["conversation"] == body["conversation"]  # reused, not a new one

    listed = client.get("/api/conversations", headers=FORGE).json()
    chats = listed["conversations"] if isinstance(listed, dict) else listed
    voice_rows = [c for c in chats if c.get("title") == "Voice"]
    assert len(voice_rows) == 1
    row = voice_rows[0]
    assert row["mode"] == runner.DEFAULT_MODE == "dontAsk"
    assert not row.get("ultracode")


def test_a_deleted_voice_conversation_is_made_again(client):
    first = client.get(
        f"/api/voice/reply?id={ask(client, 'one')}&wait=20", headers=FORGE
    ).json()
    assert (
        client.delete(
            f"/api/conversations/{first['conversation']}", headers=FORGE
        ).status_code
        == 200
    )
    second = client.get(
        f"/api/voice/reply?id={ask(client, 'two')}&wait=20", headers=FORGE
    ).json()
    assert second["done"] and second["conversation"] != first["conversation"]


def test_reply_wait_is_capped_at_thirty_seconds(monkeypatch):
    desk = voice_ask.VoiceDesk(lambda: None)
    desk._jobs["j"] = {"done": False, "text": "", "error": "", "conversation": ""}
    waits = []

    class Cond:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def wait(self, s):
            waits.append(s)
            desk._jobs["j"]["done"] = True

    desk._cond = Cond()  # type: ignore[assignment]
    desk.reply("j", 999)
    assert waits and waits[0] <= 30.0


@pytest.mark.parametrize(
    "events, expected",
    [
        ([], (False, "", "")),
        (
            [
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "text", "text": "hi"}]},
                }
            ],
            (False, "hi", ""),
        ),
        (
            [
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "text", "text": "first"}]},
                },
                {"type": "assistant", "message": {"content": [{"type": "tool_use"}]}},
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "text", "text": "last"}]},
                },
                {"type": "result", "subtype": "success"},
            ],
            (True, "last", ""),
        ),
        (
            [{"type": "result", "subtype": "success", "result": "from result"}],
            (True, "from result", ""),
        ),
        (
            [{"type": "result", "subtype": "error_max_turns", "is_error": True}],
            (True, "", "Claude Code ended the turn with an error"),
        ),
        (
            [{"type": "forge_exit", "code": 1}],
            (True, "", "Claude Code stopped before it answered"),
        ),
    ],
)
def test_reply_text_sweep(events, expected):
    assert voice_ask.reply_text(events) == expected


def test_avatar_voice_uses_the_service_first_then_falls_back(
    client, monkeypatch, tmp_path
):
    sent = {}

    class Answer:
        def __init__(self, data):
            self.data = data

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return self.data

    def fake_urlopen(request, timeout=0):
        sent.update(
            url=request.full_url,
            body=json.loads(request.data),
            headers=dict(request.headers),
        )
        return Answer(b"RIFF....WAVEfmt ")

    monkeypatch.setattr(voice.urllib.request, "urlopen", fake_urlopen)
    r = client.post(
        "/api/voice", json={"text": "hello", "voice": "bf_emma"}, headers=FORGE
    )
    assert r.status_code == 200 and r.content.startswith(b"RIFF")
    assert sent["url"].endswith(":8467/api/tts")
    assert sent["body"] == {
        "text": "hello",
        "app": "claude",
        "speed": 1.0,
        "voice": "bf_emma",
    }
    assert sent["headers"].get("X-forge") == "1"

    def down(request, timeout=0):
        raise voice.urllib.error.URLError("refused")

    monkeypatch.setattr(voice.urllib.request, "urlopen", down)
    wav = tmp_path / "local.wav"
    wav.write_bytes(b"RIFFlocal")
    monkeypatch.setattr(web_app.speaker, "say", lambda text, v, speed: wav)
    r = client.post("/api/voice", json={"text": "hello"}, headers=FORGE)
    assert r.status_code == 200 and r.content == b"RIFFlocal"
