"""Five years of news, the full article, and the pages they feed.

No network: the portal fixture reproduces the markup of a real month page
(`Portal:Current events/March 2022`) - a topic heading whose links become the
topic chain, events with inline links, citation anchors marked `external`, and
a navbar of external links in the day heading that must not become events.
"""

from datetime import date, timedelta

import dossier
import enrich
import store
from pages import registry as page_registry
from research import news_archive as archive
from research.scoring import SubjectProfile
from sources import news_archive as news_source
from sources.registry import Context
from sources.wikipedia import article_from, split_sections

MONTH_HTML = """<div class="current-events">
<div role="region" class="current-events-main vevent">
 <div class="current-events-heading">
  <span class="summary">March 1, 2022<span style="display:none">(<span class="bday dtstart">2022-03-01</span>)</span></span>
  <ul class="current-events-navbar"><li><a class="external text" href="https://en.wikipedia.org/w/index.php?title=x&amp;action=edit">edit</a></li></ul>
 </div>
 <div class="current-events-content description">
<p><b>Armed conflicts and attacks</b></p>
<ul><li><a href="/wiki/Russo-Ukrainian_War" class="mw-redirect" title="Russo-Ukrainian War">Russo-Ukrainian War</a>
<ul><li>The <a href="/wiki/Armed_Forces_of_Ukraine" title="Armed Forces of Ukraine">Ukrainian army</a> foils a plot against President <a href="/wiki/Volodymyr_Zelenskyy" title="Volodymyr Zelenskyy">Volodymyr Zelenskyy</a>. <a rel="nofollow" class="external text" href="https://www.reuters.com/a">(Reuters)</a> <a class="external text" href="https://www.theguardian.com/b">(<i>The Guardian</i>)</a></li>
<li>A convoy advances toward <a href="/wiki/Kyiv" title="Kyiv">Kyiv</a>. <a class="external text" href="https://www.bbc.com/c">(BBC News)</a></li></ul></li></ul>
<p><b>Politics and elections</b></p>
<ul><li><a href="/wiki/File:X.jpg" title="File:X.jpg">img</a> <a href="/wiki/Zelensky" class="mw-redirect" title="Zelensky">Zelensky</a> addresses the <a href="/wiki/European_Parliament" title="European Parliament">European Parliament</a>. <a class="external text" href="https://apnews.com/d">(AP)</a></li></ul>
 </div>
</div>
</div>"""


class StubFetcher:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def get_json(self, url, api=True, params=None, **kw):
        self.calls.append(dict(params or {}))
        return self.answer(params or {}) if callable(self.answer) else self.answer


def _hold_month(root, month_key, events, final=True):
    archive._write(
        archive._month_path(month_key, root),
        {
            "month": month_key,
            "fetched": "2030-01-01T00:00:00+00:00",
            "final": final,
            "events": events,
        },
    )


def _event(day, text, links=(), topics=(), outlet="Reuters"):
    return {
        "date": day,
        "category": "Politics and elections",
        "text": text,
        "links": list(links),
        "topics": list(topics),
        "citations": [{"outlet": outlet, "url": f"https://example.com/{text[:5]}"}],
    }


# --- parsing ----------------------------------------------------------------


def test_a_month_page_becomes_events_with_links_topics_and_citations():
    events = archive.parse_month(MONTH_HTML)
    assert len(events) == 3
    plot = events[0]
    assert plot["date"] == "2022-03-01"
    assert plot["category"] == "Armed conflicts and attacks"
    assert plot["text"] == (
        "The Ukrainian army foils a plot against President Volodymyr Zelenskyy."
    )
    assert plot["links"] == ["Armed Forces of Ukraine", "Volodymyr Zelenskyy"]
    assert plot["topics"] == ["Russo-Ukrainian War"]
    assert [c["outlet"] for c in plot["citations"]] == ["Reuters", "The Guardian"]


def test_a_topic_heading_is_not_itself_an_event():
    texts = [e["text"] for e in archive.parse_month(MONTH_HTML)]
    assert "Russo-Ukrainian War" not in texts
    assert not any("edit" == t for t in texts)


def test_file_links_are_furniture_not_subjects():
    speech = archive.parse_month(MONTH_HTML)[2]
    assert speech["category"] == "Politics and elections"
    assert speech["links"] == ["Zelensky", "European Parliament"]


def test_the_window_is_five_years_of_months_inclusive():
    months = archive.months_in_window(date(2026, 9, 14), 5)
    assert months[0] == "2021-09" and months[-1] == "2026-09"
    assert len(months) == 61


# --- storage and matching ---------------------------------------------------


def test_redirects_and_topics_both_link_an_event_to_a_subject(tmp_path):
    _hold_month(tmp_path, "2022-03", archive.parse_month(MONTH_HTML))
    person = archive.match(
        {"Volodymyr Zelenskyy", "Zelensky"}, months=["2022-03"], root=tmp_path
    )
    assert len(person) == 2
    assert {e["how"] for e in person} == {"named"}
    war = archive.match({"Russo-Ukrainian War"}, months=["2022-03"], root=tmp_path)
    assert len(war) == 2 and {e["how"] for e in war} == {"topic"}


