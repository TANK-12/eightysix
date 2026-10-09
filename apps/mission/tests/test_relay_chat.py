"""The WhatsApp chat with Relay, mirrored (mc/relay_chat.py, task 109)."""

from __future__ import annotations

import sys

import pytest
from fastapi.testclient import TestClient

H = {"X-Mission": "1"}


@pytest.fixture
def relay(laptop):
    """Relay's own chat module on the fake data folder, the chat made."""
    from mc import borrow

    borrow.setup()
    import chat  # pyright: ignore[reportMissingImports]
    import store  # pyright: ignore[reportMissingImports]

    store.save_settings({"whatsapp_frontdesk": "off", "whatsapp_fallback": "off"})
    chat.chat_task()
    return chat


@pytest.fixture
def client(laptop):
    import web_app

    return TestClient(web_app.app)


def test_no_chat_yet(client, laptop):
    got = client.get("/api/relay-chat").json()
    assert got["task"] is None and "messages" not in got


def test_thread_reads_the_messages_and_says_same(client, relay):
    task, _ = relay.route("who is using my cpu")  # as a WhatsApp line does
    relay.log_reply("Mostly Exo Lab.\nAnd a test.", "Relay")
    relay.log_reply("All quiet.", "Boss")
    got = client.get("/api/relay-chat").json()
    said = [(m["who"], m["me"], m["new"], m["text"]) for m in got["messages"]]
    assert said == [
        ("Emerson", True, True, "who is using my cpu"),
        ("Relay", False, False, "Mostly Exo Lab.\nAnd a test."),
        ("Boss", False, False, "All quiet."),
    ]
    assert all(m["at"] for m in got["messages"])
    assert len({m["key"] for m in got["messages"]}) == 3
    assert got["task"] == task["id"] and got["answering"] is True  # queued
    again = client.get("/api/relay-chat", params={"seen": got["version"]}).json()
    assert again["same"] is True and "messages" not in again
    relay.log_reply("One more.")
    newer = client.get("/api/relay-chat", params={"seen": got["version"]}).json()
    assert [m["key"] for m in newer["messages"][:3]] == [
        m["key"] for m in got["messages"]
    ]  # kept lines keep their keys
    assert newer["messages"][-1]["text"] == "One more."


def test_bad_version_is_refused(client):
    assert client.get("/api/relay-chat", params={"seen": "<b>"}).status_code == 400


@pytest.fixture
def fake_cli(tmp_path, monkeypatch):
    """A stand-in for `relay as-whatsapp` that records what it was given."""
    from mc import relay_chat

    got = tmp_path / "got.txt"
    script = tmp_path / "cli.py"
    script.write_text(
        "import sys, time\n"
        "text = sys.stdin.read()\n"
        f"open({str(got)!r}, 'w').write(text)\n"
        "if text.startswith('fail'): sys.exit('Traceback\\nValueError: broken')\n"
        "if text.startswith('slow'): time.sleep(5)\n"
        "print('Sent: the answer comes in the chat.')\n"
    )
    monkeypatch.setattr(
        relay_chat, "command", lambda: [sys.executable, str(script), "as-whatsapp"]
    )
    return got


def test_say_runs_relay_as_whatsapp(client, fake_cli):
    r = client.post("/api/relay-chat/say", json={"text": "  hi there "}, headers=H)
    assert r.status_code == 200 and r.json()["reply"].startswith("Sent")
    assert fake_cli.read_text() == "hi there"
    client.post(
        "/api/relay-chat/say", json={"text": "status?", "boss": True}, headers=H
    )
    assert fake_cli.read_text() == "boss: status?"
    client.post(
        "/api/relay-chat/say", json={"text": "Boss, any news", "boss": True}, headers=H
    )
    assert fake_cli.read_text() == "Boss, any news"  # not "boss: Boss, ..."


def test_say_refuses_and_reports(client, fake_cli, monkeypatch):
    from mc import relay_chat

    assert client.post("/api/relay-chat/say", json={"text": "hi"}).status_code == 403
    r = client.post("/api/relay-chat/say", json={"text": "   "}, headers=H)
    assert r.status_code == 400
    r = client.post("/api/relay-chat/say", json={"text": "fail now"}, headers=H)
    assert r.status_code == 502 and "ValueError: broken" in r.json()["detail"]
    monkeypatch.setattr(relay_chat, "SAY_TIMEOUT", 0.5)
    r = client.post("/api/relay-chat/say", json={"text": "slow one"}, headers=H)
    assert r.status_code == 504 and "check the chat" in r.json()["detail"]
    monkeypatch.setattr(relay_chat, "command", lambda: ["/nope/python", "/nope/cli"])
    r = client.post("/api/relay-chat/say", json={"text": "hi"}, headers=H)
    assert r.status_code == 503


def test_say_with_the_real_relay_cli(client, relay):
    """End to end: Relay's own cli.py (its venv) on the fake data folder."""
    r = client.post("/api/relay-chat/say", json={"text": "status"}, headers=H)
    assert r.status_code == 200, r.text
    answer = r.json()["reply"]
    said = client.get("/api/relay-chat").json()["messages"]
    assert [(m["who"], m["text"]) for m in said][0] == ("Emerson", "status")
    assert said[1]["who"] == "Relay" and said[1]["text"].split("\n")[0] in answer
    assert not said[0]["new"]  # a command: the chat session does not answer it
