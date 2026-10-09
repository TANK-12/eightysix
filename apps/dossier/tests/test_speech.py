"""Speaking a dossier. The rule under test: nothing is spoken that would not
have been shown in writing."""

import dossier
import store
from research import speech


def hold(tmp_path, name, timeline=(), claims=(), entity_type="person"):
    slug = store.slugify(name)
    d = store.ensure_subject(slug, tmp_path)
    store.write_json(
        d / dossier.FILES["subject"],
        {
            "slug": slug,
            "name": name,
            "entity_type": entity_type,
            "depth": "quick",
            "identity": {"description": "a test subject"},
        },
    )
    store.write_json(d / dossier.FILES["timeline"], list(timeline))
    store.write_json(d / dossier.FILES["claims"], list(claims))
    dossier.reindex(tmp_path)
    return slug


def event(date, title, kind="office"):
    return {"date": date, "title": title, "kind": kind, "url": "u", "detail": ""}


# --- what reaches the voice -------------------------------------------------


def test_citation_markers_are_never_spoken():
    """'[4]' is not a sound. It has to go before rendering."""
    assert speech.speakable("She was chancellor [4][9]. Then she left [12].") == (
        "She was chancellor. Then she left."
    )


def test_stripping_markers_does_not_mangle_ordinary_brackets():
    assert speech.speakable("The party (CDU) won [3].") == "The party (CDU) won."


def test_nothing_to_say_is_refused_rather_than_rendered(tmp_path):
    out = speech.render("   [4]  ", "empty", root=tmp_path)
    assert out["ok"] is False and "nothing to say" in out["error"].lower()


def test_dates_are_turned_into_something_readable():
    assert speech._spoken_date("1990-10-03") == "3 October 1990"
    assert speech._spoken_date("2005-11") == "November 2005"
    assert speech._spoken_date("1954") == "1954"
    assert speech._spoken_date("nonsense") == "nonsense"


# --- the tour ---------------------------------------------------------------


def test_a_tour_reads_the_record_in_date_order(tmp_path):
    slug = hold(
        tmp_path,
        "Someone",
        timeline=[
            event("2005-11-22", "became chancellor"),
            event("1990-12-20", "elected to parliament"),
        ],
    )
    script = speech.tour_script(slug, root=tmp_path)
    said = [l["text"] for l in script["lines"] if l["kind"] == "event"]
    assert said[0].startswith("20 December 1990")
    assert said[1].startswith("22 November 2005")


def test_a_persons_tour_leaves_out_economic_indicators(tmp_path):
    """Narrating 'government debt: 20.9%' between two elections is noise."""
    slug = hold(
        tmp_path,
        "Someone",
        timeline=[
            event("1990", "Government debt: 20.9%", kind="indicator"),
            event("1991", "became a minister", kind="office"),
        ],
    )
    text = speech.tour_script(slug, root=tmp_path)["text"]
    assert "Government debt" not in text
    assert "became a minister" in text


def test_a_countrys_tour_keeps_them(tmp_path):
    """For a country those indicators are the story, not an interruption."""
    slug = hold(
        tmp_path,
        "Someland",
        entity_type="country",
        timeline=[
            event("1990", "Government debt: 20.9%", kind="indicator"),
        ],
    )
    assert "Government debt" in speech.tour_script(slug, root=tmp_path)["text"]


def test_only_corroborated_claims_are_read_out(tmp_path):
    slug = hold(
        tmp_path,
        "Someone",
        claims=[
            {"text": "This one is checked", "confidence": "verified", "evidence": []},
            {"text": "This one is not", "confidence": "reported", "evidence": []},
            {"text": "This one is contested", "confidence": "disputed", "evidence": []},
        ],
    )
    text = speech.tour_script(slug, root=tmp_path)["text"]
    assert "This one is checked" in text
    assert "This one is not" not in text
    assert "This one is contested" not in text


def test_a_tour_says_that_disputed_claims_exist_without_reading_them(tmp_path):
    slug = hold(
        tmp_path,
        "Someone",
        claims=[
            {"text": "contested thing", "confidence": "disputed", "evidence": []},
        ],
    )
    text = speech.tour_script(slug, root=tmp_path)["text"]
    assert "disputed" in text and "contested thing" not in text


def test_a_subject_with_no_dossier_is_an_error_not_a_crash(tmp_path):
    out = speech.tour_script("nobody", root=tmp_path)
    assert out["error"] and out["lines"] == []


# --- what the environment offers -------------------------------------------


def test_availability_reports_what_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(speech, "PIPER", tmp_path / "no-piper")
    monkeypatch.setattr(speech, "VOICES_DIR", tmp_path / "no-voices")
    state = speech.available()
    assert state["ready"] is False
    assert any("Piper" in m for m in state["missing"])


def test_rendering_refuses_cleanly_when_the_voice_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(speech, "VOICES_DIR", tmp_path / "nowhere")
    out = speech.render("hello", "x", root=tmp_path)
    assert out["ok"] is False and out["path"] == ""
