"""The Everything tab: every record held on a subject in one place, including
the saved text of each source, so nothing needs the original link to read."""

import pytest
from fastapi.testclient import TestClient

import dossier
import entities.registry as entity_registry
import pages.registry as page_registry
import store
import web_app


def stored_subject():
    return {
        "slug": "angela-merkel",
        "subject": {
            "slug": "angela-merkel",
            "name": "Angela Merkel",
            "entity_type": "person",
            "identity": {"Party": ["CDU"]},
        },
        "timeline": [
            {"date": "2005-11-22", "title": "Chancellor", "kind": "office"},
            {"date": "2021-01-01", "title": "Summit", "kind": "news"},
            {"date": "2021-02-01", "title": "Headline", "kind": "coverage"},
        ],
        "claims": [
            {"text": f"claim {i}", "confidence": "reported", "relevance": 0.5}
            for i in range(250)
        ],
        "quotes": [{"text": f"quote {i}"} for i in range(350)],
        "relations": [{"relation": "member of", "target": "CDU"}],
        "sources": [
            {
                "source_id": "s1",
                "url": "https://bbc.co.uk/a",
                "title": "A",
                "domain": "bbc.co.uk",
                "tier": "major",
                "relevance": 0.8,
                "words": 400,
                "published": "2020-01-01",
                "origin": "ddg_lite",
            }
        ],
        "images": [{"kind": "portrait", "stored": "images/p.jpg"}, {"kind": "logo"}],
        "notes": {"markdown": "mine"},
        "history": [],
        "article": {
            "title": "Angela Merkel",
            "sections": [{"heading": "Lead", "text": "x", "level": 2}],
        },
    }


def _blocks():
    page = page_registry.build_page("everything", stored_subject())
    return {b["kind"]: b for b in page["blocks"]}


def test_every_subject_type_has_an_everything_tab_right_after_overview():
    for entity in entity_registry.all_types():
        assert entity.pages[:2] == ("overview", "everything"), entity.name


def test_the_everything_tab_holds_every_kind_of_record():
    kinds = set(_blocks())
    for kind in (
        "pictures",
        "grouped_facts",
        "article",
        "news",
        "timeline",
        "claims",
        "quotes",
        "relations",
        "source_texts",
        "notes",
    ):
        assert kind in kinds, kind


def test_nothing_on_the_everything_tab_is_cut_off():
    blocks = _blocks()
    assert len(blocks["claims"]["claims"]) == 250
    assert len(blocks["quotes"]["quotes"]) == 350


def test_news_is_not_repeated_in_the_timeline():
    blocks = _blocks()
    assert [e["title"] for e in blocks["timeline"]["events"]] == ["Chancellor"]
    assert blocks["news"]["total"] == 2


def test_the_pictures_block_counts_only_pictures_on_disk():
    assert _blocks()["pictures"]["count"] == 1


def test_the_saved_texts_block_lists_every_source():
    rows = _blocks()["source_texts"]["sources"]
    assert [r["source_id"] for r in rows] == ["s1"]
    assert _blocks()["source_texts"]["slug"] == "angela-merkel"


# --- reading saved text back ----------------------------------------------------


@pytest.fixture
def root(tmp_path):
    d = store.subject_dir("angela-merkel", tmp_path)
    d.mkdir(parents=True)
    store.write_json(d / dossier.FILES["subject"], {"slug": "angela-merkel"})
    store.write_text_bundle(
        d, {"s1": "Merkel led Germany for sixteen years.", "s2": ""}
    )
    return tmp_path


def test_saved_texts_are_listed_with_their_word_counts(root):
    assert dossier.saved_texts("angela-merkel", root) == {"s1": 6}


def test_one_saved_text_is_read_back_whole(root):
    assert (
        dossier.saved_text("angela-merkel", "s1", root)
        == "Merkel led Germany for sixteen years."
    )


def test_nothing_is_read_for_an_unknown_source_subject_or_unsafe_name(root):
    assert dossier.saved_text("angela-merkel", "nope", root) is None
    assert dossier.saved_text("nobody", "s1", root) is None
    assert dossier.saved_text("..", "s1", root) is None
    assert dossier.saved_texts("..", root) == {}


def test_the_saved_text_routes(monkeypatch):
    monkeypatch.setattr(dossier, "saved_texts", lambda slug, root=None: {"s1": 6})
    monkeypatch.setattr(
        dossier,
        "saved_text",
        lambda slug, source_id, root=None: "hello" if source_id == "s1" else None,
    )
    client = TestClient(web_app.app)
    assert client.get("/api/subject/x/texts").json() == {"texts": {"s1": 6}}
    found = client.get("/api/subject/x/text/s1")
    assert found.status_code == 200
    assert found.json() == {"source_id": "s1", "text": "hello"}
    assert client.get("/api/subject/x/text/s9").status_code == 404
