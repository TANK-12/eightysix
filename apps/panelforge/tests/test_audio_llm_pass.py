"""The local-model page reading: guarded speakers, expressions and OCR fixes."""

import json

import pytest

from panelforge.audio import llm_pass


def _fixture():
    bubbles = {
        "bubbles": [
            {"id": "b1", "panel_id": "p1", "kind": "caption"},
            {"id": "b2", "panel_id": "p2", "kind": "speech"},
            {"id": "b3", "panel_id": "p2", "kind": "speech"},
            {"id": "b4", "panel_id": "p3", "kind": "speech"},
        ]
    }
    scene = {
        "panels": {
            "p1": {"scene_id": "s1", "mood": "calm", "characters": []},
            "p2": {
                "scene_id": "s1",
                "mood": "tense",
                "characters": [{"cast_id": "c01"}, {"cast_id": "c02"}],
            },
            "p3": {
                "scene_id": "s1",
                "mood": "tense",
                "characters": [{"cast_id": "c02"}],
            },
        },
        "speakers": {
            "b2": {"speaker": "c01", "conf": 0.4},
            "b3": {"speaker": "c01", "conf": 0.9},
            "b4": {"speaker": "c02", "conf": 0.5},
        },
    }
    script = {
        "lines": [
            {
                "id": "l1",
                "bubble_id": "b1",
                "speaker": "narrator",
                "kind": "caption",
                "text": "The empire grew.",
                "emotion": {"expression": "neutral", "cues": []},
            },
            {
                "id": "l2",
                "bubble_id": "b2",
                "speaker": "c01",
                "kind": "speech",
                "text": "1S this it?",
                "emotion": {"expression": "neutral", "cues": []},
            },
            {
                "id": "l3",
                "bubble_id": "b3",
                "speaker": "c01",
                "kind": "speech",
                "text": "Get out.",
                "emotion": {"expression": "neutral", "cues": []},
            },
            {
                "id": "l4",
                "bubble_id": "b4",
                "speaker": "c02",
                "kind": "speech",
                "text": "Fine.",
                "emotion": {"expression": "neutral", "cues": []},
            },
        ]
    }
    cast = {"cast": [{"id": "c01", "name": "Rook"}, {"id": "c02", "name": "Vale"}]}
    return script, bubbles, scene, cast


def test_pass_takes_only_guarded_changes():
    script, bubbles, scene, cast = _fixture()
    prompts = []

    def chat(system, user):
        prompts.append(user)
        return json.dumps(
            {
                "1": {
                    "speaker": "narrator",
                    "expression": "neutral",
                    "intensity": 0,
                    "fix": None,
                },
                # unsure geometry, c02 is present: taken; OCR fix is small: taken
                "2": {
                    "speaker": "c02",
                    "expression": "surprised",
                    "intensity": 0.6,
                    "fix": "Is this it?",
                },
                # geometry was sure (0.9): speaker kept; expression taken
                "3": {
                    "speaker": "c02",
                    "expression": "angry",
                    "intensity": 0.8,
                    "fix": None,
                    "delivery": {"speed": 0.8, "gain_db": -9, "pause_after": 0.6},
                    "why": "a quiet threat",
                },
                # a character who is not in the panel: refused; a rewrite: refused
                "4": {
                    "speaker": "c09",
                    "expression": "happy",
                    "intensity": 0.5,
                    "fix": "Fine, let us go home now and rest.",
                },
            }
        )

    took = llm_pass.run(script, bubbles, scene, cast, chat)
    assert took == {"speaker": 1, "expression": 3, "fix": 1, "delivery": 1}, took
    by = {l["id"]: l for l in script["lines"]}
    assert by["l2"]["speaker"] == "c02" and by["l2"]["text"] == "Is this it?"
    assert by["l2"]["text_ocr"] == "1S this it?" and by["l2"]["llm"]["fix_taken"]
    assert by["l3"]["speaker"] == "c01" and by["l3"]["emotion"]["expression"] == "angry"
    assert "model read: angry" in by["l3"]["emotion"]["cues"]
    em3 = by["l3"]["emotion"]
    assert em3["speed"] == 0.8 and em3["gain_db"] == -6.0  # clamped to the DSP limit
    assert em3["pause_after"] == 0.6 and by["l3"]["llm"]["why"] == "a quiet threat"
    assert any(c.startswith("model delivery") for c in em3["cues"])
    assert by["l4"]["speaker"] == "c02" and by["l4"]["text"] == "Fine."
    assert by["l4"]["emotion"]["expression"] == "happy"  # expression alone is fine
    assert "Rook" in prompts[0] and "geometry guess" in prompts[0]


