"""POST /api/voice/command: fast path, then phrases, then the model; risky
tools refused from voice. No tool really runs and no model is called: the
tool runner and the agent are faked."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

import web_app  # noqa: E402
from acchan import router, voice_command  # noqa: E402
from acchan.tools import apps  # noqa: E402


@pytest.fixture
def ran(monkeypatch):
    calls = []

    def fake_run(name, args):
        calls.append((name, args))
        return True, {"set_volume": "Volume 40%."}.get(name, f"Did {name}.")

    monkeypatch.setattr(voice_command, "_run", fake_run)

    def no_model(text, deadline, allow):
        raise AssertionError("the model must not be called")

    monkeypatch.setattr(web_app, "_voice_agent", no_model)
    return calls


client = TestClient(web_app.app, base_url="http://127.0.0.1:8451")
FORGE = {"X-Forge": "1"}


def post(text, **extra):
    answer = client.post(
        "/api/voice/command", json={"text": text, **extra}, headers=FORGE
    )
    assert answer.status_code == 200, answer.text
    return answer.json()


def test_fast_path_hit(ran):
    assert router.fast_path("pause the music")
    body = post("pause the music")
    assert body["handled_by"] == "fast"
    assert body["calls"] and body["calls"][0]["ok"]
    assert ran and isinstance(body["ms"], int)


def test_phrase_hit(ran):
    text = "could you turn it down to 40"
    assert router.fast_path(text) is None
    body = post(text)
    assert body["handled_by"] == "phrase"
    assert ran == [("set_volume", {"percent": 40})]
    assert body["calls"] == [
        {"tool": "set_volume", "args": {"percent": 40}, "ok": True}
    ]
    assert body["reply"] == "Volume 40%."


def test_risky_fast_call_refused_from_voice(ran):
    fast = router.fast_path("close this tab")
    assert fast and voice_command.voice_blocked(fast[0].tool)
    body = post("close this tab")
    assert ran == []
    assert "confirm it in Acchan" in body["reply"]
    assert body["calls"][0]["ok"] is False


def test_risky_phrase_refused(monkeypatch, ran):
    monkeypatch.setattr(router, "fast_path", lambda text: None)
    monkeypatch.setattr(
        voice_command.phrases,
        "match",
        lambda text: ("run_command", {"command": "ls"}, 1.0),
    )
    body = post("list my files in a shell")
    assert ran == [] and "confirm it in Acchan" in body["reply"]


@pytest.mark.parametrize(
    "name",
    [
        "run_command",
        "shell_run",
        "shell_send",
        "press_keys",
        "type_text",
        "trash",
        "move_path",
        "write_file",
        "close_window",
        "close_tab",
        "terminal_type",
    ],
)
def test_voice_blocks_risky_tools(name):
    assert voice_command.voice_blocked(name)


@pytest.mark.parametrize(
    "name", ["launch_app", "set_volume", "media_control", "open_web", "weather"]
)
def test_voice_allows_safe_tools(name):
    assert not voice_command.voice_blocked(name)


def test_no_model_means_none(ran):
    body = post("tell me a story about dragons", use_model=False)
    assert body == {**body, "handled_by": "none", "reply": "", "calls": []}


def test_model_answer_is_spoken_short(monkeypatch, ran):
    seen = {}

    def fake_agent(text, deadline, allow):
        seen["allow_shell"] = allow("run_command")
        seen["allow_volume"] = allow("set_volume")
        return "Dragons are **big**. They fly. They also hoard gold. The end.", []

    monkeypatch.setattr(web_app, "_voice_agent", fake_agent)
    body = post("tell me a story about dragons")
    assert body["handled_by"] == "jan"
    assert body["reply"] == "Dragons are big. They fly."
    assert seen == {"allow_shell": False, "allow_volume": True}


def test_empty_text_is_400():
    answer = client.post("/api/voice/command", json={"text": " "}, headers=FORGE)
    assert answer.status_code == 400


def test_no_forge_header_is_403(ran):
    answer = client.post("/api/voice/command", json={"text": "volume 40"})
    assert answer.status_code == 403
    assert ran == []


def test_source_cannot_lift_the_voice_guard(ran):
    body = post("close this tab", source="chat")
    assert ran == []
    assert "confirm it in Acchan" in body["reply"]


def test_launch_app_quotes_arguments(monkeypatch):
    ran = []
    monkeypatch.setattr(apps, "find_app", lambda name, **kw: None)
    monkeypatch.setattr(apps.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(apps, "hypr_exec", ran.append)
    apps.launch_app("mpv", "song.mp3; rm -rf ~")
    assert ran == ["mpv 'song.mp3; rm -rf ~'"]
    apps.launch_app("mpv")
    assert ran[-1] == "mpv"


def test_speech_uses_shared_service_then_falls_back(monkeypatch):
    from acchan import voice

    sent = []

    def service(path, data, kind):
        sent.append((path, kind))
        return b"RIFF-from-service"

    monkeypatch.setattr(voice, "_service", service)
    monkeypatch.setattr(voice, "_speak_local", lambda words, v: b"RIFF-local")
    assert voice.speak("Opened Firefox.") == b"RIFF-from-service"
    assert sent == [("/api/tts", "application/json")]
    monkeypatch.setattr(voice, "_service", lambda *a: None)
    assert voice.speak("Opened Firefox.") == b"RIFF-local"


def test_listening_uses_shared_service_then_falls_back(monkeypatch):
    from acchan import voice

    monkeypatch.setattr(voice, "_service", lambda *a: b'{"text": " open  steam "}')
    monkeypatch.setattr(voice, "_transcribe_local", lambda audio, suffix: "local")
    assert voice.transcribe(b"audio", ".wav") == "open steam"
    monkeypatch.setattr(voice, "_service", lambda *a: None)
    assert voice.transcribe(b"audio", ".wav") == "local"


def test_foreign_host_is_403(ran):
    headers = {**FORGE, "Host": "rebind.example:8451"}
    answer = client.post(
        "/api/voice/command", json={"text": "volume 40"}, headers=headers
    )
    assert answer.status_code == 403
    assert ran == []


def test_voice_never_starts_programs_from_path(monkeypatch, ran):
    monkeypatch.setattr(apps, "find_app", lambda query, strict=False: None)
    for text in ("start reboot", "open poweroff", "launch shutdown", "start yes"):
        body = post(text)
        assert "no installed app" in body["reply"], (text, body)
    assert ran == []


def test_voice_refuses_power_desktop_entries(monkeypatch):
    entry = {"name": "Power Off", "exec": "systemctl poweroff", "categories": ""}
    monkeypatch.setattr(apps, "find_app", lambda query, strict=False: entry)
    assert voice_command.launch_refusal({"name": "power off"})


def test_voice_launches_installed_apps(monkeypatch, ran):
    entry = {"name": "Firefox", "exec": "firefox %u", "categories": "WebBrowser;"}
    monkeypatch.setattr(apps, "find_app", lambda query, strict=False: entry)
    post("start firefox")
    assert [name for name, _ in ran] == ["launch_app"]


def test_model_from_voice_cannot_launch_or_open(monkeypatch, ran):
    allowed = {}

    def agent(text, deadline, allow):
        names = ("launch_app", "open_item", "open_terminal", "terminal_new_tab")
        allowed.update({n: allow(n) for n in names + ("weather",)})
        return "Fine.", []

    monkeypatch.setattr(web_app, "_voice_agent", agent)
    post("tell me something nice about otters")
    assert allowed == {
        "launch_app": False,
        "open_item": False,
        "open_terminal": False,
        "terminal_new_tab": False,
        "weather": True,
    }


@pytest.mark.parametrize("name", ["open_terminal", "terminal_new_tab"])
def test_spoken_terminal_only_without_a_command(name):
    assert voice_command.voice_refusal(name, {"command": "reboot"})
    assert voice_command.voice_refusal(name, {"command": "  "}) is None
    assert voice_command.voice_refusal(name, {}) is None


def test_the_voice_agent_never_saves_a_picture_over_a_file(tmp_path):
    """The model picking take_screenshot for a spoken request gets the same
    argument check as the fast path and phrases; nothing is grabbed."""
    notes = tmp_path / "notes.md"
    notes.write_text("mine")
    agent = web_app._VoiceAgent.__new__(web_app._VoiceAgent)
    agent.allow = staticmethod(voice_command.voice_agent_allowed)
    args = json.dumps({"path": str(notes)})
    ok, said = agent._run_tool("take_screenshot", args, "small")
    refused = voice_command.NO_OVERWRITE.format(kind="file", name="notes.md")
    assert (ok, said) == (False, refused)
    assert notes.read_text() == "mine"
    assert agent._run_tool("run_command", "{}", "small") == (
        False,
        voice_command.CONFIRM,
    )
