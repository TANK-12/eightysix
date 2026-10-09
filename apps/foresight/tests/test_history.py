"""Five years of history, and what the rules tier learns from it.

No network and no model. The backtest is checked on series whose right answer
is known in advance: a straight line, where a line must win and every claim
must hold, and a flat series, where it must not.
"""

from datetime import date, timedelta

import dossier_link
import plans
import store
import sweep
from analysis import trend
from signals import fx, news_events
from signals import registry as sources
from signals.registry import Reading, SignalSpec


class StubFetcher:
    def __init__(self, payload=None):
        self.payload = payload
        self.calls = []

    def get_json(self, url, api=True, params=None, **kw):
        self.calls.append((url, params or {}))
        return self.payload


def _daily(values, end=None):
    end = end or date.today() - timedelta(days=1)
    start = end - timedelta(days=len(values) - 1)
    return [
        {"date": (start + timedelta(days=i)).isoformat(), "value": float(v)}
        for i, v in enumerate(values)
    ]


# --- gathering history -------------------------------------------------------


def test_the_first_sweep_of_a_source_reaches_back_five_years(tmp_path, monkeypatch):
    seen = []

    def fetch(name, ctx):
        seen.append(ctx.days)
        return [Reading(date=date.today().isoformat(), value=1.0)]

    spec = SignalSpec(
        name="fake", label="Fake", kind="attention", unit="u", fetch=fetch
    )
    monkeypatch.setattr(sources, "enabled_sources", lambda: [spec])
    ctx = sweep.Context(fetcher=None, days=60)
    sweep.sweep_subject("x", "X", ctx, root=tmp_path)
    sweep.sweep_subject("x", "X", ctx, root=tmp_path)
    assert seen == [sweep.HISTORY_DAYS, 60]


def test_a_breakout_is_measured_against_the_recent_past():
    # Years at 1000, then a quiet recent stretch at 10, then a jump to 30.
    # Against five years the jump would read as a collapse; against the
    # recent baseline it is the breakout it is.
    z, median, _ = trend.score([1000.0] * 400 + [10.0] * 90 + [30.0] * 3)
    assert median == 10.0
    assert z > trend.THRESHOLD


def test_currency_is_read_from_the_host_frankfurter_moved_to():
    stub = StubFetcher({"rates": {"2026-01-02": {"AUD": 1.5}}})
    ctx = sweep.Context(
        fetcher=stub,
        days=60,
        stored={"subject": {"identity": {"Currency": ["Australian dollar"]}}},
    )
    readings = fx.fetch("Australia", ctx)
    assert readings and stub.calls[0][0].startswith("https://api.frankfurter.dev/v1/")


def test_news_events_are_counted_by_month_from_dossiers_archive(tmp_path, monkeypatch):
    from research import news_archive as archive  # Dossier's, on sweep's path

    months = archive.months_in_window()
    old, older, current = months[-3], months[-4], months[-1]
    for month, count in ((older, 2), (old, 0), (current, 5)):
        archive._write(
            archive._month_path(month, tmp_path),
            {
                "month": month,
                "fetched": "2030-01-01T00:00:00+00:00",
                "final": True,
                "events": [
                    {
                        "date": f"{month}-03",
                        "text": "t",
                        "links": ["Kyiv"],
                        "topics": [],
                    }
                ]
                * count,
            },
        )
    monkeypatch.setattr(dossier_link, "root", lambda: tmp_path)
    ctx = sweep.Context(
        fetcher=StubFetcher({"query": {"pages": [{"title": "Kyiv"}]}}),
        stored={"subject": {"identity": {"wikipedia_title": "Kyiv"}}},
    )
    readings = news_events.fetch("Kyiv", ctx)
    by_month = {r.date[:7]: r.value for r in readings}
    # The month in progress is left out; a month held with nothing is a zero.
    assert by_month == {older: 2.0, old: 0.0}
    assert all(r.series == "per-month" for r in readings)