def test_user_edited_lines_and_bad_answers_are_left_alone():
    script, bubbles, scene, cast = _fixture()
    script["lines"][1]["edited"] = True
    script["lines"][2]["emotion"]["source"] = "user"
    took = llm_pass.run(script, bubbles, scene, cast, lambda s, u: "not json at all")
    assert took == {"speaker": 0, "expression": 0, "fix": 0, "delivery": 0}
    took = llm_pass.run(
        script,
        bubbles,
        scene,
        cast,
        lambda s, u: json.dumps(
            {
                "2": {"speaker": "c02", "fix": "Is this it?"},
                "3": {"expression": "angry", "intensity": 0.9},
            }
        ),
    )
    assert took == {"speaker": 0, "expression": 0, "fix": 0, "delivery": 0}
    assert script["lines"][1]["text"] == "1S this it?"


def test_one_failing_batch_does_not_lose_the_rest():
    script, bubbles, scene, cast = _fixture()
    calls = {"n": 0}

    def chat(system, user):
        calls["n"] += 1
        raise RuntimeError("model busy")

    took = llm_pass.run(script, bubbles, scene, cast, chat)
    assert (
        took == {"speaker": 0, "expression": 0, "fix": 0, "delivery": 0}
        and calls["n"] >= 1
    )


def test_a_first_person_caption_becomes_the_characters_thought():
    script, bubbles, scene, cast = _fixture()
    script["lines"][0]["text"] = "Can I really do that?"
    # the scene's "narrator, it's a caption box" comes at 0.8 on the real
    # series; that is the kind rule, not knowledge of who thinks it
    scene["speakers"]["b1"] = {"speaker": "narrator", "conf": 0.8, "why": "caption box"}
    scene["panels"]["p1"]["characters"] = [{"cast_id": "c01"}]
    took = llm_pass.run(
        script,
        bubbles,
        scene,
        cast,
        lambda s, u: json.dumps(
            {"1": {"speaker": "c01", "expression": "surprised", "intensity": 0.5}}
        ),
    )
    assert took["speaker"] == 1
    l1 = script["lines"][0]
    assert (
        l1["speaker"] == "c01"
        and l1["kind"] == "thought"
        and l1["llm"]["kind"] == "thought"
    )


def test_an_unparseable_batch_is_retried_in_halves():
    script, bubbles, scene, cast = _fixture()
    calls = []

    def chat(system, user):
        calls.append(user)
        block = user.split("Lines to annotate:")[1]
        nums = [ln.strip().split(" [")[0] for ln in block.strip().split("\n")]
        if len(nums) > 2:
            return '{"1": {"speaker": "narr'  # cut off: the whole batch is too long
        return json.dumps({k: {"expression": "angry", "intensity": 0.5} for k in nums})

    took = llm_pass.run(script, bubbles, scene, cast, chat)
    assert took["expression"] == 4 and len(calls) == 3


def test_narrator_is_accepted_for_a_line_in_an_empty_panel():
    script, bubbles, scene, cast = _fixture()
    # a narration box the reader called speech, in a panel with nobody in it
    bubbles["bubbles"][0]["kind"] = "speech"
    script["lines"][0].update({"kind": "speech", "speaker": None})
    scene["speakers"]["b1"] = {"speaker": None, "conf": 0.0}
    took = llm_pass.run(
        script,
        bubbles,
        scene,
        cast,
        lambda s, u: json.dumps({"1": {"speaker": "narrator"}}),
    )
    assert took["speaker"] == 1 and script["lines"][0]["speaker"] == "narrator"


