"""Casting: the model's look verdicts become distinct, fitting voices."""

from PIL import Image

from panelforge.audio import casting

VOICES = [
    "af_alloy",
    "af_bella",
    "af_heart",
    "af_kore",
    "af_nicole",
    "af_sky",
    "am_adam",
    "am_echo",
    "am_fenrir",
    "am_michael",
    "am_onyx",
    "am_puck",
    "am_santa",
]


def _cast(tmp_path):
    (tmp_path / "assets/cast").mkdir(parents=True)
    doc = {"narrator": {"voice": {"kokoro": "am_santa"}}, "cast": []}
    for i, panels in enumerate([40, 30, 20, 5], 1):
        cid = f"c{i:02d}"
        (tmp_path / f"assets/cast/{cid}").mkdir()
        Image.new("RGB", (60, 80), "grey").save(tmp_path / f"assets/cast/{cid}/s1.png")
        doc["cast"].append(
            {
                "id": cid,
                "name": f"character {i}",
                "samples": [f"assets/cast/{cid}/s1.png"],
                "panels": list(range(panels)),
                "voice": None,
            }
        )
    # the lead's voice was chosen by hand and must stay
    doc["cast"][0]["voice"] = {"kokoro": "af_alloy", "speed": 1.0, "pitch": 0.0}
    return doc


def test_parse_look_reads_the_three_fields_loosely():
    assert casting.parse_look("male | adult | dark") == {
        "gender": "male",
        "age": "adult",
        "timbre": "dark",
    }
    assert casting.parse_look("Female | Old woman | soft voice\n") == {
        "gender": "female",
        "age": "old",
        "timbre": "soft",
    }
    assert casting.parse_look("a boy") is None


def test_every_described_character_gets_a_distinct_fitting_voice(tmp_path):
    doc = _cast(tmp_path)
    answers = {
        "character 2": "male | adult | dark",
        "character 3": "male | old | dark",
        "character 4": "female | child | bright",
    }
    asked = []

    def chat_image(system, user, url):
        asked.append(user)
        assert url.startswith("data:image/jpeg;base64,")
        return next(v for k, v in answers.items() if k in user)

    result = casting.cast_voices(doc, tmp_path, chat_image, VOICES)
    assert result["voices"] == 3 and len(asked) == 3  # the lead was not asked
    by_id = {c["id"]: c for c in doc["cast"]}
    assert by_id["c01"]["voice"]["kokoro"] == "af_alloy"  # untouched
    v2, v3, v4 = (by_id[c]["voice"] for c in ("c02", "c03", "c04"))
    # both dark men: the more frequent one gets the first dark voice, the
    # other the next; neither takes the narrator's am_santa
    assert v2["kokoro"] == "am_onyx" and v3["kokoro"] == "am_fenrir"
    assert v3["pitch"] < 0 and v3["speed"] < 1.0  # old
    assert v4["kokoro"] == "af_bella" and v4["pitch"] == 2.0  # bright girl
    assert all(v["source"] == "model" for v in (v2, v3, v4))
    assert len({v2["kokoro"], v3["kokoro"], v4["kokoro"]}) == 3


def test_a_model_chosen_voice_is_rechosen_but_a_hand_one_is_not(tmp_path):
    doc = _cast(tmp_path)
    doc["cast"][1]["voice"] = {"kokoro": "am_puck", "source": "model"}
    doc["cast"][2]["voice"] = {"kokoro": "am_echo"}  # by hand
    seen = []

    def chat_image(system, user, url):
        seen.append(user)
        return "female | teen | soft"

    casting.cast_voices(doc, tmp_path, chat_image, VOICES, only={"c02", "c03"})
    assert len(seen) == 1 and "character 2" in seen[0]
    assert doc["cast"][1]["voice"]["kokoro"] == "af_nicole"
    assert doc["cast"][2]["voice"]["kokoro"] == "am_echo"


def test_more_men_than_voices_share_with_a_pitch_offset(tmp_path):
    doc = {"narrator": {"voice": {"kokoro": "am_santa"}}, "cast": []}
    for i in range(1, 6):
        doc["cast"].append(
            {"id": f"c{i:02d}", "panels": list(range(50 - i)), "voice": None}
        )
    looks = {
        f"c{i:02d}": {"gender": "male", "age": "adult", "timbre": "dark"}
        for i in range(1, 6)
    }
    n = casting.assign_voices(
        doc, looks, ["am_onyx", "am_fenrir", "am_santa", "bm_george"]
    )
    assert n == 5
    voices = [(c["voice"]["kokoro"], c["voice"]["pitch"]) for c in doc["cast"]]
    # three distinct voices first (the British man after the Americans),
    # then the fitting ones again, told apart by pitch
    assert voices[:3] == [("am_onyx", 0.0), ("am_fenrir", 0.0), ("bm_george", 0.0)]
    assert voices[3][0] == "am_onyx" and voices[3][1] == -0.8
    assert voices[4][0] == "am_fenrir" and voices[4][1] == -0.8
    assert "shared" in doc["cast"][3]["voice"]["why"]
    assert all(v != "am_santa" for v, _ in voices)  # the narrator's, never shared
