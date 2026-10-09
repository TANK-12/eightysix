import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_VOICE_SETTINGS", str(tmp_path / "voice.json"))
    monkeypatch.setenv("FORGE_VOICE_PLAYER", "true")
    monkeypatch.setenv("FORGE_ACCHAN_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("FORGE_CLAUDE_URL", "http://127.0.0.1:9")
    home = tmp_path / "models"
    for rel in ("voice/stt/fake/m.bin", "voice/tts/fake/m.onnx"):
        (home / rel).parent.mkdir(parents=True, exist_ok=True)
        (home / rel).write_bytes(b"x")
    monkeypatch.setenv("FORGE_MODELS_DIR", str(home))
    reg = {
        "models": [
            {
                "id": "fake-stt",
                "kind": "stt",
                "label": "Fake STT",
                "engine": "fake",
                "tier": "fast",
                "files": {"model": "voice/stt/fake/m.bin"},
            },
            {
                "id": "fake-tts",
                "kind": "tts",
                "label": "Fake TTS",
                "engine": "fake",
                "tier": "fast",
                "files": {"model": "voice/tts/fake/m.onnx"},
                "voices": ["a", "b"],
                "default_voice": "a",
            },
            {
                "id": "gone-tts",
                "kind": "tts",
                "label": "Gone",
                "engine": "fake",
                "files": {"model": "voice/tts/gone/x.onnx"},
            },
        ],
        "defaults": {"stt": "fake-stt", "tts": "fake-tts", "tts_best": "fake-tts"},
        "wake": {"claude": ["claude", "tetsu"], "jan": ["jan", "acchan"]},
    }
    (tmp_path / "reg.json").write_text(json.dumps(reg))
    monkeypatch.setenv("FORGE_VOICE_REGISTRY", str(tmp_path / "reg.json"))
    yield tmp_path


class FakeEngine:
    heard = "hello there"
    calls: list = []

    def __init__(self, row, files, threads):
        self.row = row

    def transcribe(self, audio):
        FakeEngine.calls.append(("stt", len(audio)))
        return FakeEngine.heard

    def voices(self):
        return ["a", "b"]

    def synthesize(self, text, voice, speed):
        import numpy as np

        FakeEngine.calls.append(("tts", text, voice, speed))
        return np.zeros(24000, dtype=np.float32), 24000

    def close(self):
        pass


@pytest.fixture
def client(env):
    from fastapi.testclient import TestClient

    import web_app

    web_app.voice = web_app.service.Voice()
    web_app.voice.models.loader = FakeEngine
    FakeEngine.calls = []
    FakeEngine.heard = "hello there"
    c = TestClient(web_app.app, base_url="http://127.0.0.1:8467")
    c.headers["X-Forge"] = "1"
    return c


def tone_wav(path, seconds=1.0, loud=(0.3, 0.8)):
    """A wav: quiet, a loud tone between loud[0]..loud[1] s, then quiet."""
    import numpy as np

    import engines

    t = np.arange(int(16000 * seconds)) / 16000
    a = np.zeros_like(t, dtype=np.float32)
    m = (t >= loud[0]) & (t < loud[1])
    a[m] = 0.3 * np.sin(2 * np.pi * 440 * t[m])
    Path(path).write_bytes(engines.wav_bytes(a, 16000))
    return path
