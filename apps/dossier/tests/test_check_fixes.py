"""Problems found by the full check of the real library on 2026-09-15.

Each test reproduces one thing that was observed going wrong on real data.
"""

import httpx
import pytest

import dossier
import jobqueue
import llm
import store
from pages import common, record
from research import claims as claims_mod
from research import pipeline
from research.scoring import SubjectProfile
from sources.properties import grouped


def _result(report):
    return {
        "name": "Angela Merkel",
        "slug": "angela-merkel",
        "entity_type": "person",
        "identity": {"qid": "Q567"},
        "context_terms": ["politician"],
        "timeline": [],
        "quotes": [],
        "relations": [],
        "claims": [],
        "sources": [],
        "texts": {},
        "report": report,
        "updated": "2026-09-15",
    }


# --- repeated values in a fact row -------------------------------------------


def test_a_fact_row_names_each_value_once():
    stored = {
        "subject": {
            "identity": {
                "party": ["Republican Party", "Democratic Party", "Republican Party"]
            }
        }
    }
    block = common.facts_block(stored, [("party", "Party")])
    assert block["rows"] == [
        {"label": "Party", "value": "Republican Party, Democratic Party"}
    ]


def test_a_grouped_fact_row_names_each_value_once():
    panels = grouped(
        {"Party": ["Republican Party", "Reform Party", "Republican Party"]}, "person"
    )
    rows = [r for p in panels for r in p["rows"] if r["label"] == "Party"]
    assert rows == [{"label": "Party", "value": "Republican Party, Reform Party"}]


# --- the Record page said "no claims yet" above real claims --------------------


def test_record_page_has_no_empty_disputed_block_above_real_claims():
    stored = {"claims": [{"text": "a b c", "confidence": "reported"}]}
    claim_blocks = [b for b in record.build(stored)["blocks"] if b["kind"] == "claims"]
    assert len(claim_blocks) == 1
    assert len(claim_blocks[0]["claims"]) == 1


def test_record_page_still_leads_with_disputes_when_there_are_some():
    stored = {
        "claims": [
            {"text": "x y z", "confidence": "disputed"},
            {"text": "a b c", "confidence": "verified"},
        ]
    }
    first = record.build(stored)["blocks"][0]
    assert first["kind"] == "claims"
    assert [c["confidence"] for c in first["claims"]] == ["disputed"]


# --- a verified claim contradicted its own quote -------------------------------

TRUMP_SPAN = (
    "Presenting himself as a political outsider, Trump won the 2016 presidential "
    "election against Democratic Party nominee Hillary Clinton."
)


@pytest.mark.parametrize(
    "statement,span,ok",
    [
        (
            "Donald Trump won the 2024 presidential election decisively",
            TRUMP_SPAN,
            False,
        ),
        ("Trump won the 2016 presidential election", TRUMP_SPAN, True),
        (
            "She served as chancellor for 16 years",
            "Merkel served as chancellor for 16 years.",
            True,
        ),
        (
            "She served as chancellor for 18 years",
            "Merkel served as chancellor for 16 years.",
            False,
        ),
        (
            "The city had 1,200,000 residents",
            "By then 1200000 people lived in the city.",
            True,
        ),
        (
            "He graduated from the University of Pennsylvania",
            "He graduated from the University of Pennsylvania with a degree.",
            True,
        ),
    ],
)
def test_a_claim_must_not_state_figures_its_quote_does_not(statement, span, ok):
    assert claims_mod.claim_matches_span(statement, span) is ok


def test_extraction_drops_a_claim_whose_quote_gives_a_different_year(monkeypatch):
    filler = (
        "Donald Trump is an American politician and businessman who has been "
        "active in public life for decades and remains a subject of very wide "
        "coverage in newspapers, books and broadcasts around the world. "
    )
    text = TRUMP_SPAN + " " + filler * 3
    monkeypatch.setattr(
        llm,
        "chat_json",
        lambda *a, **k: [
            {
                "claim": "Donald Trump won the 2024 presidential election decisively",
                "anchor": "Presenting himself as a political outsider,",
            },
            {
                "claim": "Donald Trump won the 2016 presidential election",
                "anchor": "Presenting himself as a political outsider,",
            },
        ],
    )
    found = claims_mod.extract_claims(
        {"text": text, "domain": "wikipedia.org"},
        SubjectProfile(name="Donald Trump"),
        "s1",
        "c1",
        0.9,
    )
    assert [c.text for c in found] == [
        "Donald Trump won the 2016 presidential election"
    ]


# --- failed deep dives were recorded as deep ----------------------------------


@pytest.fixture
def root(tmp_path):
    (tmp_path / store.SUBJECTS).mkdir(parents=True)
    return tmp_path


