"""Edge cases the task 120 critic found in cloned voices and mood tags: a line
of tags only, a voice another row owns, a missing profiles folder, a lost
Breeze copy, a Japanese line with no Japanese fall-back, words in round
brackets, a broken tag file and what /api/say reports. Fake audio.cpp and
Breeze servers only, no real model."""

import json
import shutil
import sys
from pathlib import Path

import pytest

from conftest import FakeEngine, tone_wav

TESTS = Path(__file__).resolve().parent


def script(path: Path, src: Path) -> Path:
    path.write_text(f"#!{sys.executable}\n" + src.read_text().split("\n", 1)[1])
    path.chmod(0o755)
    return path


def profile(home: Path, pid: str, lang: str, text="calm words") -> Path:
    d = home / pid
    d.mkdir(parents=True)
    tone_wav(d / "calm.wav")
    clips = {"calm": {"wav": "calm.wav", "text": text}}
    (d / "profile.json").write_text(json.dumps({"language": lang, "clips": clips}))
    return d


@pytest.fixture
def heavy(env, client, monkeypatch, tmp_path):
    import engines
    import service
    import web_app

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setattr(service, "mem_available_mb", lambda: 64000)
    monkeypatch.setattr(service, "jan_busy", lambda: False)
    web_app.voice.models.loader = lambda row, files, t: (
        FakeEngine(row, files, t)
        if row.get("engine") == "fake"
        else engines.load(row, files, t)
    )
    home = tmp_path / "profiles"
    profile(home, "harbour", "en")
    profile(home, "lena-ja", "ja")
    model = tmp_path / "m.gguf"
    model.write_bytes(b"x")
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    ac = script(tmp_path / "audiocpp_server", TESTS / "fake_audiocpp_server.py")
    bdir = tmp_path / "breeze"
    bdir.mkdir()
    (bdir / "m.gguf").write_bytes(b"g")
    tone_wav(bdir / "ref.wav")
    br = script(tmp_path / "breeze-server", TESTS / "fake_breeze_server.py")
    ac_files = {
        "model": str(model),
        "server": str(ac),
        "runtime": str(runtime),
        "profiles": str(home),
    }
    common = {"kind": "tts", "heavy": True, "load_timeout_s": 20}
    rows = [
        dict(
            common,
            id="iro-test",
            engine="audio_cpp",
            family="irodori_tts",
            task="clon",
            expressive="irodori",
            languages=["ja"],
            default_voice="lena-ja",
            files=ac_files,
        ),
        dict(
            common,
            id="auk-test",
            engine="audio_cpp",
            family="auk",
            task="tts",
            expressive="auk",
            languages=["en"],
            default_voice="harbour",
            files=ac_files,
        ),
        dict(
            common,
            id="breeze-test",
            engine="breeze_cpp",
            expressive="breeze",
            languages=["en"],
            default_voice="harbour",
            voices=["harbour"],
            ref_text="The harbour lights.",
            files={
                "model": str(bdir / "m.gguf"),
                "ref": str(bdir / "ref.wav"),
                "server": str(br),
                "profiles": str(home),
            },
        ),
    ]
    reg = json.loads((env / "reg.json").read_text())
    reg["models"] += rows
    (env / "reg.json").write_text(json.dumps(reg))
    yield web_app, home
    web_app.voice.models.unload()


def logged(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines()]


@pytest.mark.parametrize(
    "model,first,text",
    [
        ("iro-test", "こんにちは", "[laugh]"),
        ("auk-test", "Hello there", "(laughs)"),
        ("breeze-test", "Hello there", "[angry]"),
    ],
)
def test_a_line_of_tags_only_keeps_the_heavy_model_loaded(
    heavy, client, model, first, text
):
    web_app, _ = heavy
    assert client.post("/api/tts", json={"text": first, "model": model}).is_success
    proc = web_app.voice.models._loaded[model].proc
    r = client.post("/api/tts", json={"text": text, "model": model})
    assert r.status_code == 400 and "nothing to say" in r.text
    assert web_app.voice.models.is_loaded(model) and proc.poll() is None


