"""engines/audio_cpp.py against a stand-in server (tests/fake_audiocpp_server.py)."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest

from conftest import tone_wav

FAKE = Path(__file__).with_name("fake_audiocpp_server.py")
AUK_PROMPT = 'Say the following with the same voice: "{text}"'


def make_profile(home: Path, pid: str, language: str, moods=("calm",), **extra):
    d = home / pid
    d.mkdir(parents=True)
    clips = {}
    for m in moods:
        tone_wav(d / f"{m}.wav")
        clips[m] = {"wav": f"{m}.wav", "text": f"{m} words"}
    (d / "profile.json").write_text(
        json.dumps(dict(extra, language=language, clips=clips))
    )
    return d


@pytest.fixture
def ac(env, tmp_path, monkeypatch):
    """An AuK-like row, its files and a log of what the server was asked."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("FAKE_AC_LOG", str(tmp_path / "fake.log"))
    model = tmp_path / "models" / "voice" / "tts" / "auk"
    model.mkdir(parents=True)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    server = tmp_path / "audiocpp_server"  # argv[1] is this path, as for a script
    server.write_text(f"#!{sys.executable}\n" + FAKE.read_text().split("\n", 1)[1])
    server.chmod(0o755)
    home = tmp_path / "models" / "voice" / "profiles"
    make_profile(home, "harbour", "en", ("calm", "angry"))
    make_profile(home, "lena-ja", "ja")
    row: dict = {
        "id": "auk-test",
        "kind": "tts",
        "engine": "audio_cpp",
        "family": "auk",
        "task": "tts",
        "tasks": {"edit": "gen"},
        "session_options": {"auk.variant": "flash"},
        "expressive": "auk",
        "languages": ["en"],
        "prompt": AUK_PROMPT,
        "duration": "estimate",
        "default_voice": "harbour",
        "load_timeout_s": 20,
    }
    files = {"model": model, "server": server, "runtime": runtime, "profiles": home}
    return row, files, tmp_path / "fake.log"


def asked(log: Path) -> list[dict]:
    return [json.loads(x) for x in log.read_text().splitlines()]


def test_load_speaks_with_the_mood_clip_and_stops(ac):
    from engines import audio_cpp

    row, files, log = ac
    eng = audio_cpp.Engine(row, files, 3)
    try:
        assert eng.voices() == ["harbour"]  # the ja profile is not this row's
        audio, rate = eng.synthesize('[angry] I said "fall back" (sighs)', "", 1.0)
        assert rate == 24000 and audio.dtype == np.float32 and len(audio) > 0
        start, req = asked(log)[0], asked(log)[1]
        assert start["cwd"] == str(files["runtime"])
        cfg = start["config"]
        assert cfg["host"] == "127.0.0.1" and cfg["threads"] == 3
        assert cfg["lazy_load"] is True and cfg["max_loaded_models"] == 1
        assert [(m["id"], m["task"]) for m in cfg["models"]] == [
            ("speak", "tts"),
            ("edit", "gen"),
        ]
        assert cfg["models"][0]["session_options"] == {"auk.variant": "flash"}
        body = req["body"]
        assert (
            body["input"]
            == "Say the following with the same voice: \"I said 'fall back'\""
        )
        assert body["voice_ref"]["path"].endswith("harbour/angry.wav")
        assert "reference_text" not in body  # only rows with ref_text: true
        assert body["options"]["duration_sec"] == pytest.approx(0.38 * 4 + 0.5)
        proc = eng.proc
        assert proc is not None
        assert eng.pidfile.name == f"auk-test@{os.getpid()}.pid"
        assert eng.pidfile.read_text().split() == [str(proc.pid), str(os.getpid())]
    finally:
        eng.close()
    assert proc.poll() is not None
    assert not eng.pidfile.exists() and not eng.config.exists()
    eng.close()  # twice is fine


def test_mood_without_a_clip_and_unknown_voice_use_calm_default(ac):
    from engines import InputError, audio_cpp

    row, files, log = ac
    eng = audio_cpp.Engine(row, files, 2)
    try:
        body = eng.request("[whisper] quiet now", "nobody", 2.0)
        assert body["voice_ref"]["path"].endswith("harbour/calm.wav")
        assert body["input"].endswith('"quiet now"')
        assert body["options"]["duration_sec"] == pytest.approx((0.38 * 2 + 0.5) / 2)
        assert eng.used_voice == "harbour"
        with pytest.raises(InputError, match="nothing to say"):
            eng.request("[laughs]", "harbour", 1.0)
    finally:
        eng.close()


def test_irodori_style_speed_and_ref_text(ac):
    from engines import audio_cpp

    row, files, log = ac
    iro: dict = dict(row, id="iro-test", family="irodori_tts", task="clon", tasks={})
    iro.update(expressive="irodori", languages=["ja"], default_voice="lena-ja")
    iro.update(prompt=None, duration=None, ref_text=True, options={"language": "ja"})
    iro.update(speed_option="duration_scale", speed_invert=True, seed=7)
    eng = audio_cpp.Engine(iro, files, 2)
    try:
        assert eng.voices() == ["lena-ja"]
        body = eng.request("[angry] 下がれ。[sigh]", "", 1.25)
        assert body["input"] == "😠下がれ。😮‍💨"
        assert body["voice_ref"]["path"].endswith("lena-ja/calm.wav")
        assert body["reference_text"] == "calm words"
        assert body["options"] == {"language": "ja", "duration_scale": 0.8}
        assert body["seed"] == 7
        assert "duration_scale" not in eng.request("下がれ", "", 1.0)["options"]
    finally:
        eng.close()


