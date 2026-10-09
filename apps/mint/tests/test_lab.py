import pytest

from mint import data, lab
from mint.engine import RunConfig
from mint.series import Series, made_up


def walk(symbol, n=900, start="2015-01-05", seed=3, drift=0.08):
    s = made_up(symbol, n=n, start=start, seed=seed, drift=drift)
    s.source, s.name, s.notes = "yahoo", symbol, []
    return s


def rising(symbol, n=600, start="2015-01-05", step=0.001):
    s = walk(symbol, n=n, start=start)
    c = [100 * (1 + step) ** i for i in range(n)]
    return Series(symbol, s.dates, list(c), list(c), list(c), list(c), name=symbol)


def rate_series(pct=4.0):
    days = ["2000-01-03", "2030-01-02"]
    return Series("rba-cash", days, [pct] * 2, [pct] * 2, [pct] * 2, [pct] * 2, source="rba")


def make_lab(root, prices):
    def fetcher(sym):
        if sym in prices:
            return prices[sym], {}
        raise data.PriceError(f"no prices for {sym}")

    store = data.PriceStore(str(root), fetcher=fetcher)
    store.fetchers = {}  # the RBA rate comes from `prices` too, never the network
    return lab.Lab(store)


def test_backtest_reports_strategy_benchmark_both_periods_and_luck(tmp_path):
    L = make_lab(tmp_path, {"VAS.AX": walk("VAS.AX"), "rba-cash": rate_series()})
    out = L.backtest("VAS.AX", "cash", "trend_200", None, RunConfig(start_cash=1000), luck_runs=20)
    assert out["tuning"]["start"] == out["whole"]["start"]
    assert out["tuning"]["end"] == out["split_date"] == out["test"]["start"]
    assert out["test"]["end"] == out["whole"]["end"]
    assert out["bench"]["symbol"] == "VAS.AX"
    assert out["bench"]["whole"]["start"] == out["whole"]["start"]
    c = out["curve"]
    assert len(c["dates"]) == len(c["equity"]) == len(c["bench"]) == len(c["money_in"])
    assert c["dates"][-1] == out["whole"]["end"]
    assert c["money_in"][-1] == pytest.approx(out["whole"]["money_in"])
    assert out["luck"]
    assert "plain fund" in out["verdict"]
    assert not out["made_up"]


def test_buy_and_hold_on_the_benchmark_ends_where_the_benchmark_does(tmp_path):
    L = make_lab(tmp_path, {"VAS.AX": walk("VAS.AX"), "rba-cash": rate_series()})
    out = L.backtest("VAS.AX", "cash", "buy_and_hold", None, RunConfig(), luck_runs=0)
    assert out["whole"]["final"] == pytest.approx(out["bench"]["whole"]["final"])
    assert "luck" not in out


def test_a_market_older_than_its_benchmark_starts_when_the_benchmark_does(tmp_path):
    prices = {
        "BHP.AX": walk("BHP.AX", n=1200, start="2012-01-02"),
        "VAS.AX": walk("VAS.AX", n=600, start="2014-06-02", seed=5),
        "rba-cash": rate_series(),
    }
    out = make_lab(tmp_path, prices).backtest(
        "BHP.AX", "cash", "buy_and_hold", None, RunConfig(), luck_runs=0
    )
    assert out["whole"]["start"] == "2014-06-02"
    assert any("benchmark VAS.AX begin" in n for n in out["notes"])


def test_sweep_picks_its_winner_from_the_tuning_years_only(tmp_path):
    a = walk("AAA.AX", n=900, seed=11)
    b = walk("AAA.AX", n=900, seed=11)
    k = int(len(a) * 0.7)
    other = walk("X", n=900, seed=99, drift=-0.2)
    scale = a.close[k] / other.close[k]
    for i in range(k + 1, len(b)):
        for mine, theirs in ((b.open, other.open), (b.high, other.high), (b.low, other.low)):
            mine[i] = theirs[i] * scale
        b.close[i] = other.close[i] * scale
    cfg = RunConfig(start_cash=5000, deposit=0)
    ra = make_lab(tmp_path / "a", {"AAA.AX": a, "rba-cash": rate_series()})
    rb = make_lab(tmp_path / "b", {"AAA.AX": b, "rba-cash": rate_series()})
    sa = ra.sweep("AAA.AX", "cash", "sma_cross", cfg, steps=3)
    sb = rb.sweep("AAA.AX", "cash", "sma_cross", cfg, steps=3)
    assert sa["split_date"] == sb["split_date"] == a.dates[k]
    assert sa["tried"] == sb["tried"] > 1
    assert sa["best"]["params"] == sb["best"]["params"]
    assert sa["best"]["tuning"] == sb["best"]["tuning"]
    assert sa["best"]["test"] != sb["best"]["test"]
    assert sa["best"]["tuning"] == max(r["tuning"] for r in sa["rows"])
    assert "unseen years" in sa["verdict"]


