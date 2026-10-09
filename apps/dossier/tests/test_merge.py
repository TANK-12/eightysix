"""Accumulation rules: a second run must add without duplicating or losing.

These use a temporary data root, so they never touch the real library on AN3.
"""

import pytest

import dossier
import store


@pytest.fixture
def root(tmp_path):
    (tmp_path / store.SUBJECTS).mkdir(parents=True)
    return tmp_path


def result(
    name="Angela Merkel",
    sources=None,
    claims=None,
    timeline=None,
    quotes=None,
    phase="quick",
):
    return {
        "name": name,
        "slug": store.slugify(name),
        "entity_type": "person",
        "identity": {"qid": "Q567", "description": "chancellor of Germany"},
        "context_terms": ["politician", "Germany"],
        "timeline": (
            timeline
            if timeline is not None
            else [
                {
                    "date": "2005-11-22",
                    "end": "",
                    "title": "Chancellor of Germany",
                    "kind": "office",
                    "detail": "",
                    "source_id": "wikidata",
                    "url": "u",
                },
            ]
        ),
        "quotes": (
            quotes
            if quotes is not None
            else [
                {
                    "text": "We can do this",
                    "citation": "Speech, 2015",
                    "url": "u",
                    "sourced": True,
                },
            ]
        ),
        "relations": [{"relation": "member of", "target": "CDU", "url": "u"}],
        "claims": claims if claims is not None else [],
        "sources": (
            sources
            if sources is not None
            else [
                {
                    "source_id": "s1",
                    "url": "https://bbc.co.uk/a",
                    "title": "A",
                    "domain": "bbc.co.uk",
                    "tier": "major",
                    "origin": "ddg_lite",
                    "published": "2020-01-01",
                    "relevance": 0.8,
                    "cluster_id": "c1",
                    "words": 400,
                },
            ]
        ),
        "texts": {"s1": "some article text"},
        "report": {"phase": phase, "seconds": 1.0},
        "updated": "2026-09-09",
    }


def claim(
    text,
    source_id,
    domain,
    span="Merkel led Germany for sixteen years.",
    tier="major",
    cluster="c1",
):
    return {
        "text": text,
        "confidence": "reported",
        "independent_sources": 1,
        "relevance": 0.8,
        "conflicts": [],
        "evidence": [
            {
                "source_id": source_id,
                "cluster_id": cluster,
                "domain": domain,
                "tier": tier,
                "relevance": 0.8,
                "span": span,
                "url": f"https://{domain}/x",
            }
        ],
    }


def test_saving_the_same_result_twice_changes_nothing(root):
    dossier.save(result(), root)
    changes = dossier.save(result(), root)
    assert changes["sources_added"] == 0
    assert changes["timeline_added"] == 0
    assert changes["quotes_added"] == 0
    stored = dossier.load("angela-merkel", root)
    assert len(stored["sources"]) == 1
    assert len(stored["timeline"]) == 1
    assert len(stored["quotes"]) == 1


def test_a_second_run_adds_new_material_and_keeps_the_old(root):
    dossier.save(result(), root)
    second = result(
        sources=[
            {
                "source_id": "s2",
                "url": "https://reuters.com/b",
                "title": "B",
                "domain": "reuters.com",
                "tier": "major",
                "origin": "ddg_lite",
                "published": "2021-01-01",
                "relevance": 0.7,
                "cluster_id": "c2",
                "words": 300,
            }
        ],
        timeline=[
            {
                "date": "2021-12-08",
                "end": "",
                "title": "Left office",
                "kind": "office",
                "detail": "",
                "source_id": "wikidata",
                "url": "u",
            }
        ],
        quotes=[
            {
                "text": "A different remark",
                "citation": "Interview",
                "url": "u",
                "sourced": True,
            }
        ],
    )
    changes = dossier.save(second, root)
    assert changes["sources_added"] == 1
    stored = dossier.load("angela-merkel", root)
    # Nothing from the first run may have been dropped.
    assert {s["source_id"] for s in stored["sources"]} == {"s1", "s2"}
    assert len(stored["timeline"]) == 2
    assert len(stored["quotes"]) == 2


def test_restated_claim_gains_evidence_rather_than_duplicating(root):
    dossier.save(
        result(
            claims=[
                claim(
                    "Merkel served as chancellor of Germany for sixteen years",
                    "s1",
                    "bbc.co.uk",
                )
            ]
        ),
        root,
    )
    dossier.save(
        result(
            claims=[
                claim(
                    "Merkel was Germany's chancellor for 16 years",
                    "s2",
                    "reuters.com",
                    cluster="c2",
                )
            ]
        ),
        root,
    )
    stored = dossier.load("angela-merkel", root)
    assert len(stored["claims"]) == 1, "the same fact was stored twice"
    only = stored["claims"][0]
    assert len(only["evidence"]) == 2
    assert only["independent_sources"] == 2


