"""Expression-cue rules (CONTRACTS.md "Expression cues for voice acting").
Table-driven sweeps over cue combinations: every knob stays in bounds, every
fired cue is named, effects are monotonic in intensity, and a line with no
cues is exactly what the punctuation rules alone produced."""

import itertools

import numpy as np
import pytest

from panelforge.audio import dsp, emotion

OUTLINES = ["smooth", "jagged", "wobbly", "dashed", "cloud", "rect", "none"]
KINDS = ["speech", "thought", "caption", "shout", "whisper"]
MOODS = [None, "tense", "calm", "action", "sad", "comic", "mystery"]
SPACES = [None, "small-room", "hall", "outdoor", "vehicle", "comms", "void"]
FACES = list(emotion.EXPRESSIONS)

BOUNDS = {
    "speed": (0.6, 1.8),
    "gain_db": (-14.0, 8.0),
    "pause_after": (0.0, 2.0),
    "reverb": (0.0, 1.0),
    "pitch": (-4.0, 4.0),
    "tremolo": (0.0, 0.75),
    "grit": (0.0, 0.7),
    "breath": (0.0, 1.0),
    "intensity": (0.0, 1.0),
}


def _ctx(
    face=None, i=0.7, conf=0.9, outline=None, mood=None, space=None, size=0.5, **style
):
    ctx: dict = {"style": dict(style)}
    if outline:
        ctx["style"]["outline"] = outline
    if face:
        ctx["expression"] = {"label": face, "intensity": i, "conf": conf}
    if mood:
        ctx["mood"] = mood
    if space:
        ctx["acoustics"] = {"space": space, "size": size}
    return ctx


def test_no_context_matches_punctuation_rules_exactly():
    for text, kind in [
        ("Hello there.", "speech"),
        ("Run!", "speech"),
        ("why...", "thought"),
        ("really?", "speech"),
        ("hush", "whisper"),
        ("Later.", "caption"),
    ]:
        plain = emotion.rules_for(text, kind)
        with_empty = emotion.rules_for(text, kind, {})
        assert plain == with_empty
        # text-only rules are punctuation plus what the words say (layer 3)
        from_words, wi, _ = emotion.words_expression(text)
        assert plain["expression"] == (from_words or "neutral")
        assert plain["intensity"] == (wi if from_words else 0.0)
        if not from_words:
            assert plain["pitch"] == 0.0 and plain["tremolo"] == 0.0
            assert plain["grit"] == 0.0 and plain["breath"] == 0.0
            assert plain["blend"] is None
        assert plain["source"] == "auto"


def test_neutral_line_renders_bit_identical_to_before():
    sr = 8000
    x = (np.sin(2 * np.pi * 220 * np.arange(sr) / sr) * 0.5).astype(np.float32)
    em = emotion.rules_for("Hello there.", "speech")
    assert np.array_equal(emotion.apply(x, sr, em), x)
    legacy = {"speed": 1.0, "gain_db": -3.0, "pause_after": 0.2, "reverb": 0.35}
    expected = dsp.gain_db(
        dsp.lowpass(dsp.echo(x, sr, delay_s=0.07, decay=0.3, taps=3), sr, 3200), -3.0
    )
    assert np.array_equal(emotion.apply(x, sr, legacy), expected)


def test_full_sweep_bounds_and_cue_names():
    n = 0
    for face, outline, mood, space, kind in itertools.product(
        FACES, OUTLINES, MOODS, SPACES, KINDS
    ):
        for i in (0.0, 0.5, 1.0):
            em = emotion.rules_for(
                "We are NOT going back!",
                kind,
                _ctx(face, i, outline=outline, mood=mood, space=space),
            )
            n += 1
            for key, (lo, hi) in BOUNDS.items():
                assert lo <= em[key] <= hi, (
                    key,
                    em[key],
                    face,
                    outline,
                    mood,
                    space,
                    kind,
                )
            assert em["eq"] in (None, "radio", "vehicle", "void")
            assert em["room"] in (None, *dsp.ROOMS)
            for cue in em["cues"]:
                assert cue == cue.lower() or not cue.isupper(), cue
                assert cue.strip() == cue and cue
            if emotion.OUTLINES[outline]:  # outlines that change nothing fire no cue
                assert any(outline in c for c in em["cues"]), (outline, em["cues"])
            if mood:
                assert any(mood in c for c in em["cues"])
            if space:
                assert any(space in c for c in em["cues"])
                if kind != "thought" and outline != "cloud":
                    assert em["room"] == space
            if face != "neutral" and i > 0:
                assert em["expression"] == face
                assert any(f"{face} face" in c for c in em["cues"])
            if em["blend"]:
                assert 0 < em["blend"]["weight"] <= 0.25
                assert em["blend"]["tone"] in emotion.BLEND_TONES
            if kind == "thought" or outline == "cloud":
                assert em["room"] == "void" and em["eq"] == "void"
            if space == "comms" and kind != "thought" and outline != "cloud":
                assert em["eq"] == "radio"
    assert n > 10000