def test_vision_pass_asks_only_where_two_stand_and_takes_a_seen_answer(tmp_path):
    from PIL import Image

    script, bubbles, scene, cast = _fixture()
    for pid in ("p1", "p2", "p3"):
        scene["panels"][pid]["characters"] = [
            {**c, "box": [i * 100, 0, 90, 200]}
            for i, c in enumerate(scene["panels"][pid]["characters"])
        ]
    (tmp_path / "work/detect/panels").mkdir(parents=True)
    panels = []
    for pid in ("p1", "p2", "p3"):
        Image.new("RGB", (200, 200), "white").save(
            tmp_path / f"work/detect/panels/{pid}.png"
        )
        panels.append(
            {
                "id": pid,
                "box": [0, 0, 200, 200],
                "image": f"work/detect/panels/{pid}.png",
            }
        )
    asked = []

    def chat_image(system, user, url):
        asked.append(user)
        assert url.startswith("data:image/jpeg;base64,")
        assert "c01 (Rook): left, middle" in user
        assert "c02 (Vale): right, middle" in user
        return '{"2": "c02", "3": "c99"}'

    took = llm_pass.vision_pass(
        script, bubbles, scene, cast, tmp_path, panels, chat_image
    )
    # only p2 has two characters and an unsure line (l2, conf 0.4); l3 is
    # sure at 0.9, l4 stands alone with one character, l1 is a caption
    assert len(asked) == 1 and "  2: 1S this it?" in asked[0]
    assert "3:" not in asked[0]
    assert took == 1
    by_id = {ln["id"]: ln for ln in script["lines"]}
    assert by_id["l2"]["speaker"] == "c02"
    assert by_id["l2"]["llm"]["vision_speaker"] == "c02"
    assert by_id["l3"]["speaker"] == "c01"
    assert by_id["l4"]["speaker"] == "c02"
    # with `everyone`, the sure line in that panel is asked about as well
    # (l4 still not: one character stands there; l1 still not: a caption)
    asked.clear()
    llm_pass.vision_pass(
        script, bubbles, scene, cast, tmp_path, panels, chat_image, everyone=True
    )
    assert len(asked) == 1 and "3:" in asked[0] and "4:" not in asked[0]


def test_vision_pass_survives_a_failed_request(tmp_path):
    from PIL import Image

    script, bubbles, scene, cast = _fixture()
    scene["panels"]["p2"]["characters"] = [
        {"cast_id": "c01", "box": [0, 0, 90, 200]},
        {"cast_id": "c02", "box": [100, 0, 90, 200]},
    ]
    (tmp_path / "work/detect/panels").mkdir(parents=True)
    Image.new("RGB", (200, 200), "white").save(tmp_path / "work/detect/panels/p2.png")
    panels = [
        {"id": "p2", "box": [0, 0, 200, 200], "image": "work/detect/panels/p2.png"}
    ]

    def chat_image(system, user, url):
        raise TimeoutError("slow")

    assert (
        llm_pass.vision_pass(script, bubbles, scene, cast, tmp_path, panels, chat_image)
        == 0
    )
    assert script["lines"][1]["speaker"] == "c01"


def test_a_dropped_connection_is_asked_once_more(monkeypatch):
    monkeypatch.setattr(llm_pass, "RETRY_WAIT", 0.0)
    calls = []

    def chat(system, user):
        calls.append(user)
        if len(calls) == 1:
            raise RuntimeError("Jan said 500: proxy error: Failed to read connection")
        return '{"1": {"speaker": "narrator"}}'

    assert llm_pass._ask_twice(chat, "s", "u") == '{"1": {"speaker": "narrator"}}'
    assert len(calls) == 2

    def broken(system, user):
        raise ValueError("bad json body")

    with pytest.raises(ValueError):
        llm_pass._ask_twice(broken, "s", "u")


def test_bare_number_keys_and_delivery_words_are_understood():
    raw = '{\n  2: { "speaker": "c02", "delivery": "slow, quiet", "why": "threat" },\n  3: { "delivery": ["shout"], },\n}'
    got = llm_pass._parse(raw)
    assert set(got) == {"2", "3"}
    assert llm_pass.delivery_knobs(got["2"]["delivery"]) == {
        "speed": 0.85,
        "gain_db": -4.0,
    }
    assert llm_pass.delivery_knobs(got["3"]["delivery"])["gain_db"] == 5.0
    assert llm_pass.delivery_knobs({"speed": 1.3, "junk": 1}) == {"speed": 1.3}
    assert llm_pass.delivery_knobs("mumbling") == {}
    assert llm_pass.delivery_knobs(None) == {}


def test_a_balloon_in_an_empty_panel_may_go_to_someone_in_the_scene():
    script, bubbles, scene, cast = _fixture()
    # a speech balloon with a tail in a panel where nobody is drawn: the
    # model is offered the scene's cast and may pick c02 speaking off-panel
    bubbles["bubbles"][0].update({"kind": "speech", "tail": [5, 5]})
    script["lines"][0].update({"kind": "speech", "speaker": None})
    scene["speakers"]["b1"] = {"speaker": None, "conf": 0.0}
    prompts = []

    def chat(system, user):
        prompts.append(user)
        return "1 | c02 | angry | 0.5 | - | shouting from off-panel | -"

    took = llm_pass.run(script, bubbles, scene, cast, chat)
    assert (
        "nobody drawn; in this scene: c01 (Rook), c02 (Vale); balloon with a tail"
        in prompts[0]
    )
    assert took["speaker"] == 1 and script["lines"][0]["speaker"] == "c02"
    assert script["lines"][0]["llm"]["why"] == "shouting from off-panel"