def test_notes_survive_every_research_run(root):
    dossier.save(result(), root)
    dossier.save_notes("angela-merkel", "My own reading of her record.", root)
    dossier.save(result(), root)
    dossier.save(result(phase="deep"), root)
    stored = dossier.load("angela-merkel", root)
    assert stored["notes"]["markdown"] == "My own reading of her record."


def test_history_records_every_run(root):
    dossier.save(result(), root)
    dossier.save(result(), root)
    stored = dossier.load("angela-merkel", root)
    assert len(stored["history"]) == 2
    assert "changes" in stored["history"][0]


def test_depth_upgrades_to_deep_and_never_downgrades(root):
    dossier.save(result(phase="deep"), root)
    assert dossier.load("angela-merkel", root)["subject"]["depth"] == "deep"
    dossier.save(result(phase="quick"), root)
    assert dossier.load("angela-merkel", root)["subject"]["depth"] == "deep"


def test_index_reflects_what_is_on_disk(root):
    dossier.save(result(), root)
    dossier.save(result(name="Olaf Scholz"), root)
    rows = dossier.library(root)
    assert {r["slug"] for r in rows} == {"angela-merkel", "olaf-scholz"}


def test_regrade_recomputes_verdicts_without_touching_evidence(root):
    """When the corroboration rules change, stored verdicts must be able to
    catch up without refetching - and without losing anything."""
    dossier.save(
        result(
            claims=[
                claim("Merkel led Germany for sixteen years", "s1", "bbc.co.uk"),
            ]
        ),
        root,
    )
    stored = store.read_json(
        store.subject_dir("angela-merkel", root) / "claims.json", []
    )
    # Corrupt the stored verdict the way a rule change would.
    stored[0]["confidence"] = "disputed"
    store.write_json(store.subject_dir("angela-merkel", root) / "claims.json", stored)

    report = dossier.regrade("angela-merkel", root)
    after = dossier.load("angela-merkel", root)["claims"]
    assert report["claims"] == 1
    assert after[0]["confidence"] == "reported"
    assert len(after[0]["evidence"]) == 1, "regrading must not touch the evidence"
    assert after[0]["evidence"][0]["span"].startswith("Merkel led Germany")


def test_an_unreadable_subject_does_not_vanish_from_the_index(root):
    """Seen for real on the exfat USB drive: a transient read failure made
    reindex write an empty index over a good one. Losing the library because a
    file was momentarily busy is the exact failure this app must not have."""
    dossier.save(result(), root)
    assert len(dossier.library(root)) == 1

    # Corrupt subject.json the way a half-written or busy file reads.
    subject_file = store.subject_dir("angela-merkel", root) / "subject.json"
    subject_file.write_text("{ this will not parse", encoding="utf-8")

    rows = dossier.reindex(root)
    assert len(rows) == 1, "the subject was dropped when its file would not read"
    assert rows[0]["name"] == "Angela Merkel"
    assert len(dossier.library(root)) == 1


def test_an_empty_index_beside_real_subjects_is_rebuilt(root):
    dossier.save(result(), root)
    store.write_json(root / "index.json", [])
    assert len(dossier.library(root)) == 1, "a stale empty index was believed"


def test_a_genuinely_empty_library_stays_empty(root):
    assert dossier.library(root) == []
    assert dossier.reindex(root) == []


def test_article_text_is_merged_into_one_bundle(root):
    """One file per source wasted 256KB of exfat cluster on a 181-byte extract;
    675 of them turned 3.9MB of text into 303MB on disk."""
    first = result()
    first["texts"] = {"s1": "first article text"}
    dossier.save(first, root)

    second = result()
    second["texts"] = {"s2": "second article text"}
    changes = dossier.save(second, root)

    d = store.subject_dir("angela-merkel", root)
    bundle = store.read_text_bundle(d)
    assert bundle == {"s1": "first article text", "s2": "second article text"}
    assert changes["texts_stored"] == 1
    assert not (d / "text").exists() or not list((d / "text").glob("*.txt.gz"))


def test_saving_the_same_text_twice_stores_it_once(root):
    payload = result()
    payload["texts"] = {"s1": "an article"}
    dossier.save(payload, root)
    changes = dossier.save(payload, root)
    assert changes["texts_stored"] == 0
    assert store.read_text_bundle(store.subject_dir("angela-merkel", root)) == {
        "s1": "an article"
    }


def test_legacy_per_source_text_files_migrate_without_loss(root):
    dossier.save(result(), root)
    d = store.ensure_subject("angela-merkel", root)
    (d / "text").mkdir(exist_ok=True)
    store.write_text_gz(d / "text" / "old1.txt.gz", "text from the old layout")
    store.write_text_gz(d / "text" / "old2.txt.gz", "another old one")

    moved = dossier.migrate_text_files("angela-merkel", root)
    assert moved == 2
    bundle = store.read_text_bundle(d)
    assert bundle["old1"] == "text from the old layout"
    assert bundle["old2"] == "another old one"
    assert not (d / "text").exists(), "the legacy directory should be gone"

    # Running it again is harmless.
    assert dossier.migrate_text_files("angela-merkel", root) == 0