@pytest.mark.parametrize("face", [f for f in FACES if f != "neutral"])
@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("outline", OUTLINES)
def test_effects_are_monotonic_in_intensity(face, kind, outline):
    table = emotion.EXPRESSIONS[face]
    signs = {
        "speed": table.get("speed", 0.0),
        "gain_db": table.get("gain", 0.0),
        "pitch": table.get("pitch", 0.0),
        "tremolo": table.get("tremolo", 0.0),
        "grit": table.get("grit", 0.0),
        "breath": table.get("breath", 0.0),
        "pause_after": table.get("pause", 0.0),
    }
    prev = None
    for i in np.linspace(0.0, 1.0, 11):
        em = emotion.rules_for(
            "We leave at dawn.", kind, _ctx(face, float(i), outline=outline)
        )  # a sentence with no cue words, so only the face sets the expression
        assert em["intensity"] == pytest.approx(float(i), abs=1e-6)
        if prev is not None:
            for key, sign in signs.items():
                if sign > 0:
                    assert em[key] >= prev[key] - 1e-9, (key, i, prev[key], em[key])
                elif sign < 0:
                    assert em[key] <= prev[key] + 1e-9, (key, i, prev[key], em[key])
            if table.get("blend"):
                w_now = (em["blend"] or {}).get("weight", 0.0)
                w_prev = (prev["blend"] or {}).get("weight", 0.0)
                assert w_now >= w_prev
        prev = em


def test_low_confidence_face_is_ignored_but_explained():
    em = emotion.rules_for("Fine.", "speech", _ctx("angry", 0.9, conf=0.1))
    plain = emotion.rules_for("Fine.", "speech")
    assert em["expression"] == "neutral" and em["gain_db"] == plain["gain_db"]
    assert any("low confidence" in c for c in em["cues"])


def test_lettering_rules():
    base = emotion.rules_for("Come here.", "speech")
    loud = emotion.rules_for(
        "Come here.", "speech", _ctx(text_scale=1.6, stroke_weight=1.5)
    )
    assert loud["gain_db"] > base["gain_db"] and loud["grit"] > 0
    assert "large heavy lettering" in loud["cues"]
    quiet = emotion.rules_for(
        "Come here.", "speech", {"style": {"text_scale": 0.6}, "balloon_scale": 1.5}
    )
    assert quiet["gain_db"] < base["gain_db"]
    assert "small text in big balloon" in quiet["cues"]
    small = emotion.rules_for("Come here.", "speech", _ctx(text_scale=0.6))
    assert base["gain_db"] > small["gain_db"] > quiet["gain_db"]
    wavy = emotion.rules_for("Come here.", "speech", _ctx(wavy=True))
    assert wavy["tremolo"] > 0 and "wavy lettering" in wavy["cues"]
    trem = emotion.rules_for("Come here.", "speech", _ctx(trembling=True))
    assert trem["tremolo"] > wavy["tremolo"] and trem["breath"] > 0
    bold = emotion.rules_for(
        "I will NEVER go back.", "speech", _ctx(bold_words=["NEVER"])
    )
    assert bold["emphasis"] == ["never"]
    assert "bold words: never" in bold["cues"]


