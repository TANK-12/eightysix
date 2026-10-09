"""Scenarios, and the ledger that marks them.

The rule these protect: **a forecast nobody can mark must never count as a
hit.** Everything else in this file follows from that. An indicator naming a
series that does not exist, one whose date has passed with no new reading, and
one a model proposed against a series this app does not hold are all failures
that must be visible rather than quietly scored as correct.
"""

from datetime import date, timedelta

import plans
import store


def _series(tmp_path, slug, name, points):
    store.write_json(store.series_path(slug, name, tmp_path), points)


def _day(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


def _scenario(indicators, created=None, slug="x", tier="rules"):
    return plans.Scenario(
        id="test1234",
        slug=slug,
        subject="X",
        title="t",
        created=created or _day(-30),
        tier=tier,
        branches=[plans.Branch(name="b", indicators=indicators)],
    )


# --- the ledger -------------------------------------------------------------


def test_an_indicator_that_is_not_due_is_left_alone(tmp_path):
    scenario = _scenario([plans.Indicator("s", "above", 1.0, _day(30))])
    plans.score(scenario, tmp_path)
    assert scenario.branches[0].indicators[0].outcome == "pending"


def test_a_met_indicator_is_marked_met(tmp_path):
    _series(tmp_path, "x", "s", [{"date": _day(-1), "value": 5.0}])
    scenario = _scenario([plans.Indicator("s", "above", 1.0, _day(0))])
    plans.score(scenario, tmp_path)
    indicator = scenario.branches[0].indicators[0]
    assert indicator.outcome == "met"
    assert indicator.observed == 5.0


def test_a_missed_indicator_is_marked_missed(tmp_path):
    _series(tmp_path, "x", "s", [{"date": _day(-1), "value": 0.5}])
    scenario = _scenario([plans.Indicator("s", "above", 1.0, _day(0))])
    plans.score(scenario, tmp_path)
    assert scenario.branches[0].indicators[0].outcome == "missed"


def test_below_is_the_mirror_of_above(tmp_path):
    _series(tmp_path, "x", "s", [{"date": _day(-1), "value": 0.5}])
    scenario = _scenario([plans.Indicator("s", "below", 1.0, _day(0))])
    plans.score(scenario, tmp_path)
    assert scenario.branches[0].indicators[0].outcome == "met"


def test_an_indicator_naming_no_stored_series_cannot_be_marked(tmp_path):
    scenario = _scenario([plans.Indicator("nothing-like-this", "above", 1.0, _day(-1))])
    plans.score(scenario, tmp_path)
    assert scenario.branches[0].indicators[0].outcome == "unscorable"


def test_a_reading_older_than_the_forecast_cannot_test_it(tmp_path):
    """The one that matters most.

    An annual series whose next figure has not published yet still has the
    reading the projection was DRAWN from. Marking against that would score
    every forecast as correct for free."""
    _series(tmp_path, "x", "s", [{"date": _day(-60), "value": 5.0}])
    scenario = _scenario(
        [plans.Indicator("s", "above", 1.0, _day(-1))], created=_day(-30)
    )
    plans.score(scenario, tmp_path)
    assert scenario.branches[0].indicators[0].outcome == "unscorable"


def test_a_reading_after_the_forecast_does_test_it(tmp_path):
    _series(
        tmp_path,
        "x",
        "s",
        [
            {"date": _day(-60), "value": 5.0},
            {"date": _day(-10), "value": 9.0},
        ],
    )
    scenario = _scenario(
        [plans.Indicator("s", "above", 1.0, _day(-1))], created=_day(-30)
    )
    plans.score(scenario, tmp_path)
    assert scenario.branches[0].indicators[0].outcome == "met"
    assert scenario.branches[0].indicators[0].observed == 9.0


def test_scoring_twice_does_not_change_a_settled_indicator(tmp_path):
    _series(tmp_path, "x", "s", [{"date": _day(-1), "value": 5.0}])
    scenario = _scenario([plans.Indicator("s", "above", 1.0, _day(0))])
    plans.score(scenario, tmp_path)
    _series(tmp_path, "x", "s", [{"date": _day(-1), "value": 0.0}])
    plans.score(scenario, tmp_path)
    assert scenario.branches[0].indicators[0].outcome == "met"


def test_the_tally_counts_what_settled(tmp_path):
    _series(tmp_path, "x", "s", [{"date": _day(-1), "value": 5.0}])
    scenario = _scenario(
        [
            plans.Indicator("s", "above", 1.0, _day(0)),
            plans.Indicator("s", "below", 1.0, _day(0)),
            plans.Indicator("s", "above", 1.0, _day(30)),
        ]
    )
    plans.score(scenario, tmp_path)
    line = plans.tally(scenario)
    assert line["met"] == 1 and line["missed"] == 1 and line["pending"] == 1
    assert line["settled"] == 2
    assert line["accuracy"] == 0.5


def test_accuracy_is_none_rather_than_zero_when_nothing_has_settled(tmp_path):
    """Nothing settled is not a 0% hit rate, and showing one would be a lie."""
    scenario = _scenario([plans.Indicator("s", "above", 1.0, _day(30))])
    assert plans.tally(scenario)["accuracy"] is None


# --- writing one from the rules tier ---------------------------------------


def test_the_rules_tier_projects_every_stored_series(tmp_path):
    points = [
        # Fourteen weekly readings: 91 days, enough history to support the
        # 90-day claim (a line is not carried further than it reaches back).
        {"date": (date.today() - timedelta(days=n * 7)).isoformat(), "value": 100 - n}
        for n in range(13, -1, -1)
    ]
    _series(tmp_path, "x", "daily", points)
    scenario = plans.from_rules("x", "X", tmp_path)
    assert scenario.tier == "rules"
    assert scenario.model == ""  # no model was anywhere near it
    names = [b.name for b in scenario.branches]
    assert names == ["The trend continues", "The trend breaks"]
    assert scenario.branches[0].indicators


def test_the_two_rules_branches_are_exact_complements(tmp_path):
    points = [
        # Fourteen weekly readings: 91 days, enough history to support the
        # 90-day claim (a line is not carried further than it reaches back).
        {"date": (date.today() - timedelta(days=n * 7)).isoformat(), "value": 100 - n}
        for n in range(13, -1, -1)
    ]
    _series(tmp_path, "x", "daily", points)
    scenario = plans.from_rules("x", "X", tmp_path)
    carried, broken = scenario.branches[0].indicators, scenario.branches[1].indicators
    assert len(carried) == len(broken)
    for a, b in zip(carried, broken):
        assert a.series == b.series and a.threshold == b.threshold
        assert a.by_date == b.by_date
        assert {a.direction, b.direction} == {"above", "below"}


def test_a_slow_series_is_not_projected_to_a_date_it_cannot_reach(tmp_path):
    """An annual figure projected three months out cannot be marked: the next
    reading will not have published."""
    points = [{"date": f"{2015 + n}-12-31", "value": 100 + n} for n in range(9)]
    _series(tmp_path, "x", "yearly", points)
    scenario = plans.from_rules("x", "X", tmp_path)
    horizons = {i.by_date for i in scenario.branches[0].indicators}
    soonest = min(horizons)
    assert soonest > (date.today() + timedelta(days=400)).isoformat()


def test_a_series_with_almost_no_history_is_not_projected(tmp_path):
    _series(tmp_path, "x", "thin", [{"date": _day(-2), "value": 1.0}])
    scenario = plans.from_rules("x", "X", tmp_path)
    assert scenario.branches == []


# --- writing one from a model ----------------------------------------------


class _Answer:
    def __init__(self, text, tier="think", model="m"):
        self.text = text
        self.tier = tier
        self.model = model


class _World:
    def subject_summary(self, slug, name):
        return {"text": "stuff", "evidence": []}


def _ask(text):
    return lambda prompt, tier: _Answer(text)


def test_a_model_branch_naming_a_real_series_is_kept(tmp_path):
    _series(tmp_path, "x", "real", [{"date": _day(-1), "value": 1.0}])
    reply = (
        '{"title": "T", "branches": [{"name": "A", "narrative": "n",'
        ' "indicators": [{"series": "real", "direction": "above",'
        f' "threshold": 2, "by_date": "{_day(100)}", "note": "x"}}]}}]}}'
    )
    scenario = plans.from_model("x", "X", "think", _World(), _ask(reply), tmp_path)
    assert len(scenario.branches) == 1
    assert scenario.branches[0].indicators[0].series == "real"
    assert scenario.model == "m"


def test_a_model_branch_inventing_a_series_is_discarded(tmp_path):
    """The same rule Dossier applies to an uncited sentence. A branch whose
    indicators cannot be marked is not a branch."""
    _series(tmp_path, "x", "real", [{"date": _day(-1), "value": 1.0}])
    reply = (
        '{"title": "T", "branches": [{"name": "A",'
        ' "indicators": [{"series": "imaginary.index", "direction": "above",'
        f' "threshold": 2, "by_date": "{_day(100)}"}}]}}]}}'
    )
    scenario = plans.from_model("x", "X", "think", _World(), _ask(reply), tmp_path)
    assert scenario.branches == []
    assert "discarded" in scenario.basis


def test_a_model_date_in_the_past_is_discarded(tmp_path):
    _series(tmp_path, "x", "real", [{"date": _day(-1), "value": 1.0}])
    reply = (
        '{"branches": [{"name": "A", "indicators": [{"series": "real",'
        f' "direction": "above", "threshold": 2, "by_date": "{_day(-5)}"}}]}}]}}'
    )
    scenario = plans.from_model("x", "X", "think", _World(), _ask(reply), tmp_path)
    assert scenario.branches == []


def test_a_model_reply_wrapped_in_prose_is_still_read(tmp_path):
    _series(tmp_path, "x", "real", [{"date": _day(-1), "value": 1.0}])
    reply = (
        "Here you go:\n```json\n"
        '{"branches": [{"name": "A", "indicators": [{"series": "real",'
        f' "direction": "below", "threshold": 2, "by_date": "{_day(100)}"}}]}}]}}'
        "\n```\nHope that helps."
    )
    scenario = plans.from_model("x", "X", "think", _World(), _ask(reply), tmp_path)
    assert len(scenario.branches) == 1


def test_a_model_saying_nothing_useful_produces_no_scenario(tmp_path):
    scenario = plans.from_model(
        "x", "X", "think", _World(), _ask("I am not sure."), tmp_path
    )
    assert scenario.branches == []


# --- round trip -------------------------------------------------------------


def test_a_scenario_survives_being_written_and_read(tmp_path):
    _series(tmp_path, "x", "s", [{"date": _day(-1), "value": 5.0}])
    scenario = _scenario([plans.Indicator("s", "above", 1.0, _day(0), note="n")])
    plans.score(scenario, tmp_path)
    plans.save(scenario, tmp_path)
    again = plans.load("test1234", tmp_path)
    assert again is not None
    assert again.branches[0].indicators[0].outcome == "met"
    assert again.branches[0].indicators[0].note == "n"


def test_the_record_separates_the_tiers(tmp_path):
    _series(tmp_path, "x", "s", [{"date": _day(-1), "value": 5.0}])
    a = _scenario([plans.Indicator("s", "above", 1.0, _day(0))], tier="rules")
    b = _scenario([plans.Indicator("s", "below", 1.0, _day(0))], tier="think")
    b.id = "test5678"
    for scenario in (a, b):
        plans.save(plans.score(scenario, tmp_path), tmp_path)
    ledger = plans.record(tmp_path)
    assert ledger["totals"]["scenarios"] == 2
    assert ledger["by_tier"]["rules"]["met"] == 1
    assert ledger["by_tier"]["think"]["missed"] == 1
