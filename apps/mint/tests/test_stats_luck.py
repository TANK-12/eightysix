import pytest

from conftest import bars, cfd_venue, inst
from mint import luck, stats, strategies
from mint.engine import RunConfig, RunResult, run
from mint.series import made_up


def fake_result(twr, equity=None, flows=None, start="2024-01-01"):
    import datetime as dt

    d0 = dt.date.fromisoformat(start)
    n = len(twr)
    dates = [(d0 + dt.timedelta(days=i * 365 // (n - 1))).isoformat() for i in range(n)]
    equity = equity or [100 * x for x in twr]
    flows = flows or [equity[0]] + [0.0] * (n - 1)
    from mint.account import Account

    return RunResult(dates, equity, flows, [0.0] * n, twr, Account(cfd_venue()), 1.0)


def test_xirr_matches_a_known_yearly_rate():
    r = stats.xirr([("2024-01-01", -100.0), ("2024-12-31", 110.0)])
    assert r == pytest.approx(0.10, abs=0.002)
    assert stats.xirr([("2024-01-01", -100.0), ("2025-01-01", 0.0)]) == -1.0


def test_segment_growth_drawdown_and_profit():
    res = fake_result([1.0, 2.0, 1.0, 1.5])
    seg = stats.segment(res)
    assert seg["growth"] == pytest.approx(1.5)
    assert seg["max_drawdown"] == pytest.approx(0.5)
    assert seg["cagr"] == pytest.approx(0.5, abs=0.01)
    assert seg["profit"] == pytest.approx(50.0)


def test_segment_of_a_slice_starts_fresh():
    res = fake_result([1.0, 2.0, 4.0, 4.0])
    seg = stats.segment(res, 1, 2)
    assert seg["growth"] == pytest.approx(2.0)
    assert seg["days"] == 2


def test_best_of_k_shows_how_retries_find_luck():
    assert stats.best_of_k(1) == pytest.approx(0.05)
    assert stats.best_of_k(20) == pytest.approx(0.6415, abs=0.001)


def series_and_run(sid="sma_cross", seed=5):
    s = made_up(n=1200, seed=seed)
    mod = strategies.load()[sid]
    t = mod.targets(s, strategies.params_for(mod.META, {}))
    v = cfd_venue(spread_pct={"default": 0.02}, funding_markup_pct=3.0)
    cfg = RunConfig(start_cash=1000, deposit=0, leverage=2)
    return s, t, v, cfg, run(s, t, v, inst(), cfg)


def test_luck_check_is_repeatable_with_a_seed():
    s, t, v, cfg, res = series_and_run()
    a = luck.check(s, t, v, inst(), cfg, res, runs=40, seed=9)
    b = luck.check(s, t, v, inst(), cfg, res, runs=40, seed=9)
    assert a == b
    assert not a["skipped"] and 0 <= a["percentile"] <= 100
    assert sum(a["hist"]["counts"]) == 40


def test_luck_check_skips_a_strategy_that_never_leaves_the_market():
    s = bars([100.0 + i for i in range(50)])
    t = [1.0] * 50
    v = cfd_venue()
    cfg = RunConfig(start_cash=1000, deposit=0)
    res = run(s, t, v, inst(), cfg)
    out = luck.check(s, t, v, inst(), cfg, res, runs=10)
    assert out["skipped"]


def test_random_traders_match_the_strategy_profile_roughly():
    import random

    prof = {"entries": 20, "avg_hold": 10.0, "size": 1.0, "long_share": 1.0, "time_in_market": 0.4}
    rng = random.Random(4)
    n = 500
    ins = []
    for _ in range(200):
        tg = luck.random_targets(n, prof, rng)
        ins.append(sum(1 for x in tg if x) / n)
    avg = sum(ins) / len(ins)
    assert 0.25 < avg < 0.55


def test_verdict_words():
    assert "rare for luck" in luck.verdict(97)
    assert "easily be luck" in luck.verdict(80)
    assert "No sign of skill" in luck.verdict(40)