def test_no_profile_for_the_language_says_so(ac):
    from engines import audio_cpp

    row, files, log = ac
    eng = audio_cpp.Engine(dict(row, languages=["fr"]), files, 2)
    try:
        assert eng.voices() == []
        with pytest.raises(RuntimeError, match="no voice profile in fr"):
            eng.synthesize("bonjour", "", 1.0)
    finally:
        eng.close()


def test_empty_audio_is_an_error_and_json_audio_is_read(ac, monkeypatch):
    from engines import audio_cpp

    row, files, log = ac
    monkeypatch.setenv("FAKE_AC_MODE", "empty")
    eng = audio_cpp.Engine(row, files, 2)
    try:
        with pytest.raises(RuntimeError, match="made no audio"):
            eng.synthesize("hello there", "harbour", 1.0)
    finally:
        eng.close()
    monkeypatch.setenv("FAKE_AC_MODE", "json")
    eng = audio_cpp.Engine(row, files, 2)
    try:
        audio, rate = eng.synthesize("hello there", "harbour", 1.0)
        assert rate == 24000 and len(audio) == 2400 * 9  # nine words with the prompt
    finally:
        eng.close()


def test_edit_and_design_for_profiles(ac, tmp_path):
    from engines import audio_cpp

    row, files, log = ac
    row = dict(row, design_option="instruct")
    eng = audio_cpp.Engine(row, files, 2)
    try:
        src = files["profiles"] / "harbour" / "calm.wav"
        out = eng.edit(src, "Change the emotion to sad.", tmp_path / "sad.wav")
        assert out.exists() and out.stat().st_size > 1000
        eng.design("Hello there.", "a calm young woman", tmp_path / "d.wav")
        reqs = [r for r in asked(log) if "path" in r]
        assert reqs[0]["path"] == "/v1/tasks/run"
        assert reqs[0]["body"]["model"] == "edit"
        assert reqs[0]["body"]["request"] == {
            "text": "Change the emotion to sad.",
            "audio": str(src),
        }
        d = reqs[1]["body"]
        assert d["model"] == "speak" and "voice_ref" not in d
        assert d["options"]["instruct"] == "a calm young woman"
        assert d["options"]["duration_sec"] == pytest.approx(0.38 * 2 + 0.5)
    finally:
        eng.close()
    with pytest.raises(RuntimeError, match="no edit task"):
        e2 = audio_cpp.Engine(dict(row, tasks={}), files, 2)
        try:
            e2.edit(src, "x", tmp_path / "x.wav")
        finally:
            e2.close()


def test_a_server_that_dies_says_why(ac, monkeypatch):
    from engines import audio_cpp

    row, files, log = ac
    monkeypatch.setenv("FAKE_AC_MODE", "die")
    with pytest.raises(RuntimeError, match="failed to load model"):
        audio_cpp.Engine(row, files, 2)
    sd = Path(os.environ["XDG_CACHE_HOME"]) / "forge" / "voice"
    assert not list(sd.glob("auk-test@*.pid"))


def test_a_server_left_by_a_dead_backend_is_stopped(ac):
    from engines import audio_cpp

    row, files, log = ac
    cfg = files["server"].parent / "left.json"
    cfg.write_text(json.dumps({"port": audio_cpp.free_port(), "models": []}))
    left = subprocess.Popen(
        [str(files["server"]), "--config", str(cfg), "--no-ui"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(0.5)
        assert left.poll() is None  # a live server, so stopping it proves something
        sd = Path(os.environ["XDG_CACHE_HOME"]) / "forge" / "voice"
        sd.mkdir(parents=True, exist_ok=True)
        pf = sd / "auk-test@999999.pid"
        pf.write_text(f"{left.pid} 999999\n")
        audio_cpp.clear_stale(row, files)
        end = time.monotonic() + 5
        while left.poll() is None and time.monotonic() < end:
            time.sleep(0.1)
        assert left.poll() is not None and not pf.exists()
    finally:
        if left.poll() is None:
            left.kill()
        left.wait()


def test_estimate_and_decode_helpers():
    from engines import audio_cpp

    assert audio_cpp.estimate_seconds("one two three") == pytest.approx(1.64)
    assert audio_cpp.estimate_seconds("下がれ") == pytest.approx(0.95)
    assert audio_cpp.estimate_seconds("x", {"seconds_per_word": 1}) == pytest.approx(
        1.5
    )
    import engines

    a, rate = audio_cpp.decode_audio(
        engines.wav_bytes(np.full(100, 0.5, np.float32), 16000)
    )
    assert rate == 16000 and len(a) == 100 and abs(a[0] - 0.5) < 0.001


def test_an_answer_without_audio_says_so():
    from engines.audio_cpp import decode_audio

    with pytest.raises(RuntimeError, match="no audio"):
        decode_audio(b'{"error": "model busy"}')
