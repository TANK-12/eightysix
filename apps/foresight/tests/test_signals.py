"""Signal sources and the store beneath them.

No network: the stub fetcher returns the exact response shapes captured from
the live endpoints, including Hacker News's flat story list and Lemmy's nested
`posts[].counts` objects.
"""

import store
from analysis import trend
from signals import hn, lemmy, pageviews
from signals import registry as sources
from sweep import Context


class StubFetcher:
    def __init__(self, payload=None):
        self.payload = payload
        self.calls = []

    def get_json(self, url, api=True, params=None, **kw):
        self.calls.append((url, params or {}))
        if callable(self.payload):
            return self.payload(url, params or {})
        return self.payload


def ctx(payload, days=60, stored=None):
    return Context(
        fetcher=StubFetcher(payload), days=days, stored=stored or {}, log=lambda m: None
    )


# --- the registry -----------------------------------------------------------


def test_sources_are_discovered_not_declared():
    names = {s.name for s in sources.all_sources()}
    assert {"pageviews", "hn", "lemmy"} <= names


def test_every_source_declares_what_is_wrong_with_it():
    """A measurement shown without its bias is worse than none, so the caveat
    is not optional."""
    for spec in sources.all_sources():
        assert spec.caveat.strip(), f"{spec.name} has no caveat"
        assert spec.kind in sources.KINDS
        assert spec.unit.strip()


def test_a_source_needing_credentials_is_not_swept_automatically():
    for spec in sources.enabled_sources():
        assert not spec.needs_credentials


# --- pageviews --------------------------------------------------------------


def test_pageviews_reads_the_daily_series():
    payload = {
        "items": [
            {"timestamp": "2026090100", "views": 1200},
            {"timestamp": "2026090200", "views": 1500},
        ]
    }
    readings = pageviews.fetch("Angela Merkel", ctx(payload))
    assert [r.date for r in readings] == ["2026-09-01", "2026-09-02"]
    assert readings[1].value == 1500.0


def test_pageviews_uses_the_title_dossier_resolved_not_the_typed_name():
    """A name the user typed 404s; the title Wikidata resolved does not."""
    stored = {"subject": {"identity": {"wikipedia_title": "Bongbong Marcos"}}}
    assert pageviews.article_title("bongbong", stored) == "Bongbong Marcos"
    assert pageviews.article_title("Someone Else", {}) == "Someone Else"


def test_pageviews_survives_an_empty_answer():
    assert pageviews.fetch("Nobody", ctx(None)) == []
    assert pageviews.fetch("Nobody", ctx({})) == []


# --- hacker news ------------------------------------------------------------


def test_hn_groups_stories_into_one_reading_a_day():
    payload = {
        "hits": [
            {
                "created_at": "2026-09-01T10:00:00Z",
                "points": 100,
                "num_comments": 40,
                "title": "A",
                "objectID": "1",
            },
            {
                "created_at": "2026-09-01T18:00:00Z",
                "points": 20,
                "num_comments": 5,
                "title": "B",
                "objectID": "2",
            },
            {
                "created_at": "2026-09-02T09:00:00Z",
                "points": 7,
                "num_comments": 1,
                "title": "C",
                "objectID": "3",
            },
        ]
    }
    readings = hn.fetch("NATO", ctx(payload))
    assert [r.date for r in readings] == ["2026-09-01", "2026-09-02"]
    assert readings[0].value == 2.0  # two stories that day
    assert readings[0].sample == 45  # comments carried as the sample
    assert "A" in readings[0].detail  # the top story by points, not the latest


def test_hn_handles_no_hits():
    assert hn.fetch("Nothing", ctx({"hits": []})) == []


# --- lemmy ------------------------------------------------------------------


def test_lemmy_reads_the_nested_counts():
    payload = {
        "posts": [
            {
                "post": {
                    "published": "2026-09-01T10:00:00Z",
                    "name": "One",
                    "ap_id": "https://lemmy.world/post/1",
                },
                "counts": {"score": 12, "comments": 3},
            },
            {
                "post": {
                    "published": "2026-09-01T12:00:00Z",
                    "name": "Two",
                    "ap_id": "https://lemmy.world/post/2",
                },
                "counts": {"score": 40, "comments": 9},
            },
        ]
    }
    readings = lemmy.fetch("NATO", ctx(payload))
    assert len(readings) == 1
    assert readings[0].value == 2.0
    assert "Two" in readings[0].detail  # highest score wins


