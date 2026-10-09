"""cast.py: a game's lines to clips in its characters' voices."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pytest

import cast
import engines
import profiles
from test_profiles import make, tone

LINES = {
    "m1.a.010": {"speaker": "lena", "text": "Good morning.", "note": "cheerful"},
    "m1.a.020": {"speaker": "shin", "text": "Understood.", "note": "very quiet"},
    "m1.a.030": {"speaker": "lena", "text": "Log in.", "channel": "console"},
    "m1.a.040": {"speaker": "raiden", "text": "Oi."},
    "m1.a.050": {"speaker": "shin", "text": "Move.", "note": "from his bench"},
}


@pytest.fixture
def game(tmp_path):
    (tmp_path / "dialogue").mkdir()
    for i, part in enumerate(
        (dict(list(LINES.items())[:3]), dict(list(LINES.items())[3:]))
    ):
        f = tmp_path / "dialogue" / f"act{i}.json"
        f.write_text(json.dumps({"entries": part, "speakers": {}}))
    home = tmp_path / "profiles"
    make(home, "86-lena-en")
    make(home, "86-shin-en", clips=("calm", "whisper"))
    c = {
        "name": "test",
        "lines": str(tmp_path / "dialogue" / "*.json"),
        "out": str(tmp_path / "out"),
        "skip_channels": ["console"],
        "languages": {
            "en": {"model": "breeze", "design_model": "designer", "text": "text"},
            "ja": {"model": "irodori", "text": "text_ja"},
        },
        "note_moods": {"very quiet": "whisper", "quiet": "gentle"},
        "speakers": {
            "lena": {"en": {"voice": "86-lena-en", "describe": "a young officer"}},
            "shin": {"en": {"voice": "86-shin-en"}},
        },
    }
    return c, home


def test_moods_from_notes():
    c = {"note_moods": {"very quiet": "whisper", "quiet": "gentle"}}
    assert cast.mood_of("very quiet; plays only if", c) == "whisper"
    assert cast.mood_of("quieter", c) is None  # a phrase, not a prefix
    assert cast.mood_of("cheerful; chalk on the blackboard", c) == "happy"
    assert cast.mood_of("flat", c) == "calm"
    assert cast.mood_of("reading; bored", {"note_moods": {"bored": "tired"}}) == "tired"
    assert cast.mood_of("light; nobody answers", c) is None
    assert cast.mood_of("laughs", c) is None  # a sound is not a mood
    assert cast.mood_of("", c) is None


def test_plan_says_what_each_line_becomes(game):
    c, home = game
    items = {i["id"]: i for i in cast.plan(c, "en", home)}
    assert list(items) == sorted(LINES)
    assert items["m1.a.010"]["said"] == "[happy] Good morning."
    assert items["m1.a.010"]["stand_in"] is True
    assert items["m1.a.020"]["stand_in"] is False
    c["speakers"]["shin"]["en"]["preset"] = "am_x"  # a preset voice is a stand-in
    assert cast.plan(c, "en", home, only=("m1.a.020",))[0]["stand_in"] is True
    del c["speakers"]["shin"]["en"]["preset"]
    assert items["m1.a.020"]["said"] == "[whisper] Understood."
    key = items["m1.a.020"]["clip_key"].split("|")  # calm and the mood clip
    assert key[0].startswith("calm.wav:") and key[1].startswith("whisper.wav:")
    assert items["m1.a.050"]["said"] == "Move." and items["m1.a.050"]["mood"] is None
    assert "|" not in items["m1.a.050"]["clip_key"]  # calm only
    assert items["m1.a.050"]["clip_key"].startswith("calm.wav:")
    assert items["m1.a.030"]["skip"] == "console line, read not heard"
    assert items["m1.a.040"]["skip"] == "no en voice for raiden"
    ja = {i["id"]: i["skip"] for i in cast.plan(c, "ja", home)}
    assert ja.pop("m1.a.030") == "console line, read not heard"
    assert set(ja.values()) == {"no ja words"}
    only = cast.plan(c, "en", home, only=("m1.a.020",), speaker="shin")
    assert [i["id"] for i in only] == ["m1.a.020"]
    c["speakers"]["shin"]["en"]["voice"] = "86-nobody"
    assert "not made yet" in cast.plan(c, "en", home, speaker="shin")[0]["skip"]
    with pytest.raises(SystemExit):
        cast.plan(c, "de", home)


@pytest.fixture
def voice_api():
    """A stand-in Voice backend: a wav for any line, the default voice for
    voice 'busy' (as when Jan is busy), and what it was asked."""
    asked = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_POST(self):  # header names in lower case, as uvicorn sends them
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            asked.append(dict(body, path=self.path, forge=self.headers.get("X-Forge")))
            data = engines.wav_bytes(np.zeros(16000 * 5 // 4, np.float32), 16000)
            self.send_response(200)
            self.send_header("content-type", "audio/wav")
            model = "kokoro" if body["voice"] in ("busy", "old") else body["model"]
            self.send_header("x-voice-model", model)
            swap = body["voice"] == "swap"  # the backend picked another voice
            self.send_header("x-voice-voice", "harbour" if swap else body["voice"])
            if body["voice"] == "busy":
                self.send_header("x-voice-fell-back", "Jan is busy")
            self.end_headers()
            self.wfile.write(data + body["text"].encode())

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}", asked
    srv.shutdown()


def test_render_makes_keeps_and_remakes_clips(game, voice_api, tmp_path):
    c, home = game
    url, asked = voice_api
    dry = cast.render(c, "en", home, url, dry=True)
    assert [i["id"] for i in dry["todo"]] == ["m1.a.010", "m1.a.020", "m1.a.050"]
    assert asked == [] and not (tmp_path / "out").exists()

    res = cast.render(c, "en", home, url)
    why = {"console line, read not heard": 1, "no en voice for raiden": 1}
    assert res == {"made": 3, "kept": 0, "skipped": 2, "failed": [], "why": why}
    assert asked[0] == {
        "text": "[happy] Good morning.",
        "model": "breeze",
        "voice": "86-lena-en",
        "app": "cast",
        "path": "/api/tts",
        "forge": "1",
    }
    folder = tmp_path / "out" / "en"
    assert (folder / "m1.a.020.wav").read_bytes().endswith(b"[whisper] Understood.")
    m = json.loads((folder / "manifest.json").read_text())
    assert m["cast"] == "test" and m["language"] == "en"
    line = m["lines"]["m1.a.010"]
    assert line["file"] == "m1.a.010.wav" and line["seconds"] == 1.25
    assert line["speaker"] == "lena" and line["stand_in"] and not line["private"]

    assert cast.render(c, "en", home, url)["kept"] == 3 and len(asked) == 3
    LINES_CHANGED = json.loads((tmp_path / "dialogue" / "act1.json").read_text())
    LINES_CHANGED["entries"]["m1.a.050"]["text"] = "Move now."
    (tmp_path / "dialogue" / "act1.json").write_text(json.dumps(LINES_CHANGED))
    tone(home / "86-lena-en" / "calm.wav", seconds=0.5)  # a new voice clip
    res = cast.render(c, "en", home, url)
    assert res["made"] == 2 and res["kept"] == 1
    assert {a["text"] for a in asked[3:]} == {"[happy] Good morning.", "Move now."}
    assert cast.render(c, "en", home, url, redo=True, limit=1)["made"] == 1


def test_a_clip_in_the_default_voice_is_not_kept(game, voice_api, tmp_path):
    c, home = game
    url, _ = voice_api
    make(home, "busy")
    make(home, "old")
    c["speakers"]["shin"]["en"]["voice"] = "busy"
    res = cast.render(c, "en", home, url)
    assert res["made"] == 1 and len(res["failed"]) == 2
    assert "fell back to the default (Jan is busy)" in res["failed"][0]
    assert not (tmp_path / "out" / "en" / "m1.a.020.wav").exists()
    c["speakers"]["shin"]["en"]["voice"] = "old"  # an old backend, no fell-back header
    res = cast.render(c, "en", home, url)
    assert res["made"] == 0 and "kokoro spoke, not breeze" in res["failed"][0]
    res = cast.render(c, "en", home, "http://127.0.0.1:9")  # nothing listening
    assert res["made"] == 0 and len(res["failed"]) == 2


def test_voices_designs_only_missing_stand_ins(game, monkeypatch):
    c, home = game
    c["speakers"]["kurena"] = {
        "en": {"voice": "86-kurena-en", "describe": "cold", "sample": "Range four."}
    }
    calls = []

    class Eng:
        def design(self, text, describe, out):
            calls.append((text, describe))
            return tone(out)

        def close(self):
            calls.append("closed")

    monkeypatch.setattr(profiles, "_engine", lambda m, tools: ({"id": m}, Eng()))
    assert cast.design_voices(c, "en", home) == ["86-kurena-en"]
    assert calls == [("Range four.", "cold"), "closed"]
    p = profiles.load(home)["86-kurena-en"]
    assert p["language"] == "en" and p["label"] == "kurena (stand-in)"
    assert p["source"].startswith("stand-in designed with designer for test")
    assert p["clips"]["calm"]["text"] == "Range four."
    assert cast.design_voices(c, "en", home) == []  # nothing left to make


def test_voices_reads_a_preset_voice_first(game, monkeypatch):
    c, home = game
    c["languages"]["en"]["preset_model"] = "kokoro"
    c["speakers"]["kurena"] = {
        "en": {"voice": "86-kurena-en", "preset": "af_x", "sample": "Range four."}
    }
    c["speakers"]["theo"] = {
        "en": {"voice": "86-theo-en", "describe": "dry", "sample": "Laughing Fox."}
    }
    calls = []

    class Eng:
        def __init__(self, model, tools):
            self.model, self.tools = model, tools

        def synthesize(self, text, voice, speed):
            calls.append((self.model, self.tools, text, voice))
            return np.full(2400, 0.1, np.float32), 24000

        def design(self, text, describe, out):
            calls.append((self.model, self.tools, text, describe))
            return tone(out)

        def close(self):
            calls.append(("closed", self.model))

    monkeypatch.setattr(
        profiles, "_engine", lambda m, tools: ({"id": m}, Eng(m, tools))
    )
    assert cast.design_voices(c, "en", home) == ["86-kurena-en", "86-theo-en"]
    assert calls == [
        ("kokoro", False, "Range four.", "af_x"),
        ("closed", "kokoro"),
        ("designer", True, "Laughing Fox.", "dry"),
        ("closed", "designer"),
    ]
    p = profiles.load(home)["86-kurena-en"]
    assert p["source"] == "stand-in read by af_x of kokoro for test"
    assert p["clips"]["calm"]["text"] == "Range four."
    c["languages"]["en"].pop("preset_model")
    c["speakers"]["rito"] = {
        "en": {"voice": "86-rito-en", "preset": "x", "sample": "a"}
    }
    with pytest.raises(SystemExit):
        cast.design_voices(c, "en", home)


def test_the_eightysix_cast_file_is_sound():
    c = cast.load("eightysix")
    assert set(c["languages"]) == {"en", "ja"}
    for sid, per in c["speakers"].items():
        for lang, sp in per.items():
            assert lang in c["languages"]
            assert profiles.ID.match(sp["voice"])
            assert sp["sample"] and (sp.get("describe") or sp.get("preset"))
            maker = "preset_model" if sp.get("preset") else "design_model"
            assert c["languages"][lang].get(maker)
    for mood in c["note_moods"].values():
        assert mood in cast.expressive.vocab()["tags"]
    with pytest.raises(SystemExit):
        cast.load("../etc")


def test_a_new_calm_clip_remakes_mood_lines_too(game, voice_api):
    """Breeze clones only the calm clip, so a new calm clip must remake a
    whisper line even though Shin has a whisper clip of his own."""
    c, home = game
    url, asked = voice_api
    assert cast.render(c, "en", home, url)["made"] == 3
    tone(home / "86-shin-en" / "calm.wav", seconds=0.9)
    res = cast.render(c, "en", home, url)
    assert res["made"] == 2 and res["kept"] == 1
    assert {a["text"] for a in asked[3:]} == {"[whisper] Understood.", "Move."}
    tone(home / "86-shin-en" / "whisper.wav", seconds=0.7)  # the mood clip too
    assert cast.render(c, "en", home, url)["made"] == 1
    assert asked[-1]["text"] == "[whisper] Understood."


def test_a_clip_in_another_voice_is_not_kept(game, voice_api, tmp_path):
    c, home = game
    url, _ = voice_api
    make(home, "swap")
    c["speakers"]["shin"]["en"]["voice"] = "swap"
    res = cast.render(c, "en", home, url)
    assert res["made"] == 1 and len(res["failed"]) == 2
    assert "voice harbour spoke, not swap" in res["failed"][0]
    assert not (tmp_path / "out" / "en" / "m1.a.020.wav").exists()


def test_two_ids_never_share_a_file_and_silent_lines_are_skipped(
    game, voice_api, tmp_path
):
    c, home = game
    url, asked = voice_api
    entries = {
        "x 1": {"speaker": "lena", "text": "First line."},
        "x_1": {"speaker": "lena", "text": "Second line."},
        "x.2": {"speaker": "lena", "text": "...", "note": "says nothing"},
        "x.3": {"speaker": "lena", "text": "[sigh]"},
    }
    (tmp_path / "dialogue" / "act9.json").write_text(json.dumps({"entries": entries}))
    res = cast.render(c, "en", home, url)
    assert res["why"]["nothing to say (no words)"] == 2 and not res["failed"]
    m = json.loads((tmp_path / "out" / "en" / "manifest.json").read_text())
    first, second = m["lines"]["x 1"]["file"], m["lines"]["x_1"]["file"]
    assert second == "x_1.wav" and first.startswith("x_1-") and first != second
    folder = tmp_path / "out" / "en"
    assert (folder / first).read_bytes().endswith(b"First line.")
    assert (folder / second).read_bytes().endswith(b"Second line.")
    assert "x.2" not in m["lines"] and "x.3" not in m["lines"]
