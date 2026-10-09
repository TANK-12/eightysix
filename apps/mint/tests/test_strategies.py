import pytest

from mint import strategies
from mint.indicators import prior_high, prior_low, rsi, sma
from mint.series import made_up

ALL = strategies.load()


def test_every_strategy_is_discovered_with_a_full_meta():
    assert {"buy_and_hold", "coin_flip", "trend_200", "sma_cross"} <= set(ALL)
    for sid, mod in ALL.items():
        meta = mod.META
        assert meta["id"] == sid and meta["name"] and meta["summary"]
        for p in meta["params"]:
            assert p["min"] <= p["default"] <= p["max"], (sid, p["key"])
            assert p["help"] and p["label"]


@pytest.mark.parametrize("sid", sorted(ALL))
def test_no_peeking_a_decision_never_changes_when_later_days_are_cut(sid):
    s = made_up(n=900, seed=3)
    mod = ALL[sid]
    params = strategies.params_for(mod.META, {})
    if "shorts" in params:
        params["shorts"] = 1
    full = mod.targets(s, params)
    assert len(full) == len(s)
    assert all(-1.0 <= x <= 1.0 for x in full)
    for cut in (1, 2, 50, 201, 260, 333, 640, 899):
        part = mod.targets(s.slice(0, cut), params)
        assert part == full[:cut], f"{sid} changed its past at cut {cut}"


@pytest.mark.parametrize("sid", sorted(ALL))
def test_every_strategy_runs_on_a_very_short_series(sid):
    s = made_up(n=3)
    mod = ALL[sid]
    assert len(mod.targets(s, strategies.params_for(mod.META, {}))) == 3


def test_params_are_kept_inside_their_range_and_bad_values_fall_back():
    meta = ALL["sma_cross"].META
    p = strategies.params_for(meta, {"fast": 9999, "slow": "rubbish"})
    assert p["fast"] == 100 and p["slow"] == 100


def test_indicators_on_toy_numbers():
    assert sma([1, 2, 3, 4], 2) == [None, 1.5, 2.5, 3.5]
    assert prior_high([1, 5, 2, 3], 2) == [None, None, 5, 5]
    assert prior_low([1, 5, 2, 3], 2) == [None, None, 1, 2]
    up = rsi([float(i) for i in range(10)], 3)
    assert up[:3] == [None, None, None] and up[3] == 100.0
    down = rsi([float(10 - i) for i in range(10)], 3)
    assert down[5] == pytest.approx(0.0)
