"""Mood picking and the persona registry, checked against things Emerson has
actually typed (typos included), so the right persona answers."""

import json

import pytest

import personas

REAL = [
    ("still bloddy not working fix it", "fix"),
    ("the gemoetry dash game music dont work", "fix"),
    (
        "so the picels resolutyion selecter was fixed but now the tsxt for the upscale is whit on whirte",
        "fix",
    ),
    ("so tldr what have you done", "status"),
    ("so hows it going", "status"),
    ("is everything done?", "status"),
    ("whats usint th ecpu?", "status"),
    ("make more and  more", "build"),
    ("add 15 more feautre", "build"),
    (
        "i want a cool astronmy and galaxy and solar system map and gravity game and se tons of tokens",
        "build",
    ),
    ("im bored", "downtime"),
    ("hey hows your day", "downtime"),
    ("should i tunr on usage tokens", "plan"),
    ("are you sure thats true", "check"),
    ("can you double check the benchmark numbers", "check"),
    ("look up the new tts models and give me sources", "check"),
    ("research which drone is best", "check"),
    ("open the source code for the hub", "default"),
    ("where are the source files", "default"),
    ("edit apps/crewroom/sources/helpers.py", "default"),
    ("use the crewroom sources module", "default"),
    ("the board is the source of truth", "default"),
    ("open source models for tts", "default"),
    ("the researcher persona", "default"),
    ("u sure?", "check"),
    ("is that accurate", "check"),
    ("can you confirm this", "check"),
    ("read the manifest", "default"),
]


@pytest.mark.parametrize("text,mood", REAL)
def test_real_messages_get_the_right_mood(text, mood):
    assert personas.pick_mood(text) == mood


def test_every_registry_persona_is_complete_and_moods_are_covered():
    everyone = personas.load()
    assert {"tetsu", "kira", "shizu", "archchan", "yui", "ren", "shiori"} <= set(
        everyone
    )
    covered = set()
    for p in everyone.values():
        assert p["avatar"]["kind"] in ("live2d", "puppet")
        assert p["voice"] and p["prompt"] and p["reactions"]["done"]
        covered |= set(p["moods"])
    assert covered >= set(personas.MOODS)


def test_downtime_alternates_unless_one_is_chosen(tmp_path):
    cast = personas.Personas(tmp_path)
    picks = {cast.for_message("im bored")[0]["id"] for _ in range(4)}
    assert picks == {"yui", "ren"}
    cast.save_prefs({"downtime": "yui"})
    assert {cast.for_message("im bored")[0]["id"] for _ in range(4)} == {"yui"}


def test_overrides_swap_avatar_and_voice_and_bad_ones_are_refused(tmp_path):
    cast = personas.Personas(tmp_path)
    cast.save_prefs(
        {
            "overrides": {
                "kira": {"avatar": {"kind": "live2d", "id": "haru"}, "voice": "am_echo"}
            }
        }
    )
    kira = cast.all()["kira"]
    assert (
        kira["avatar"] == {"kind": "live2d", "id": "haru"}
        and kira["voice"] == "am_echo"
    )
    for bad in [
        {"pinned": "nobody"},
        {"overrides": {"kira": {"avatar": {"kind": "gif", "id": "x"}}}},
        {"overrides": {"kira": {"avatar": {"kind": "live2d", "id": "../x"}}}},
    ]:
        with pytest.raises(ValueError):
            cast.save_prefs(bad)
    assert json.loads((tmp_path / "personas.json").read_text())["pinned"] == "auto"


def test_the_avatar_is_off_until_turned_on_and_the_choice_is_kept(tmp_path):
    # A21: Emerson does not want the Live2D stage running by default.
    book = personas.Personas(tmp_path)
    assert book.prefs()["avatar"] is False
    assert book.save_prefs({"avatar": True})["avatar"] is True
    assert personas.Personas(tmp_path).prefs()["avatar"] is True
    assert book.save_prefs({"avatar": False})["avatar"] is False


def test_a_fact_check_question_is_answered_by_shiori(tmp_path):
    cast = personas.Personas(tmp_path)
    persona, mood = cast.for_message("are you sure that's true? double check it")
    assert (persona["id"], mood) == ("shiori", "check")
    assert "Shiori" in cast.roster_prompt()
