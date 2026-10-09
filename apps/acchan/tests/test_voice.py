"""Acchan's voice (Emerson, 2026-09-27: "make the Jan in Acchan have TTS and
STT using stuff I already have"). These run the real engines already on the
laptop: Kokoro speaks, whisper.cpp listens, so the round trip is checked end
to end with no microphone. Skipped where an engine is missing."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acchan import settings, voice  # noqa: E402

ready = voice.status()
needs_both = pytest.mark.skipif(
    not (ready["speak"] and ready["listen"]), reason=f"voice engines: {ready}"
)


def test_code_and_markup_are_not_read_aloud():
    reply = (
        "## Done\nRun **this**:\n```bash\nls -la ~/Projects\n```\n"
        "See [the docs](https://example.com/x) or https://example.com/y and `git status`."
    )
    said = voice.speech_text(reply)
    assert "ls -la" not in said and "```" not in said and "**" not in said
    assert "the docs" in said and "https://" not in said and "git status" in said
    assert "code" in said.lower()  # says that there was code, instead of reading it
    assert len(voice.speech_text("word " * 2000)) <= voice.MAX_SPOKEN


def test_voice_settings_default_to_quiet():
    assert settings.DEFAULTS["speak"] is False
    assert settings.DEFAULTS["voice"] in voice.VOICES


def test_it_uses_what_is_already_installed():
    # nothing downloaded: every engine path points into existing installs
    for path in (voice.KOKORO_SCRIPT, voice.WHISPER_CLI, voice.WHISPER_MODEL):
        assert "Forge" in str(path) or ".var/app" in str(path), path


@needs_both
def test_what_it_says_it_can_hear_back():
    wav = voice.speak("Open a terminal and list my projects folder.")
    assert wav[:4] == b"RIFF" and len(wav) > 20000
    # base.en writes "project's" where tiny.en wrote "projects": same words
    heard = voice.transcribe(wav, ".wav").lower().replace("'", "")
    for word in ("terminal", "projects", "folder"):
        assert word in heard, heard


@needs_both
def test_the_web_routes_speak_and_listen():
    from fastapi.testclient import TestClient

    import web_app

    client = TestClient(web_app.app)
    assert client.get("/api/voice/status").json()["listen"] is True
    said = client.post("/api/voice/speak", json={"text": "Hello from Acchan."})
    assert said.status_code == 200 and said.headers["content-type"] == "audio/wav"
    heard = client.post(
        "/api/voice/listen",
        content=said.content,
        headers={"Content-Type": "audio/wav"},
    )
    assert heard.status_code == 200 and "hello" in heard.json()["text"].lower()
    assert client.post("/api/voice/speak", json={"text": "  "}).status_code == 400