def test_outline_rules():
    base = emotion.rules_for("Come here.", "speech")
    jag = emotion.rules_for("Come here.", "speech", _ctx(outline="jagged"))
    assert (
        jag["gain_db"] > base["gain_db"]
        and jag["speed"] > base["speed"]
        and jag["grit"] > 0
    )
    wob = emotion.rules_for("Come here.", "speech", _ctx(outline="wobbly"))
    assert wob["tremolo"] > 0 and wob["gain_db"] < base["gain_db"]
    dash = emotion.rules_for("Come here.", "speech", _ctx(outline="dashed"))
    assert dash["gain_db"] < base["gain_db"] and dash["breath"] > 0
    cloud = emotion.rules_for("Come here.", "speech", _ctx(outline="cloud"))
    assert cloud["room"] == "void" and cloud["eq"] == "void" and cloud["reverb"] > 0


def test_acoustics_rules():
    hall = emotion.rules_for("Come here.", "speech", _ctx(space="hall", size=1.0))
    small_hall = emotion.rules_for("Come here.", "speech", _ctx(space="hall", size=0.2))
    assert hall["room"] == "hall" and hall["reverb"] > small_hall["reverb"] > 0
    comms = emotion.rules_for("Come here.", "speech", _ctx(space="comms"))
    assert comms["eq"] == "radio" and comms["reverb"] == 0.0
    out = emotion.rules_for("Come here.", "speech", _ctx(space="outdoor"))
    assert out["reverb"] < small_hall["reverb"]


def test_mood_and_action_rules():
    base = emotion.rules_for("Come here.", "speech")
    act = emotion.rules_for("Come here.", "speech", {"mood": "action", "action": 0.9})
    assert act["speed"] > base["speed"] and "fast action panel" in act["cues"]
    sad = emotion.rules_for("Come here.", "speech", {"mood": "sad"})
    assert sad["speed"] < base["speed"] and sad["gain_db"] < base["gain_db"]


def test_segments_for_bold_words():
    one = emotion.segments_for("I will never go back.", [])
    assert one == [{"text": "I will never go back.", "speed_mul": 1.0, "gain_db": 0.0}]
    segs = emotion.segments_for("I will never, ever go back!", ["never", "ever"])
    assert [s["text"] for s in segs] == ["I will", "never, ever", "go back!"]
    assert segs[1]["speed_mul"] < 1.0 and segs[1]["gain_db"] > 0
    assert segs[0]["speed_mul"] == 1.0 and segs[2]["gain_db"] == 0.0
    lead = emotion.segments_for("NEVER again.", ["never"])
    assert [s["text"] for s in lead] == ["Never", "again."]
    caps = emotion.segments_for("I said NO WAY, friend.", ["no", "way"])
    assert [s["text"] for s in caps] == ["I said", "no way,", "friend."]
    miss = emotion.segments_for("Nothing here.", ["absent"])
    assert len(miss) == 1


def test_apply_runs_every_knob_and_stays_bounded():
    sr = 48000
    x = (np.sin(2 * np.pi * 180 * np.arange(sr) / sr) * 0.7).astype(np.float32)
    for kind, ctx in [
        ("speech", _ctx("angry", 1.0, outline="jagged", space="hall")),
        ("speech", _ctx("scared", 1.0, outline="wobbly", space="comms")),
        ("whisper", _ctx("sad", 1.0, outline="dashed", space="small-room")),
        ("thought", _ctx("happy", 1.0)),
        ("speech", _ctx("surprised", 1.0, space="vehicle")),
        ("speech", _ctx("pained", 1.0, space="void")),
    ]:
        em = emotion.rules_for("You said you would stay!", kind, ctx)
        y = emotion.apply(x, sr, em)
        assert y.shape == x.shape and np.all(np.isfinite(y))
        assert dsp.peak(y) <= 10 ** (8.0 / 20)  # at most the gain ceiling
        assert not np.array_equal(y, x)


def test_blend_partner_registry():
    from panelforge.audio import voices

    assert voices.blend_partner("am_michael", "dark") == "am_onyx"
    assert voices.blend_partner("am_onyx", "dark") == "am_fenrir"  # never itself
    assert voices.blend_partner("am_onyx", "dark", ["am_onyx"]) is None
    assert voices.blend_partner("jf_alpha", "dark") is None
    for prefix, tones in voices.BLEND_PARTNERS.items():
        for tone, partners in tones.items():
            assert tone in emotion.BLEND_TONES
            assert all(p.startswith(prefix + "_") for p in partners)
