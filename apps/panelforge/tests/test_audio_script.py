"""Script build from a fixture bubbles.json (helper-2 hasn't landed
bubbles.json yet, so this uses a fixture matching CONTRACTS.md's shape)."""

from panelforge.audio import script as script_mod

FIXTURE = {
    "schema": 1,
    "bubbles": [
        {
            "id": "b0001",
            "panel_id": "p0001",
            "order": 1,
            "box": [0, 0, 10, 10],
            "kind": "speech",
            "text": "We need to move!",
            "speaker": "c01",
        },
        {
            "id": "b0002",
            "panel_id": "p0001",
            "order": 2,
            "box": [0, 0, 10, 10],
            "kind": "thought",
            "text": "This is bad...",
            "speaker": "c01",
        },
        {
            "id": "b0003",
            "panel_id": "p0002",
            "order": 1,
            "box": [0, 0, 10, 10],
            "kind": "caption",
            "text": "Meanwhile, across town.",
            "speaker": None,
        },
        {
            "id": "b0004",
            "panel_id": "p0002",
            "order": 2,
            "box": [0, 0, 10, 10],
            "kind": "sfx",
            "text": "CLANK",
            "speaker": None,
        },
        {
            "id": "b0005",
            "panel_id": "p0003",
            "order": 1,
            "box": [0, 0, 10, 10],
            "kind": "whisper",
            "text": "don't move",
            "speaker": "c02",
        },
    ],
}


def test_sfx_bubbles_are_skipped():
    out = script_mod.build_script(FIXTURE)
    ids = [ln["bubble_id"] for ln in out["lines"]]
    assert "b0004" not in ids
    assert len(out["lines"]) == 4


def test_captions_go_to_narrator():
    out = script_mod.build_script(FIXTURE)
    caption = next(ln for ln in out["lines"] if ln["bubble_id"] == "b0003")
    assert caption["speaker"] == "narrator"


def test_emotion_attached_per_line():
    out = script_mod.build_script(FIXTURE)
    shout = next(ln for ln in out["lines"] if ln["bubble_id"] == "b0001")
    trail = next(ln for ln in out["lines"] if ln["bubble_id"] == "b0002")
    assert shout["emotion"]["speed"] > 1.0
    assert trail["emotion"]["speed"] < 1.0
    assert trail["emotion"]["reverb"] > 0  # thought bubble


def test_line_ids_sequential_and_schema():
    out = script_mod.build_script(FIXTURE)
    assert out["schema"] == 1
    assert [ln["id"] for ln in out["lines"]] == ["l0001", "l0002", "l0003", "l0004"]


def test_edited_line_survives_rebuild():
    first = script_mod.build_script(FIXTURE)
    line = first["lines"][0]
    line["edited"] = True
    line["text"] = "Emerson's custom line"
    line["voice_override"] = {"voice": "am_michael"}
    rebuilt = script_mod.build_script(FIXTURE, first)
    kept = next(ln for ln in rebuilt["lines"] if ln["bubble_id"] == "b0001")
    assert kept["text"] == "Emerson's custom line"
    assert kept["voice_override"] == {"voice": "am_michael"}


def test_unchanged_line_keeps_rendered_audio():
    first = script_mod.build_script(FIXTURE)
    first["lines"][2]["audio"] = "audio/l0003.wav"
    first["lines"][2]["dur"] = 1.2
    rebuilt = script_mod.build_script(FIXTURE, first)
    kept = next(ln for ln in rebuilt["lines"] if ln["bubble_id"] == "b0003")
    assert kept["audio"] == "audio/l0003.wav"
    assert kept["dur"] == 1.2


# ---- expression cues from scene.json and bubble style (task 9) -----------
import copy

SCENE = {
    "schema": 1,
    "panels": {
        "p0001": {
            "mood": "tense",
            "action": 0.8,
            "acoustics": {"space": "hall", "size": 0.9},
            "characters": [
                {
                    "cast_id": "c01",
                    "box": [0, 0, 5, 5],
                    "expression": {"label": "angry", "intensity": 0.8, "conf": 0.9},
                },
                {
                    "cast_id": "c02",
                    "box": [5, 0, 5, 5],
                    "expression": {"label": "scared", "intensity": 0.6, "conf": 0.8},
                },
            ],
        },
        "p0003": {
            "mood": "mystery",
            "acoustics": {"space": "comms", "size": 0.2},
            "characters": [
                {
                    "cast_id": "c02",
                    "box": [0, 0, 5, 5],
                    "expression": {"label": "scared", "intensity": 0.9, "conf": 0.9},
                }
            ],
        },
    },
    "speakers": {"b0005": {"speaker": "c02", "conf": 0.7, "why": "tail"}},
}


