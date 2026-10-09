"""Emotion rules and ALL-CAPS normalization (no model load required)."""

import numpy as np

from panelforge.audio import emotion


def test_shout_is_faster_and_louder():
    calm = emotion.rules_for("hello there", "speech")
    shout = emotion.rules_for("hello there!", "speech")
    assert shout["speed"] > calm["speed"]
    assert shout["gain_db"] > calm["gain_db"]


def test_ellipsis_is_slower_with_longer_pause():
    calm = emotion.rules_for("hello there.", "speech")
    trail = emotion.rules_for("hello there...", "speech")
    assert trail["speed"] < calm["speed"]
    assert trail["pause_after"] > calm["pause_after"]


def test_question_gets_a_lift_flag():
    q = emotion.rules_for("really?", "speech")
    assert q["lift"] is True
    flat = emotion.rules_for("really.", "speech")
    assert flat["lift"] is False


def test_whisper_is_quieter():
    normal = emotion.rules_for("hush now", "speech")
    whisper = emotion.rules_for("hush now", "whisper")
    assert whisper["gain_db"] < normal["gain_db"]


def test_thought_softer_with_reverb():
    thought = emotion.rules_for("what now", "thought")
    assert thought["gain_db"] < 0
    assert thought["reverb"] > 0


def test_all_caps_detected_and_normalized():
    assert emotion.is_shouty_caps("THIS WILL INCREASE MY WORTH!")
    assert not emotion.is_shouty_caps("Normal line.")
    norm = emotion.normalize_text("THIS WILL INCREASE MY WORTH!")
    assert norm != "THIS WILL INCREASE MY WORTH!"
    assert norm.lower() == "this will increase my worth!"


def test_apply_gain_and_reverb_change_signal():
    sr = 8000
    x = (np.sin(2 * np.pi * 440 * np.arange(sr) / sr) * 0.5).astype(np.float32)
    quiet = emotion.apply(x, sr, {"gain_db": -6.0})
    assert np.max(np.abs(quiet)) < np.max(np.abs(x))
    thoughty = emotion.apply(x, sr, {"reverb": 0.35, "gain_db": 0.0})
    assert thoughty.shape == x.shape
    assert not np.allclose(thoughty, x)


def test_words_give_an_expression_when_the_face_is_neutral():
    from panelforge.audio import emotion as E

    angry = E.rules_for("I'll kill you, you bastard!", "shout")
    assert angry["expression"] == "angry" and angry["intensity"] >= 0.5
    assert any(c.startswith("angry words") for c in angry["cues"])
    scared = E.rules_for("Please... help me. Don't leave.", "speech")
    assert scared["expression"] == "scared" and scared["tremolo"] > 0
    plain = E.rules_for("The empire grew.", "caption")
    assert plain["expression"] == "neutral" and not [
        c for c in plain["cues"] if "words" in c
    ]
    # a confident face wins over the words
    face = {"expression": {"label": "happy", "intensity": 0.8, "conf": 0.9}}
    r = E.rules_for("I'll kill you!", "speech", face)
    assert r["expression"] == "happy"
