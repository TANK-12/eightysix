"""Emotion and sound tags: the shared vocabulary (shared/voice_emotions.json),
how each style writes them, and that a plain voice never reads them aloud."""

import json

import pytest

import expressive
from conftest import FakeEngine
from engines import InputError
from engines.breeze_cpp import Engine as Breeze


@pytest.mark.parametrize(
    "text, said",
    [
        ("[angry] I told you to fall back. [sigh]", "I told you to fall back."),
        ("[Angrily] Move!", "Move!"),
        ("[sad, whisper] okay", "okay"),
        ("Wait [pause] what", "Wait... what"),
        ("[clears throat] Right.", "Right."),
        ("See (above) for more", "See (above) for more"),
        ("[angry, nope] stays", "[angry, nope] stays"),
        ("no tags here", "no tags here"),
        ("Line one [sigh]\nLine two", "Line one\nLine two"),
        ("はい [sigh] 。", "はい。"),
        ("［怒り］下がれ。", "下がれ。"),
        ("（笑）はい [ため息]", "はい"),
    ],
)
def test_plain_takes_known_tags_out(text, said):
    assert expressive.plain(text) == said


def test_mood_is_the_first_emotion_or_delivery_tag():
    assert expressive.mood(expressive.parse("[laugh] [angry] hi [sad]")) == "angry"
    assert expressive.mood(expressive.parse("[laugh] hi")) is None
    assert expressive.mood(expressive.parse("[whispering] hi")) == "whisper"
    assert expressive.has_tags("[sigh] hi") and not expressive.has_tags("(hi)")


def test_irodori_writes_emoji_in_place():
    st = expressive.style("irodori")
    pieces = expressive.parse("[angry] 何をしている。 [laugh] 冗談だ")
    assert expressive.render(pieces, st) == "😠何をしている。🤭冗談だ"


def test_spaced_styles_keep_words_apart():
    st = expressive.style("breeze")
    said = expressive.render(expressive.parse("That's funny [laugh] really"), st)
    assert said == "That's funny (laugh) really"
    omni = expressive.style("omnivoice")
    assert expressive.render(expressive.parse("[laughs] Ha"), omni) == "[laughter] Ha"


def test_unknown_style_is_plain():
    assert expressive.style("nope") == expressive.style("plain")


def test_every_style_maps_known_tags_only():
    v = expressive.vocab()
    for name, st in v["styles"].items():
        for tag in list(st.get("map", {})) + list(st.get("edits", {})):
            assert tag in v["tags"], (name, tag)
        for tag in st.get("instructions", {}):
            assert tag in v["tags"], (name, tag)
    aliases = [a for t in v["tags"].values() for a in t.get("aliases", [])]
    assert len(aliases) == len(set(aliases)) and not set(aliases) & set(v["tags"])


def breeze(style):
    e = Breeze.__new__(Breeze)
    e.instruction, e.style = "", expressive.style(style) if style else None
    return e


def test_breeze_mood_becomes_the_direction():
    f = breeze("breeze").direction("[angry] Fall back now. [laugh]")
    assert f["text"] == "Fall back now. (laugh)"
    assert f["instruction"].startswith("Speak angrily")
    assert f["cfg_scale"] == "2.5"
    f = breeze("breeze").direction("[gently] Easy now.")
    assert f == {"text": "Easy now.", "instruction": "Speak gently and warmly."}
    assert breeze("breeze").direction("[sigh]")["text"] == "(sigh)"
    with pytest.raises(InputError):
        breeze("breeze").direction("[pause]")


def test_breeze_without_style_sends_text_as_is():
    assert breeze(None).direction("[angry] hi") == {"text": "[angry] hi"}


def test_plain_voice_gets_tags_taken_out(client):
    r = client.post("/api/tts", json={"text": "[angry] hello there [sigh]"})
    assert r.status_code == 200
    assert FakeEngine.calls[-1][1] == "hello there."
    r = client.post("/api/tts", json={"text": "[sigh] [pause]"})
    assert r.status_code == 400 and "nothing to say" in r.json()["detail"]


def test_expressive_voice_gets_tags(client, env):
    reg = json.loads((env / "reg.json").read_text())
    reg["models"][1]["expressive"] = "auk"
    (env / "reg.json").write_text(json.dumps(reg))
    r = client.post("/api/tts", json={"text": "[angry] hello there [sigh]"})
    assert r.status_code == 200
    assert FakeEngine.calls[-1][1] == "[angry] hello there [sigh]."


@pytest.mark.parametrize(
    "text", ["（怒って）こんにちは", "（悲しげに）こんにちは", "［怒って］こんにちは"]
)
def test_full_width_brackets_take_every_mood(text):
    assert expressive.plain(text) == "こんにちは"
    assert expressive.mood(expressive.parse(text)) in ("angry", "sad")