def _styled_fixture():
    doc = copy.deepcopy(FIXTURE)
    by_id = {b["id"]: b for b in doc["bubbles"]}
    by_id["b0001"]["style"] = {
        "outline": "jagged",
        "text_scale": 1.5,
        "stroke_weight": 1.4,
        "bold_words": ["MOVE"],
    }
    by_id["b0001"]["box"] = [0, 0, 10, 10]
    by_id["b0005"]["style"] = {
        "outline": "dashed",
        "text_scale": 0.6,
        "trembling": True,
    }
    by_id["b0005"]["box"] = [0, 0, 40, 40]  # big balloon, small text
    by_id["b0005"]["speaker"] = None  # scene.json's speaker guess fills it
    return doc


def test_scene_cues_reach_the_line_emotion():
    out = script_mod.build_script(_styled_fixture(), None, SCENE)
    shout = next(ln for ln in out["lines"] if ln["bubble_id"] == "b0001")
    em = shout["emotion"]
    assert em["expression"] == "angry" and em["intensity"] == 0.8
    assert em["room"] == "hall"
    for cue in (
        "angry face",
        "jagged outline",
        "large heavy lettering",
        "tense mood",
        "fast action panel",
        "hall acoustics",
        "bold words: move",
        "exclamation mark",
    ):
        assert cue in em["cues"], (cue, em["cues"])
    assert em["emphasis"] == ["move"]
    whisper = next(ln for ln in out["lines"] if ln["bubble_id"] == "b0005")
    assert whisper["speaker"] == "c02"  # from scene.json speakers
    wem = whisper["emotion"]
    assert wem["expression"] == "scared" and wem["eq"] == "radio"
    assert "small text in big balloon" in wem["cues"]
    assert "trembling lettering" in wem["cues"]
    assert wem["tremolo"] > 0


def test_bubble_speaker_wins_over_scene_guess():
    doc = _styled_fixture()
    next(b for b in doc["bubbles"] if b["id"] == "b0005")["speaker"] = "c01"
    out = script_mod.build_script(doc, None, SCENE)
    whisper = next(ln for ln in out["lines"] if ln["bubble_id"] == "b0005")
    assert whisper["speaker"] == "c01"
    # and the face used is c01's in that panel -- c01 is absent from p0003,
    # so no face expression; "don't move" alone, said flat, sets no tone
    assert whisper["emotion"]["expression"] == "neutral"
    assert not any("face" in c for c in whisper["emotion"]["cues"])


def test_no_scene_means_punctuation_rules_only():
    plain = script_mod.build_script(FIXTURE)
    with_none = script_mod.build_script(FIXTURE, None, None)
    assert plain == with_none
    cues = plain["lines"][0]["emotion"]["cues"]
    assert cues[0] == "exclamation mark" and all(
        c == "exclamation mark" or c.endswith("words: move") for c in cues
    )  # punctuation plus what the words say; no page cues without a scene


def test_user_set_emotion_survives_rebuild_but_text_follows_bubble():
    first = script_mod.build_script(_styled_fixture(), None, SCENE)
    line = first["lines"][0]
    line["emotion"] = dict(
        line["emotion"], gain_db=-9.0, source="user", cues=["set by hand"]
    )
    line["audio"], line["dur"] = "audio/l0001.wav", 1.0
    rebuilt = script_mod.build_script(_styled_fixture(), first, SCENE)
    kept = next(ln for ln in rebuilt["lines"] if ln["bubble_id"] == "b0001")
    assert kept["emotion"]["gain_db"] == -9.0 and kept["emotion"]["source"] == "user"
    assert kept["audio"] == "audio/l0001.wav"  # nothing changed, audio kept
    doc = _styled_fixture()
    doc["bubbles"][0]["text"] = "We need to run!"
    rebuilt2 = script_mod.build_script(doc, first, SCENE)
    kept2 = next(ln for ln in rebuilt2["lines"] if ln["bubble_id"] == "b0001")
    assert kept2["text"] == "We need to run!"
    assert kept2["emotion"]["gain_db"] == -9.0
    assert kept2["audio"] is None  # text changed, must re-speak


def test_line_context_matches_build():
    doc = _styled_fixture()
    ctx = script_mod.line_context(doc, SCENE, "b0005")
    assert ctx is not None
    assert ctx["acoustics"]["space"] == "comms"
    assert ctx["expression"]["label"] == "scared"
    assert ctx["balloon_scale"] > 1.2
    assert script_mod.line_context(doc, SCENE, "nope") is None