def test_a_line_the_engine_cannot_say_keeps_it_loaded(heavy, client):
    """The engine's own input error (a profile whose calm clip has no words)
    answers 400 without unloading or falling back."""
    web_app, home = heavy
    profile(home, "mute", "en", text="")
    assert client.post("/api/tts", json={"text": "Hi.", "model": "breeze-test"})
    proc = web_app.voice.models._loaded["breeze-test"].proc
    r = client.post(
        "/api/tts", json={"text": "Hi.", "model": "breeze-test", "voice": "mute"}
    )
    assert r.status_code == 400 and "no words" in r.text
    assert web_app.voice.models.is_loaded("breeze-test") and proc.poll() is None


def test_a_cloning_row_speaks_only_its_own_voices_and_says_which(
    heavy, client, tmp_path, monkeypatch
):
    monkeypatch.setenv("FAKE_AC_LOG", str(tmp_path / "fake.log"))
    for asked in ("lena-ja", "nobody"):  # Japanese profile on English AuK; unknown
        r = client.post(
            "/api/tts",
            json={"text": "Hello there", "model": "auk-test", "voice": asked},
        )
        assert r.status_code == 200 and r.headers["x-voice-voice"] == "harbour"
        body = [e["body"] for e in logged(tmp_path / "fake.log") if "body" in e][-1]
        assert body["voice_ref"]["path"].endswith("harbour/calm.wav")


def test_breeze_loads_without_the_profiles_folder(heavy, client, tmp_path):
    _, home = heavy
    shutil.move(str(home), str(tmp_path / "profiles-moved"))
    r = client.post("/api/tts", json={"text": "Hello there", "model": "breeze-test"})
    assert r.status_code == 200 and r.headers["x-voice-model"] == "breeze-test"
    assert "x-voice-fell-back" not in r.headers


def test_a_lost_breeze_copy_of_a_profile_is_saved_again(
    heavy, client, tmp_path, monkeypatch
):
    log = tmp_path / "breeze.log"
    monkeypatch.setenv("FAKE_BREEZE_LOG", str(log))
    _, home = heavy
    profile(home, "lena", "en", text="Handler One to all units.")
    ask = {"text": "Fall back.", "model": "breeze-test", "voice": "lena"}
    assert client.post("/api/tts", json=ask).status_code == 200
    for copy in (tmp_path / "breeze" / "voices").glob("p-lena-*.breeze"):
        copy.unlink()  # gone on the server side
    r = client.post("/api/tts", json=ask)
    assert r.status_code == 200 and r.headers["x-voice-voice"] == "lena"
    sent = [e["speech"]["voice_id"] for e in logged(log) if "speech" in e]
    assert sent[-1].startswith("p-lena-")  # not the default voice "harbour"


def test_a_japanese_line_never_falls_back_to_an_english_voice(
    heavy, client, monkeypatch
):
    import service

    monkeypatch.setattr(service, "mem_available_mb", lambda: 100)
    r = client.post("/api/tts", json={"text": "[angry]こんにちは", "model": "iro-test"})
    assert r.status_code == 503
    assert "free memory" in r.text and "does not speak ja" in r.text
    assert not [c for c in FakeEngine.calls if c[0] == "tts"]


def test_a_profile_name_is_not_sent_to_a_plain_voice(heavy, client):
    r = client.post("/api/tts", json={"text": "hi", "voice": "harbour"})
    assert r.status_code == 200 and r.headers["x-voice-voice"] == "a"
    assert FakeEngine.calls[-1][2] == "a"


def test_plain_voices_keep_words_in_round_brackets(client):
    text = "Set the (normal) level. (laughs) Volume (silence) please, (quietly)."
    assert client.post("/api/tts", json={"text": text}).status_code == 200
    said = FakeEngine.calls[-1][1]
    for word in ("(normal)", "(silence)", "(quietly)"):
        assert word in said
    assert "laugh" not in said


def test_a_broken_tag_file_keeps_every_voice_speaking(client, tmp_path, monkeypatch):
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "voice_emotions.json").write_text('{"tags": {"calm": {"kind": "x",}}}')
    monkeypatch.setenv("FORGE_SHARED_DIR", str(shared))
    for text in ("See the note (above). [sigh]", "No brackets here."):
        assert client.post("/api/tts", json={"text": text}).status_code == 200
    assert "sigh" not in FakeEngine.calls[-2][1]  # the last good tags still apply


