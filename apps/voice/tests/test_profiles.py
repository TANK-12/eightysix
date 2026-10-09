"""Voice profiles: folders under models/voice/profiles/ with a calm clip and
mood clips, listed as the voices of a cloning model row."""

import json
import math
import struct
import wave

import pytest

import expressive
import profiles


def tone(path, seconds=0.3, rate=16000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        n = int(seconds * rate)
        w.writeframes(
            b"".join(struct.pack("<h", int(8000 * math.sin(i / 8))) for i in range(n))
        )
    return path


def make(home, pid, lang="en", clips=("calm",), extra=None):
    d = home / pid
    d.mkdir(parents=True)
    meta = {"language": lang, "clips": {}}
    for m in clips:
        tone(d / f"{m}.wav")
        meta["clips"][m] = {"wav": f"{m}.wav", "text": f"{m} words"}
    meta.update(extra or {})
    (d / "profile.json").write_text(json.dumps(meta))
    return d


def test_load_skips_bad_folders(tmp_path):
    make(tmp_path, "good", clips=("calm", "angry"))
    make(tmp_path, "nocalm", clips=("angry",))
    make(tmp_path, "Bad Name")
    make(tmp_path, "escape", extra={"clips": {"calm": {"wav": "../good/calm.wav"}}})
    (make(tmp_path, "badjson") / "profile.json").write_text("{")
    found = profiles.load(tmp_path)
    assert list(found) == ["good"]
    assert found["good"]["clips"]["angry"]["wav"] == tmp_path / "good" / "angry.wav"
    assert profiles.load(tmp_path / "missing") == {} and profiles.load(None) == {}


def test_languages_and_clip_for_a_mood(tmp_path):
    make(tmp_path, "en1", clips=("calm", "sad"))
    make(tmp_path, "ja1", lang="ja")
    found = profiles.load(tmp_path)
    assert list(profiles.for_languages(found, ["ja"])) == ["ja1"]
    assert profiles.for_languages(found, []) == found
    wav, words = profiles.clip(found["en1"], "sad")
    assert wav.name == "sad.wav" and words == "sad words"
    assert profiles.clip(found["en1"], "angry")[0].name == "calm.wav"
    assert profiles.clip(found["en1"], None)[0].name == "calm.wav"


def test_save_clip_calm_first_then_moods(tmp_path):
    src = tone(tmp_path / "src.wav", rate=44100)
    home = tmp_path / "profiles"
    with pytest.raises(ValueError):
        profiles.save_clip(home, "lena", "angry", src, "x")
    for bad in ("Lena", "../x", ""):
        with pytest.raises(ValueError):
            profiles.save_clip(home, bad, "calm", src, "x")
    with pytest.raises(ValueError):
        profiles.save_clip(home, "lena", "Angry!", src, "x")
    profiles.save_clip(home, "lena", "calm", src, "Hello.", language="en", private=True)
    profiles.save_clip(home, "lena", "angry", src, "Hello!")
    p = profiles.load(home)["lena"]
    assert sorted(p["clips"]) == ["angry", "calm"] and p["private"] is True
    with wave.open(str(p["clips"]["calm"]["wav"])) as w:
        assert w.getframerate() == profiles.RATE and w.getnchannels() == 1
    saved = json.loads((home / "lena" / "profile.json").read_text())
    assert saved["clips"]["angry"] == {"wav": "angry.wav", "text": "Hello!"}
    assert "dir" not in saved and "id" not in saved


def test_mood_list_per_style():
    tags = expressive.vocab()["tags"]
    auk = profiles.mood_list(expressive.style("auk"), tags)
    assert "calm" not in auk and {"angry", "sad", "whisper"} <= set(auk)
    iro = profiles.mood_list(expressive.style("irodori"), tags)
    assert "angry" in iro and "laugh" not in iro and "pause" not in iro


def test_registry_lists_profiles_as_voices(client, env):
    home = env / "models"
    make(home / "voice" / "profiles", "harbour")
    make(home / "voice" / "profiles", "handler-ja", lang="ja")
    reg = json.loads((env / "reg.json").read_text())
    row = dict(reg["models"][1], id="clone-tts", languages=["en"], voices=None)
    row["files"] = dict(row["files"], profiles="voice/profiles")
    reg["models"].append(row)
    (env / "reg.json").write_text(json.dumps(reg))
    models = {m["id"]: m for m in client.get("/api/registry").json()["models"]}
    assert models["clone-tts"]["voices"] == ["harbour"]
    assert models["fake-tts"]["voices"] == ["a", "b"]


def test_row_voices_keeps_named_voices_beside_profiles(env):
    import service

    home = env / "models"
    make(home / "voice" / "profiles", "lena")
    make(home / "voice" / "profiles", "shin-ja", lang="ja")
    (home / "voice" / "m.gguf").write_bytes(b"gguf")
    row = {
        "id": "breeze",
        "kind": "tts",
        "voices": ["harbour"],
        "languages": ["en"],
        "files": {"model": "voice/m.gguf", "profiles": "voice/profiles"},
    }
    assert service.row_voices(row) == ["harbour", "lena"]
    assert service.model_present(row)
    gone = dict(row, files=dict(row["files"], profiles="voice/nowhere"))
    assert service.row_voices(gone) == ["harbour"] and service.model_present(gone)
    assert not service.model_present(dict(row, files={"model": "voice/none.gguf"}))


def test_a_new_calm_clip_sets_the_old_voice_aside(tmp_path):
    home = tmp_path / "p"
    src = tone(tmp_path / "a.wav")
    profiles.save_clip(home, "lena", "calm", src, "old words", language="en")
    profiles.save_clip(home, "lena", "angry", src, "angry words")
    new = tone(tmp_path / "b.wav", seconds=0.5)
    profiles.save_clip(home, "lena", "calm", new, "new words")
    p = profiles.load(home)["lena"]
    assert {m: c["text"] for m, c in p["clips"].items()} == {"calm": "new words"}
    assert p["language"] == "en"
    old = [d for d in (home / "lena").iterdir() if d.name.startswith("old-")]
    assert len(old) == 1
    kept = sorted(f.name for f in old[0].iterdir())
    assert kept == ["angry.wav", "calm.wav", "profile.json"]
    assert "angry words" in (old[0] / "profile.json").read_text()
    # the calm clip saved again from its own file: read before it moves
    profiles.save_clip(home, "lena", "calm", home / "lena" / "calm.wav", "same")
    assert profiles.load(home)["lena"]["clips"]["calm"]["text"] == "same"
    assert len([d for d in (home / "lena").iterdir() if d.is_dir()]) == 2


def test_a_new_calm_clip_moves_only_the_profiles_own_clips(tmp_path):
    home = tmp_path / "p"
    src = tone(tmp_path / "a.wav")
    profiles.save_clip(home, "lena", "calm", src, "old words", language="en")
    profiles.save_clip(home, "shin", "calm", src, "shin words", language="en")
    mine = tone(tmp_path / "my-recording.wav")
    pj = home / "lena" / "profile.json"
    p = json.loads(pj.read_text())
    p["clips"]["angry"] = {"wav": str(mine), "text": "x"}
    p["clips"]["sad"] = {"wav": "../shin/calm.wav", "text": "y"}
    pj.write_text(json.dumps(p))
    profiles.save_clip(home, "lena", "calm", tone(tmp_path / "b.wav"), "new words")
    assert mine.is_file() and (home / "shin" / "calm.wav").is_file()
    assert "shin" in profiles.load(home)