def test_made_up_prices_need_no_network_and_say_so(tmp_path):
    out = make_lab(tmp_path, {}).backtest(
        lab.MADE_UP, "cfd", "buy_and_hold", None, RunConfig(), luck_runs=0
    )
    assert out["made_up"]
    assert any("Made-up" in n for n in out["notes"])
    assert any("fixed rate" in n for n in out["notes"])


def test_a_window_uses_earlier_history_for_its_averages(tmp_path):
    up = rising("VAS.AX", n=600)
    L = make_lab(tmp_path, {"VAS.AX": up, "rba-cash": rate_series()})
    out = L.backtest(
        "VAS.AX",
        "cash",
        "trend_200",
        None,
        RunConfig(start_cash=10000, deposit=0),
        start=up.dates[300],
        luck_runs=0,
    )
    assert out["whole"]["start"] == up.dates[300]
    assert out["curve"]["exposure"][1] > 0.9  # in from the first open, no 200-day wait


def test_bad_requests_are_lab_errors(tmp_path):
    L = make_lab(tmp_path, {"VAS.AX": walk("VAS.AX"), "^AXJO": walk("^AXJO")})
    cfg = RunConfig()
    with pytest.raises(lab.LabError, match="cannot trade"):
        L.backtest("^AXJO", "cash", "buy_and_hold", None, cfg, luck_runs=0)
    with pytest.raises(lab.LabError, match="Fewer than 30"):
        L.backtest("VAS.AX", "cash", "buy_and_hold", None, cfg, "2018-01-01", "2018-01-20")
    with pytest.raises(lab.LabError, match="No strategy"):
        L.backtest("VAS.AX", "cash", "nope", None, cfg)
    with pytest.raises(lab.LabError, match="No venue"):
        L.backtest("VAS.AX", "nope", "buy_and_hold", None, cfg)
    with pytest.raises(lab.LabError, match="no prices"):
        L.backtest("ZZZ.AX", "cash", "buy_and_hold", None, cfg)
    with pytest.raises(lab.LabError, match="nothing to tune"):
        L.sweep("VAS.AX", "cash", "buy_and_hold", cfg)


def test_sweep_grid_skips_seeds_and_switches_and_stays_under_the_cap():
    meta = {
        "params": [
            {"key": "fast", "min": 3, "max": 100, "step": 1, "default": 20},
            {"key": "slow", "min": 10, "max": 300, "step": 5, "default": 100},
            {"key": "shorts", "min": 0, "max": 1, "step": 1, "default": 0},
            {"key": "seed", "min": 1, "max": 999, "step": 1, "default": 1},
        ]
    }
    grid = lab.sweep_grid(meta, steps=6)
    assert 1 < len(grid) <= lab.MAX_SWEEP
    assert all(set(g) == {"fast", "slow"} for g in grid)
    assert {min(g["fast"] for g in grid), max(g["fast"] for g in grid)} == {3, 100}
    assert all(g["slow"] % 5 == 0 for g in grid)
    many = {"params": [dict(meta["params"][0], key=f"p{i}") for i in range(4)]}
    assert len(lab.sweep_grid(many, steps=6)) <= lab.MAX_SWEEP
    assert lab.sweep_grid({"params": []}) == []


def flat(symbol, n=600, start="2015-01-05", price=100.0):
    s = walk(symbol, n=n, start=start)
    c = [price] * n
    return Series(symbol, s.dates, list(c), list(c), list(c), list(c), name=symbol)


def test_zero_skill_traders_lose_every_time_on_a_market_that_never_moves(tmp_path):
    L = make_lab(tmp_path, {"FLAT.AX": flat("FLAT.AX"), "rba-cash": rate_series()})
    cfg = RunConfig(start_cash=1000, deposit=0, leverage=5)
    out = L.zero_skill("FLAT.AX", cfg, years=1, runs=40, trades_per_year=50, hold_days=3)
    assert out["runs"] == 40
    assert out["lost_share"] == 1.0
    assert out["p90"] < 1000
    assert out["median_costs"] > 0
    again = L.zero_skill("FLAT.AX", cfg, years=1, runs=40, trades_per_year=50, hold_days=3)
    assert again == out


def test_zero_skill_window_never_runs_past_the_history(tmp_path):
    L = make_lab(tmp_path, {"VAS.AX": walk("VAS.AX", n=400), "rba-cash": rate_series()})
    out = L.zero_skill("VAS.AX", RunConfig(leverage=1), years=50, runs=5, venue_id="cash")
    assert out["years"] == pytest.approx(400 / 252, abs=0.01)
    assert out["money_in_median"] > 100