def test_lemmy_drops_posts_older_than_the_window():
    payload = {
        "posts": [
            {
                "post": {"published": "2001-01-01T00:00:00Z", "name": "Ancient"},
                "counts": {"score": 1, "comments": 0},
            },
        ]
    }
    assert lemmy.fetch("NATO", ctx(payload, days=30)) == []


# --- the store --------------------------------------------------------------


def test_a_series_merges_by_date_rather_than_appending(tmp_path):
    """Re-running a sweep on the same day must correct, never double."""
    first = [{"date": "2026-09-01", "value": 10}, {"date": "2026-09-02", "value": 20}]
    store.merge_series("x", "pageviews", first, tmp_path)
    again = store.merge_series("x", "pageviews", first, tmp_path)
    assert again == {"added": 0, "updated": 0, "total": 2}
    assert len(store.read_series("x", "pageviews", tmp_path)) == 2


def test_a_corrected_figure_for_an_old_date_wins(tmp_path):
    store.merge_series(
        "x", "pageviews", [{"date": "2026-09-01", "value": 10}], tmp_path
    )
    result = store.merge_series(
        "x", "pageviews", [{"date": "2026-09-01", "value": 11}], tmp_path
    )
    assert result["updated"] == 1
    assert store.read_series("x", "pageviews", tmp_path)[0]["value"] == 11


def test_a_series_comes_back_in_date_order(tmp_path):
    store.merge_series(
        "x",
        "hn",
        [{"date": "2026-09-03", "value": 3}, {"date": "2026-09-01", "value": 1}],
        tmp_path,
    )
    dates = [p["date"] for p in store.read_series("x", "hn", tmp_path)]
    assert dates == sorted(dates)


def test_slugify_matches_dossiers_so_series_line_up_with_dossiers():
    """Checked against Dossier's own output, not against what looks right.

    NFKD decomposes accents but not letters like 'ł', which is its own letter
    rather than an l with a mark, so Dossier really does produce 'lech-wa-esa'.
    Foresight has to reproduce that exactly or the two stores stop lining up -
    matching the quirk matters more than fixing it.
    """
    assert store.slugify("Angela Merkel") == "angela-merkel"
    assert store.slugify("Lech Wałęsa") == "lech-wa-esa"
    assert store.slugify("Xi Jinping") == "xi-jinping"


# --- breakout detection -----------------------------------------------------


def test_a_flat_series_reports_nothing():
    flat = [100.0] * 20
    z, _median, _spread = trend.score(flat)
    assert abs(z) < trend.THRESHOLD


def test_a_real_spike_is_found():
    series = [100.0] * 20 + [900.0]
    z, median, _spread = trend.score(series)
    assert z > trend.THRESHOLD and median == 100.0


def test_a_tiny_series_makes_no_claim():
    """Three days of history has no normal to depart from."""
    assert trend.score([1.0, 50.0, 2.0]) == (0.0, 0.0, 0.0)


def test_a_small_wobble_on_small_numbers_is_not_a_thousand_sigma_event():
    """A flat baseline has zero spread; without a floor this divides by zero
    and every trivial move becomes an emergency."""
    series = [4.0] * 20 + [9.0]
    z, _median, spread = trend.score(series)
    assert spread > 0
    assert abs(z) < trend.THRESHOLD


def test_one_huge_day_does_not_hide_the_next_one():
    """The reason for a median-based score: with a mean and standard deviation
    the first spike raises the bar enough to mask the second."""
    series = [100.0] * 20 + [5000.0] + [900.0]
    z, _median, _spread = trend.score(series)
    assert z > trend.THRESHOLD


def test_a_collapse_is_reported_as_well_as_a_spike():
    series = [500.0] * 20 + [5.0]
    z, _median, _spread = trend.score(series)
    assert z < -trend.THRESHOLD


def test_run_produces_a_finding_with_its_evidence():
    points = [{"date": f"2026-08-{d:02d}", "value": 100} for d in range(1, 21)]
    points.append({"date": "2026-08-21", "value": 1200, "detail": "something happened"})
    found = trend.run("nato", "NATO", {"pageviews": points})
    assert len(found) == 1
    assert found[0].kind == "breakout"
    assert found[0].evidence, "a finding must show its working"
    assert 0 < found[0].weight <= 1.0