def test_matching_ignores_case_and_returns_newest_first(tmp_path):
    _hold_month(
        tmp_path,
        "2022-03",
        [
            _event("2022-03-01", "Older item here", links=["Kyiv"]),
            _event("2022-03-09", "Newer item here", links=["Kyiv"]),
        ],
    )
    found = archive.match({"kyiv"}, months=["2022-03"], root=tmp_path)
    assert [e["date"] for e in found] == ["2022-03-09", "2022-03-01"]


def test_ensure_downloads_each_month_once(tmp_path):
    fetcher = StubFetcher({"parse": {"text": MONTH_HTML}})
    first = archive.ensure(fetcher, months=["2022-03", "2022-04"], root=tmp_path)
    assert first["fetched"] == 2 and len(fetcher.calls) == 2
    assert fetcher.calls[0]["page"] == "Portal:Current events/March 2022"
    again = archive.ensure(fetcher, months=["2022-03", "2022-04"], root=tmp_path)
    assert again["fetched"] == 0 and len(fetcher.calls) == 2


def test_an_unfinished_month_is_refreshed_once_it_is_stale(tmp_path):
    _hold_month(tmp_path, "2026-09", [], final=False)
    raw = archive._read(archive._month_path("2026-09", tmp_path))
    raw["fetched"] = "2000-01-01T00:00:00+00:00"
    archive._write(archive._month_path("2026-09", tmp_path), raw)
    assert archive.needs_fetch("2026-09", tmp_path)


def test_a_month_that_failed_to_download_is_not_stored(tmp_path):
    result = archive.ensure(StubFetcher(None), months=["2022-03"], root=tmp_path)
    assert result["failed"] == 1
    assert archive.held_months(tmp_path) == []


def test_past_the_cap_topic_events_are_kept_first(monkeypatch):
    monkeypatch.setattr(
        archive,
        "match",
        lambda titles, root=None: [
            {**_event("2026-01-02", "named and newer"), "how": "named"},
            {**_event("2025-01-02", "filed under it"), "how": "topic"},
        ],
    )
    kept = archive.timeline_for({"X"}, cap=1)
    assert [e["title"] for e in kept] == ["filed under it"]


def test_an_event_becomes_a_reported_news_entry_citing_its_outlets():
    entry = archive.to_timeline({**archive.parse_month(MONTH_HTML)[0], "how": "named"})
    assert entry["kind"] == "news" and entry["confidence"] == "reported"
    assert entry["url"] == "https://www.reuters.com/a"
    assert "reported by Reuters, The Guardian" in entry["detail"]
    assert "Russo-Ukrainian War" in entry["detail"]


# --- the source adapter -----------------------------------------------------


def _ctx(fetcher, identity):
    return Context(fetcher=fetcher, identity=identity, log=lambda m: None)


def test_the_adapter_files_archive_events_for_the_subject(tmp_path, monkeypatch):
    monkeypatch.setattr(
        store, "data_root", lambda refresh=False: store.Root(tmp_path, False, "test")
    )
    month = archive.months_in_window()[1]
    _hold_month(
        tmp_path,
        month,
        [
            _event(f"{month}-05", "Zelensky meets leaders", links=["Zelensky"]),
            _event(f"{month}-06", "Unrelated item entirely", links=["Peru"]),
        ],
    )
    monkeypatch.setattr(archive, "needs_fetch", lambda *a, **k: False)
    fetcher = StubFetcher(
        {
            "query": {
                "pages": [
                    {
                        "title": "Volodymyr Zelenskyy",
                        "redirects": [{"title": "Zelensky"}],
                    }
                ]
            }
        }
    )
    harvest = news_source.fetch(
        SubjectProfile(name="Volodymyr Zelenskyy"),
        _ctx(fetcher, {"wikipedia_title": "Volodymyr Zelenskyy"}),
    )
    assert [e["title"] for e in harvest.timeline] == ["Zelensky meets leaders"]


def test_the_adapter_does_nothing_without_an_article_to_match():
    harvest = news_source.fetch(
        SubjectProfile(name="Nobody"), _ctx(StubFetcher(None), {})
    )
    assert not harvest.timeline and harvest.notes


# --- the article ------------------------------------------------------------


def test_an_article_splits_into_sections_without_its_reference_lists():
    text = (
        "Lead paragraph.\n\n"
        "== Early life ==\nBorn somewhere.\n"
        "=== Education ===\nStudied law.\n"
        "== References ==\nA list.\n"
        "=== Sources cited ===\nMore list.\n"
        "== Personal life ==\nMarried.\n"
    )
    sections = split_sections(text)
    assert [(s["heading"], s["level"]) for s in sections] == [
        ("Summary", 1),
        ("Early life", 2),
        ("Education", 3),
        ("Personal life", 2),
    ]
    assert sections[2]["text"] == "Studied law."


def test_an_article_with_no_text_is_not_stored():
    assert article_from("X", "") == {}


# --- storage ----------------------------------------------------------------