def test_say_reports_the_model_and_voice_that_spoke(heavy, client, monkeypatch):
    import service

    r = client.post("/api/say", json={"text": "Hello there", "model": "auk-test"})
    assert r.json()["model"] == "auk-test" and r.json()["voice"] == "harbour"
    assert r.json()["fell_back"] is None
    client.post("/api/unload")
    monkeypatch.setattr(service, "mem_available_mb", lambda: 100)
    r = client.post("/api/say", json={"text": "Hello there", "model": "auk-test"})
    assert r.status_code == 200 and r.json()["model"] == "fake-tts"
    assert r.json()["voice"] == "a" and "free memory" in r.json()["fell_back"]


@pytest.mark.parametrize("text", ["[angry]\nI told you", "[sad](sigh) I told you"])
def test_tags_survive_the_markdown_clean_up(client, text):
    assert client.post("/api/tts", json={"text": text}).status_code == 200
    said = FakeEngine.calls[-1][1]
    assert said.startswith("I told you")
    for word in ("angry", "sad", "sigh"):
        assert word not in said


@pytest.mark.parametrize(
    "text, said",
    [
        ("Read the [plain](https://example.com/guide) notes.", "Read the plain notes."),
        ("Press [Pause](https://example.com/p) to stop.", "Press Pause to stop."),
    ],
)
def test_a_link_whose_words_are_a_tag_stays_a_link(client, text, said):
    assert client.post("/api/tts", json={"text": text}).status_code == 200
    assert FakeEngine.calls[-1][1] == said


@pytest.mark.parametrize(
    "text, said",
    [
        ("[angry]\n# Alert\nStay put.", "Alert. Stay put."),
        ("[sad]\n- first\n- second", "first. second."),
    ],
)
def test_a_tag_line_keeps_the_markdown_under_it(client, text, said):
    assert client.post("/api/tts", json={"text": text}).status_code == 200
    assert FakeEngine.calls[-1][1] == said


@pytest.mark.parametrize(
    "bad",
    [
        '{"tags": {}, "styles": []}',
        '{"tags": {}}',
        "[1, 2]",
        '{"tags": {}, "styles": {"plain": {"map": []}}}',
    ],
)
def test_a_tag_file_of_the_wrong_shape_keeps_every_voice_speaking(
    client, tmp_path, monkeypatch, bad
):
    assert client.post("/api/tts", json={"text": "Warm up. [sigh]"}).status_code == 200
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "voice_emotions.json").write_text(bad)
    monkeypatch.setenv("FORGE_SHARED_DIR", str(shared))
    r = client.post("/api/tts", json={"text": "See the note (above). [sigh]"})
    assert r.status_code == 200 and "sigh" not in FakeEngine.calls[-1][1]


def test_a_cloning_row_with_no_voice_falls_back_without_loading(
    heavy, client, tmp_path
):
    web_app, home = heavy
    shutil.move(str(home), str(tmp_path / "moved"))
    loads = []
    first = web_app.voice.models.loader
    web_app.voice.models.loader = lambda row, files, t: (
        loads.append(row["id"]) or first(row, files, t)
    )
    for _ in range(2):
        r = client.post("/api/tts", json={"text": "Hello there", "model": "auk-test"})
        assert (
            r.status_code == 200
            and "has no voice in en" in r.headers["x-voice-fell-back"]
        )
    r = client.post("/api/tts", json={"text": "こんにちは", "model": "iro-test"})
    assert r.status_code == 503 and "has no voice in ja" in r.text
    assert "auk-test" not in loads and "iro-test" not in loads


def test_a_loaded_japanese_voice_speaks_while_jan_is_busy(heavy, client, monkeypatch):
    import service

    web_app, _ = heavy
    assert client.post(
        "/api/tts", json={"text": "こんにちは", "model": "iro-test"}
    ).is_success
    monkeypatch.setattr(service, "jan_busy", lambda: True)
    r = client.post("/api/tts", json={"text": "こんにちは", "model": "iro-test"})
    assert r.status_code == 200 and r.headers["x-voice-model"] == "iro-test"
    web_app.voice.models.unload()  # not loaded: it waits for Jan, with the reason
    r = client.post("/api/tts", json={"text": "こんにちは", "model": "iro-test"})
    assert r.status_code == 503 and "Jan is busy" in r.text
