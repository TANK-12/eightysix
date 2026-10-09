"""The sources that measure something real, and the analyser written for them.

Until these landed every signal here was a proxy for attention. The user said
it plainly: "i want it to store finlcian and economic and polotacl things not
just how may time they wrer searche dup, that says nothing". These tests cover
the parts that would silently corrupt data if they were wrong — a source that
publishes several series sharing one file, and a daily z-score applied to an
annual figure.
"""

from analysis import level, trend
from signals import fx, registry, worldbank
from signals.registry import Reading

# --- several series from one source ----------------------------------------


def test_a_reading_can_name_its_own_series():
    assert Reading(date="2026-01-01", value=1.0).series == ""
    assert Reading(date="2026-01-01", value=1.0, series="GDP").series == "GDP"


def test_series_keys_are_filename_safe_and_round_trip():
    import store

    assert store.series_key("worldbank", "GDP per person") == "worldbank.gdp-per-person"
    assert store.series_key("pageviews", "") == "pageviews"
    # The key becomes a filename and sources_for() reads it back off the stem;
    # Path.stem strips only the last suffix, which is why a dot is safe here.
    path = store.series_path("x", "worldbank.gdp-per-person")
    assert path.stem == "worldbank.gdp-per-person"


def test_the_nine_world_bank_indicators_are_distinct_series():
    """They share a date. Without one series each, GDP silently overwrites
    unemployment for the same year."""
    names = set(worldbank.indicators().values())
    assert len(names) == len(worldbank.indicators())


def test_the_indicator_table_comes_from_dossier():
    codes = worldbank.indicators()
    assert "NY.GDP.MKTP.CD" in codes
    assert "SL.UEM.TOTL.ZS" in codes
    # More than the fallback, which means Dossier's table was actually found.
    assert len(codes) > len(worldbank._FALLBACK)


# --- the economic sources are registered like any other --------------------


def test_the_new_sources_are_discovered_not_declared():
    names = {s.name for s in registry.all_sources()}
    assert {"worldbank", "fx", "gdelt"} <= names


def test_every_source_states_what_it_measures_and_how_it_lies():
    for spec in registry.all_sources():
        assert spec.kind in registry.KINDS, spec.name
        assert spec.caveat.strip(), f"{spec.name} has no caveat"


# --- currency --------------------------------------------------------------


class _Ctx:
    def __init__(self, currency):
        self.stored = {"subject": {"identity": {"Currency": currency}}}


def test_a_currency_the_ecb_publishes_resolves():
    assert fx.currency_for(_Ctx(["Australian dollar"]))[0] == "AUD"


def test_a_currency_the_ecb_does_not_publish_reads_nothing():
    """A missing series is honest. An approximated one is not."""
    assert fx.currency_for(_Ctx(["Zimbabwean dollar"]))[0] == ""


def test_the_dollar_itself_is_skipped():
    assert fx.currency_for(_Ctx(["United States dollar"]))[0] == ""


# --- slow series are not run through a daily z-score ------------------------


def _annual(values):
    return [{"date": f"{2016 + n}-12-31", "value": v} for n, v in enumerate(values)]


def _daily(values):
    return [{"date": f"2026-06-{n + 1:02d}", "value": v} for n, v in enumerate(values)]


def test_the_breakout_analyser_ignores_an_annual_series():
    """A GDP series trends, so its newest year is routinely its largest value
    and a z-score would report a breakout every single time."""
    points = _annual([100 + n * 5 for n in range(12)])
    assert trend.cadence_days(points) > trend.SLOW_DAYS
    assert trend.run("x", "X", {"worldbank.gdp": points}) == []


def test_the_breakout_analyser_still_reads_a_daily_series():
    points = _daily([10] * 20 + [900])
    findings = trend.run("x", "X", {"pageviews": points})
    assert findings and findings[0].kind == "breakout"


def test_the_level_analyser_ignores_a_daily_series():
    """The two divide every series between them and neither names a source."""
    assert level.run("x", "X", {"pageviews": _daily([10] * 20 + [900])}) == []


def test_the_level_analyser_reports_a_record_high():
    points = _annual([100, 101, 102, 103, 140])
    findings = level.run("x", "X", {"worldbank.gdp": points})
    assert len(findings) == 1
    assert findings[0].kind == "level"
    assert "highest" in findings[0].detail


def test_the_level_analyser_says_nothing_about_a_figure_that_barely_moved():
    """A findings list that reports everything is one nobody reads."""
    points = _annual([100, 100.1, 100.2, 100.15, 100.2])
    assert level.run("x", "X", {"worldbank.inflation": points}) == []


def test_a_level_finding_carries_its_unit():
    """ "Government debt 57.88" means nothing without "% of GDP"."""
    points = [
        {
            "date": f"{2016 + n}-12-31",
            "value": v,
            "detail": f"Government debt: {v} % of GDP (Australia, {2016 + n})",
        }
        for n, v in enumerate([70, 69, 68, 67, 58])
    ]
    findings = level.run("x", "X", {"worldbank.government-debt": points})
    assert findings
    assert "% of GDP" in findings[0].detail
    assert findings[0].headline.endswith("Government debt")


# --- what reaches the top of the findings page ------------------------------


def test_findings_are_interleaved_so_one_kind_cannot_swamp_the_page():
    """Strict weight order made the page useless: a breakout's weight saturates
    at eight sigma, so two dozen pageview spikes tie at 1.0 and every economic
    finding falls below the fold."""
    import sweep

    findings = [
        {"kind": "breakout", "weight": 1.0, "at": "2026-09-10"} for _ in range(20)
    ] + [{"kind": "level", "weight": 0.6, "at": "2026-09-10"} for _ in range(5)]
    top = sweep.interleave(findings)[:6]
    kinds = [f["kind"] for f in top]
    assert kinds.count("level") >= 2, kinds
    # The strongest kind still leads, so a genuinely extraordinary day is not
    # buried by the mixing.
    assert kinds[0] == "breakout"


def test_interleaving_keeps_every_finding_and_the_order_inside_a_kind():
    import sweep

    findings = [
        {"kind": "level", "weight": 0.2, "at": "a"},
        {"kind": "breakout", "weight": 0.9, "at": "b"},
        {"kind": "level", "weight": 0.8, "at": "c"},
    ]
    out = sweep.interleave(findings)
    assert len(out) == 3
    levels = [f["weight"] for f in out if f["kind"] == "level"]
    assert levels == [0.8, 0.2]