def _held_subject(root, slug="volodymyr-zelenskyy", title="Volodymyr Zelenskyy"):
    store.ensure_subject(slug, root)
    store.write_json(
        store.subject_dir(slug, root) / "subject.json",
        {
            "slug": slug,
            "name": title,
            "entity_type": "person",
            "identity": {"wikipedia_title": title},
        },
    )
    return slug


def test_adding_events_twice_never_doubles_them(tmp_path):
    slug = _held_subject(tmp_path)
    events = [archive.to_timeline({**_event("2024-02-01", "An item"), "how": ""})]
    article = article_from("V", "Lead.\n== Career ==\nActor.")
    first = dossier.add_events(slug, events, {"phase": "history"}, article, tmp_path)
    second = dossier.add_events(slug, events, {"phase": "history"}, None, tmp_path)
    assert first == {"timeline_added": 1, "article": True}
    assert second == {"timeline_added": 0, "article": False}
    held = dossier.load(slug, tmp_path)
    assert len(held["timeline"]) == 1
    assert len(held["history"]) == 1
    assert held["article"]["sections"][1]["heading"] == "Career"


def _result(slug, article):
    return {
        "slug": slug,
        "name": "X",
        "entity_type": "person",
        "identity": {},
        "context_terms": [],
        "updated": "2026-09-14T00:00:00+00:00",
        "report": {"phase": "quick"},
        "sources": [],
        "timeline": [],
        "quotes": [],
        "relations": [],
        "claims": [],
        "article": article,
    }


def test_a_run_without_the_article_keeps_the_stored_one(tmp_path):
    article = article_from("X", "Lead.\n== Career ==\nActor.")
    dossier.save(_result("x", article), tmp_path)
    dossier.save(_result("x", {}), tmp_path)
    assert dossier.load("x", tmp_path)["article"]["title"] == "X"


# --- pages ------------------------------------------------------------------


def _day(days_ago):
    return (date.today() - timedelta(days=days_ago)).isoformat()


def test_the_news_page_splits_the_past_year_from_the_four_before():
    stored = {
        "subject": {},
        "timeline": [
            {"date": _day(700), "title": "old", "kind": "news"},
            {"date": _day(10), "title": "new", "kind": "news"},
            {"date": _day(20), "title": "headline", "kind": "coverage"},
            {"date": _day(30), "title": "took office", "kind": "office"},
        ],
    }
    block = page_registry.build_page("news", stored)["blocks"][0]
    assert block["kind"] == "news" and block["total"] == 3
    assert [g["label"] for g in block["groups"]] == [
        "Past year",
        "One to five years ago",
    ]
    assert [e["title"] for e in block["groups"][0]["events"]] == ["new", "headline"]


def test_the_overview_timeline_leaves_news_to_its_own_page():
    stored = {
        "subject": {},
        "timeline": [
            {"date": _day(10), "title": "new", "kind": "news"},
            {"date": _day(30), "title": "took office", "kind": "office"},
        ],
    }
    blocks = page_registry.build_page("overview", stored)["blocks"]
    timeline = [b for b in blocks if b["kind"] == "timeline"][0]
    assert [e["title"] for e in timeline["events"]] == ["took office"]


def test_a_long_timeline_keeps_its_newest_entries():
    from pages import common

    stored = {"timeline": [{"date": f"20{n:02d}-01-01"} for n in range(10, 30)]}
    events = common.timeline_block(stored, limit=5)["events"]
    assert [e["date"][:4] for e in events] == ["2025", "2026", "2027", "2028", "2029"]


def test_the_in_depth_page_draws_every_section():
    stored = {"article": article_from("X", "Lead.\n== Career ==\nActor.")}
    block = page_registry.build_page("profile", stored)["blocks"][0]
    assert block["kind"] == "article" and len(block["sections"]) == 2


# --- filling in history for the library --------------------------------------


def test_filling_in_history_adds_news_and_articles_to_held_subjects(
    tmp_path, monkeypatch
):
    _held_subject(tmp_path)
    monkeypatch.setattr(archive, "months_in_window", lambda *a, **k: ["2022-03"])

    def answer(params):
        if params.get("action") == "parse":
            return {"parse": {"text": MONTH_HTML}}
        if params.get("prop") == "redirects":
            return {
                "query": {
                    "pages": [
                        {
                            "title": "Volodymyr Zelenskyy",
                            "redirects": [{"title": "Zelensky"}],
                        }
                    ]
                }
            }
        if params.get("prop") == "extracts":
            return {
                "query": {
                    "pages": [
                        {
                            "title": "Volodymyr Zelenskyy",
                            "extract": "Lead.\n== Early life ==\nBorn.",
                        }
                    ]
                }
            }
        return None

    result = enrich.run(fetcher=StubFetcher(answer), root=tmp_path)
    assert result["events_added"] == 2
    assert result["articles_added"] == 1
    assert not result["running"]
    held = dossier.load("volodymyr-zelenskyy", tmp_path)
    assert {e["kind"] for e in held["timeline"]} == {"news"}
    assert held["article"]["sections"][1]["heading"] == "Early life"

    # A second pass finds nothing new to add.
    again = enrich.run(fetcher=StubFetcher(answer), root=tmp_path)
    assert again["events_added"] == 0 and again["articles_added"] == 0