def test_a_deep_dive_whose_extraction_failed_is_not_recorded_as_deep(root):
    dossier.save(_result({"phase": "deep", "claims_complete": False}), root)
    assert dossier.load("angela-merkel", root)["subject"]["depth"] == "quick"


def test_a_deep_dive_whose_extraction_finished_is_recorded_as_deep(root):
    dossier.save(_result({"phase": "deep", "claims_complete": True}), root)
    assert dossier.load("angela-merkel", root)["subject"]["depth"] == "deep"


def test_a_failed_deep_dive_never_downgrades_an_earlier_good_one(root):
    dossier.save(_result({"phase": "deep", "claims_complete": True}), root)
    dossier.save(_result({"phase": "deep", "claims_complete": False}), root)
    assert dossier.load("angela-merkel", root)["subject"]["depth"] == "deep"


# --- one Jan error was treated as Jan being off --------------------------------


def _fake_jan(monkeypatch, handler):
    real = httpx.Client
    monkeypatch.setattr(
        llm.httpx,
        "Client",
        lambda **kw: real(transport=httpx.MockTransport(handler), **kw),
    )
    monkeypatch.setattr(llm, "resolve", lambda tier: "test-model")
    monkeypatch.setattr(llm, "RETRY_PAUSE", 0)


def test_a_server_error_is_retried_then_reported_as_that_request_failing(
    monkeypatch,
):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            500, json={"error": {"message": "does not match the peg-native format"}}
        )

    _fake_jan(monkeypatch, handler)
    with pytest.raises(llm.JanRequestFailed):
        llm.chat("reason", [{"role": "user", "content": "x"}])
    assert len(calls) == 2


def test_a_retry_that_succeeds_returns_the_answer(monkeypatch):
    replies = [
        httpx.Response(500, json={}),
        httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]}),
    ]
    _fake_jan(monkeypatch, lambda request: replies.pop(0))
    assert llm.chat("reason", [{"role": "user", "content": "x"}]) == "ok"


def test_jan_being_off_is_not_mistaken_for_one_failed_request(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("Connection refused")

    _fake_jan(monkeypatch, handler)
    with pytest.raises(llm.JanUnavailable) as caught:
        llm.chat("reason", [{"role": "user", "content": "x"}])
    assert not isinstance(caught.value, llm.JanRequestFailed)


# --- one failed article ended every claim for the subject ----------------------


def _rows(n):
    return [
        {"source_id": f"s{i}", "cluster_id": f"c{i}", "relevance": 0.9}
        for i in range(n)
    ]


def test_one_failed_article_does_not_stop_the_rest():
    report = pipeline.RunReport(phase="deep")

    def extract(row, *rest):
        if row["source_id"] == "s0":
            raise llm.JanRequestFailed("Jan returned 500: peg-native format")
        return [row["source_id"]]

    found = pipeline.read_articles(_rows(3), SubjectProfile(name="X"), report, extract)
    assert found == ["s1", "s2"]
    assert report.claims_complete is False
    assert any("500" in note for note in report.notes)


def test_jan_going_away_stops_reading_and_marks_extraction_incomplete():
    report = pipeline.RunReport(phase="deep")

    def extract(row, *rest):
        if row["source_id"] == "s1":
            raise llm.JanUnavailable("Jan unreachable")
        return [row["source_id"]]

    found = pipeline.read_articles(_rows(3), SubjectProfile(name="X"), report, extract)
    assert found == ["s0"]
    assert report.claims_complete is False


def test_reading_every_article_marks_extraction_complete():
    report = pipeline.RunReport(phase="deep")
    found = pipeline.read_articles(
        _rows(2), SubjectProfile(name="X"), report, lambda row, *rest: [1]
    )
    assert found == [1, 1]
    assert report.claims_complete is True


# --- the Jobs tab said "Failures: none" -----------------------------------------


def test_a_deep_dive_that_finished_without_its_claims_counts_as_a_failure():
    job = {
        "status": "done",
        "report": {
            "phase": "deep",
            "claims_complete": False,
            "notes": [
                "GDELT was rate-limited or unreachable; skipped",
                "Claim extraction stopped: Jan unreachable",
            ],
        },
    }
    assert jobqueue._incomplete(job) == (
        "finished without all its claims: Claim extraction stopped: Jan unreachable"
    )


def test_a_good_deep_dive_and_an_older_job_are_not_failures():
    good = {"status": "done", "report": {"phase": "deep", "claims_complete": True}}
    older = {"status": "done", "report": {"phase": "deep"}}
    quick = {"status": "done", "report": {"phase": "quick", "claims_complete": False}}
    assert not any(jobqueue._incomplete(j) for j in (good, older, quick))