def test_news_events_read_nothing_without_an_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(dossier_link, "root", lambda: tmp_path)
    ctx = sweep.Context(
        fetcher=StubFetcher(None),
        stored={"subject": {"identity": {"wikipedia_title": "Kyiv"}}},
    )
    assert news_events.fetch("Kyiv", ctx) == []


# --- learning from history ---------------------------------------------------


def test_a_backtest_never_uses_readings_after_where_it_stands():
    points = _daily(range(100))
    origin = points[49]["date"]
    window = plans._window(points, origin, 90, 1.0)
    assert window and max(p["date"] for p in window) == origin


def test_on_a_straight_line_the_line_wins_and_every_claim_holds():
    # Five and a half years: enough room for three two-year trials.
    lessons = plans.backtest(_daily([100 + day for day in range(2000)]))
    assert {lesson["horizon_days"] for lesson in lessons} == {90, 365, 730}
    for lesson in lessons:
        assert lesson["winner"] == "trend"
        assert lesson["claims"] and lesson["hits"] == lesson["claims"]
        assert lesson["trials"] >= plans.MIN_TRIALS


def test_on_a_flat_series_assuming_no_change_wins_and_nothing_is_claimed():
    lessons = plans.backtest(_daily([50] * 900))
    assert lessons
    for lesson in lessons:
        assert lesson["winner"] == "persistence"
        assert lesson["claims"] == 0 and lesson["hit_rate"] is None


def test_a_short_series_teaches_nothing():
    assert plans.backtest(_daily([1, 2, 3])) == []


def _store(tmp_path, slug, name, points):
    store.write_json(store.series_path(slug, name, tmp_path), points)


def test_the_rules_tier_stops_claiming_what_history_says_does_not_work(
    tmp_path, monkeypatch
):
    _store(tmp_path, "x", "pageviews", _daily([100 + day for day in range(200)]))
    monkeypatch.setattr(
        plans,
        "learn",
        lambda slug, root=None: {
            "series": {
                "pageviews": [
                    {"horizon_days": d, "trials": 5, "winner": "persistence"}
                    for d in (90, 365, 730)
                ]
            }
        },
    )
    scenario = plans.from_rules("x", "X", tmp_path)
    assert scenario.branches == []
    assert "left out" in scenario.basis


def test_a_projection_says_how_often_it_held_in_backtests(tmp_path, monkeypatch):
    _store(tmp_path, "x", "pageviews", _daily([100 + day for day in range(200)]))
    monkeypatch.setattr(
        plans,
        "learn",
        lambda slug, root=None: {
            "series": {
                "pageviews": [
                    {
                        "horizon_days": 90,
                        "trials": 5,
                        "winner": "trend",
                        "claims": 5,
                        "hits": 4,
                    }
                ]
            }
        },
    )
    scenario = plans.from_rules("x", "X", tmp_path)
    notes = [i.note for i in scenario.branches[0].indicators]
    assert any("held 4 of 5" in note for note in notes)


def test_a_line_is_not_carried_further_than_its_history_reaches(tmp_path):
    _store(tmp_path, "young", "lemmy", _daily([10, 12, 14]))
    assert plans.from_rules("young", "Young", tmp_path).branches == []
    _store(tmp_path, "x", "pageviews", _daily([100 + day for day in range(200)]))
    scenario = plans.from_rules("x", "X", tmp_path)
    reached = {i.by_date for i in scenario.branches[0].indicators}
    # 200 days of history supports the three-month claim and nothing longer.
    assert reached == {(date.today() + timedelta(days=90)).isoformat()}
    assert "younger than" in scenario.basis


def test_what_was_learned_is_kept_apart_from_the_live_ledger(tmp_path):
    _store(tmp_path, "x", "pageviews", _daily([100 + day for day in range(900)]))
    plans.learn("x", tmp_path)
    record = plans.record(tmp_path)
    assert record["totals"]["scenarios"] == 0
    assert record["totals"]["accuracy"] is None
    assert record["backtest"]["claims"] > 0
    assert record["backtest"]["hit_rate"] == 1.0
