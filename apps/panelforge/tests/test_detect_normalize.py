"""The OCR text cleaner: balloon-edge strokes, I read as 1/T/[, the learned
series glossary, and the junk filter for short reads. The samples are real
reads from Bad Born Blood chapters 1-9."""

import json
import types

from panelforge.detect import bubbles as B
from panelforge.detect import normalize as N


def _cand(raw, conf):
    return types.SimpleNamespace(raw=N.clean_raw(raw), conf=conf, balloon=object())


def test_balloon_edge_strokes_are_removed():
    assert (
        N.normalize("/~ CLOSE COMBAT '\\ WEAPONS ARE YOUR SPECIALTY.")
        == "Close combat weapons are your specialty."
    )
    assert N.normalize('/7 YOU SHOULD "\\ BE COMPETING') == "You should be competing"
    assert (
        N.normalize("N \" - = IF THE PALADIN CAME OUT ON TOP, I'M SCREWED! & = S s 2")
        == "If the paladin came out on top, I'm screwed!"
    )
    assert (
        N.normalize("WHAT ARE YOU... GONNA DO NOW~?") == "What are you... gonna do now?"
    )


def test_the_pronoun_i_read_as_1_t_or_bracket():
    assert N.normalize("THOUGH 1 GUESS SO.") == "Though I guess so."
    assert N.normalize("LIKE T SAID BEFORE.") == "Like I said before."
    assert N.normalize("WHATEVER [T TAKES!!") == "Whatever it takes!!"
    assert (
        N.normalize("OH, SORRY. 1S THIS A BAD TIME?")
        == "Oh, sorry. Is this a bad time?"
    )
    assert N.normalize("ONLY 1 LEFT.") == "Only 1 left."  # a real number stays


def test_stray_letters_go_but_stutters_initials_and_a_i_stay():
    assert N.normalize("V THAT N KID'S FROM A FAMILY.") == "That kid's from a family."
    assert N.normalize("N-NO WAY.") == "N-no way."
    assert N.normalize("MR. K SAID SO.") == "Mr. K said so."
    assert N.normalize("AS I SAID, A MAN.") == "As I said, a man."


def test_glossary_learned_from_the_series_keeps_names_whole(tmp_path):
    series = tmp_path / "s"
    for c in ("0001", "0002", "0003"):
        d = series / "chapters" / c
        d.mkdir(parents=True)
        (d / "bubbles.json").write_text(
            json.dumps({"bubbles": [{"text_raw": "BELLATO AND CORITE OUTPOST"}]})
        )
    (series / "cast.json").write_text(json.dumps({"cast": [{"name": "Ilay"}]}))
    try:
        learned = N.learn_glossary(series / "chapters" / "0004")
        assert {"bellato", "corite", "ilay"} <= learned
        assert N.normalize("THOUGH I GUESS BELLATO AND CORITES...") == (
            "Though I guess Bellato and Corites..."
        )
        assert N.normalize("SEE YOU, ILAY.") == "See you, Ilay."
        # a person's own words: added ones always count, banned ones never
        (series / "glossary.json").write_text(
            json.dumps({"words": ["Novus"], "banned": ["corite"]})
        )
        learned = N.learn_glossary(series / "chapters" / "0004")
        assert "novus" in learned and "corite" not in learned
    finally:
        N.GLOSSARY.clear()


def test_two_letter_split_pieces_are_only_function_words():
    # the tesseract list holds "wu" and "rt", which turned WURT into "wu rt"
    assert N.split_glued("WURT") == ["WURT"]
    assert N.split_glued("ABLETO") == ["ABLE", "TO"]


def test_short_and_stroke_filled_reads_are_junk_but_real_words_pass():
    for raw, conf in [
        ("tIﬂ' \\i\\' \\\\\\ gl..\\- RY '", 0.472),
        ("N 9 AN", 0.599),
        ("! -dl", 0.715),
        ("!.-%'", 0.575),
        ("Rt - I", 0.475),
        ("D) MOR", 0.549),
    ]:
        assert not B.looks_like_text(_cand(raw, conf)), raw
    for raw, conf in [
        ("FOOL", 0.689),
        ("HEAD.", 0.67),
        ("HAHA!", 0.556),
        ("YEAH.", 0.877),
        ("BUT I-/", 0.692),  # speech cut off mid-word (chapter 7)
    ]:
        assert B.looks_like_text(_cand(raw, conf)), raw


def test_glossary_words_split_by_the_reader_are_joined_and_glued_t_is_i():
    N.GLOSSARY.update({"bellato"})
    try:
        assert N.normalize("CORA AND BELLA TO?") == "Cora and Bellato?"
    finally:
        N.GLOSSARY.clear()
    assert N.normalize("THAVE TO DO SOMETHING!") == "I have to do something!"
    assert N.normalize("THINK ABOUT IT.") == "Think about it."
    assert (
        N.normalize("SERIOUSLY...?7 YOU ARE KIDDING") == "Seriously...? You are kidding"
    )
    assert N.normalize("ARE YOU STILL LIVING...7") == "Are you still living..."
