"""Backtests as the app asks for them: prices made ready (broken days left
out, exchange and benchmark rates lined up), the strategy run next to the
benchmark, tuning years against unseen test years, the luck check, and a
parameter sweep that picks its winner on the tuning years only."""

from __future__ import annotations

import itertools
import random
import statistics
from dataclasses import dataclass, replace

from . import data, luck, stats, strategies, venues
from .engine import RunConfig, RunResult, run
from .series import Series, align, made_up

DEFAULT_BENCHMARK = "VAS.AX"
MADE_UP = "MADE-UP"
MAX_SWEEP = 60


class LabError(ValueError):
    pass


@dataclass
class Market:
    series: Series
    targets_from: int  # index in `full` where the window starts
    full: Series  # whole usable history, so indicators can look back
    fx: list[float]
    rates: dict[str, list[float]]
    inst: venues.Instrument
    notes: list[str]


class Lab:
    def __init__(self, store: data.PriceStore):
        self.store = store
        self.venues = venues.load_venues()
        self.instruments = venues.load_instruments()

    # ---- prices ------------------------------------------------------------

    def history(self, symbol: str) -> tuple[Series, venues.Instrument, list[str]]:
        if symbol == MADE_UP:
            inst = venues.Instrument(MADE_UP, "Made-up prices", "index_major", "etf")
            s = made_up()
            return s, inst, list(s.notes)
        inst = venues.instrument_for(symbol, self.instruments)
        try:
            s = self.store.get(symbol)
        except data.PriceError as exc:
            raise LabError(str(exc)) from exc
        s, cut = data.after_breaks(s, inst.kind)
        return s, inst, list(s.notes) + cut

    def market(self, symbol: str, venue: venues.Venue, start: str = "", end: str = "") -> Market:
        full, inst, notes = self.history(symbol)
        a = full.index_on_or_after(start) if start else 0
        series = full.window(start, end)
        if len(series) < 30:
            raise LabError("Fewer than 30 days of prices in that window: pick a longer one.")
        fx, fx_notes = self.store.fx_for(series)
        rates, rate_notes = self.store.rates_for(
            series, venue.benchmark_history, [inst.currency, "AUD"]
        )
        return Market(series, a, full, fx, rates, inst, notes + fx_notes + rate_notes)

    # ---- one backtest --------------------------------------------------------

    def backtest(
        self,
        symbol: str,
        venue_id: str,
        strategy_id: str,
        params: dict | None,
        cfg: RunConfig,
        start: str = "",
        end: str = "",
        split: float = 0.7,
        luck_runs: int = 200,
    ) -> dict:
        venue, mod = self._pick(venue_id, strategy_id)
        mkt = self.market(symbol, venue, start, end)
        if not venue.can_trade(mkt.inst.kind):
            raise LabError(
                f"A {venue.label} cannot trade {mkt.inst.name}: pick the CFD "
                "broker, or an ETF such as VAS.AX."
            )
        bench_sym = mkt.inst.benchmark or DEFAULT_BENCHMARK
        if symbol == MADE_UP:
            bench_sym = MADE_UP
        bench_full, bench_inst, bench_notes = self.history(bench_sym)
        if bench_full.dates and bench_full.dates[0] > mkt.series.dates[0]:
            mkt = self.market(symbol, venue, bench_full.dates[0], end)
            mkt.notes.append(
                f"Started on {mkt.series.dates[0]}, when prices for the "
                f"benchmark {bench_sym} begin."
            )
        p = strategies.params_for(mod.META, params)
        targets = self._targets(mod, mkt, p)
        res = run(mkt.series, targets, venue, mkt.inst, cfg, mkt.fx, mkt.rates)
        bench = self._benchmark(bench_full, bench_inst, mkt.series, cfg)
        n = len(mkt.series)
        k = max(1, min(n - 2, int(n * split)))
        split_date = mkt.series.dates[k]
        bk = bench.dates.index(_on_or_before(bench.dates, split_date)) if bench.dates else 0
        rate = self._cash_rate(mkt)
        out = {
            "symbol": symbol,
            "name": mkt.inst.name,
            "venue": venue.id,
            "venue_label": venue.label,
            "strategy": mod.META["id"],
            "strategy_name": mod.META["name"],
            "params": p,
            "leverage_used": res.leverage_used,
            "split_date": split_date,
            "whole": stats.segment(res, 0, n - 1, rate),
            "tuning": stats.segment(res, 0, k, rate),
            "test": stats.segment(res, k, n - 1, rate),
            "trades": stats.trade_stats(res),
            "trade_log": res.account.trades[-300:],
            "round_trips": res.account.round_trips[-300:],
            "bench": {
                "symbol": bench_sym,
                "name": bench_inst.name,
                "whole": stats.segment(bench, 0, len(bench.dates) - 1, rate),
                "tuning": stats.segment(bench, 0, bk, rate),
                "test": stats.segment(bench, bk, len(bench.dates) - 1, rate),
            },
            "curve": _curve(mkt.series, res, bench),
            "notes": res.notes + mkt.notes + bench_notes,
            "warning": mkt.inst.warning,
            "made_up": mkt.series.source == "made-up",
        }
        if luck_runs > 0:
            out["luck"] = luck.check(
                mkt.series, targets, venue, mkt.inst, cfg, res, mkt.fx, luck_runs, 1, mkt.rates
            )
        out["verdict"] = verdict(out)
        return out

    # ---- parameter sweep -----------------------------------------------------

    def sweep(
        self,
        symbol: str,
        venue_id: str,
        strategy_id: str,
        cfg: RunConfig,
        start: str = "",
        end: str = "",
        split: float = 0.7,
        steps: int = 6,
    ) -> dict:
        venue, mod = self._pick(venue_id, strategy_id)
        mkt = self.market(symbol, venue, start, end)
        if not venue.can_trade(mkt.inst.kind):
            raise LabError(f"A {venue.label} cannot trade {mkt.inst.name}.")
        grid = sweep_grid(mod.META, steps)
        if not grid:
            raise LabError("This strategy has nothing to tune.")
        n = len(mkt.series)
        k = max(1, min(n - 2, int(n * split)))
        rows = []
        for combo in grid:
            p = strategies.params_for(mod.META, combo)
            res = run(mkt.series, self._targets(mod, mkt, p), venue, mkt.inst, cfg, mkt.fx, mkt.rates)
            tune, test = stats.segment(res, 0, k), stats.segment(res, k, n - 1)
            rows.append({"params": p, "tuning": tune["cagr"], "test": test["cagr"]})
        best = max(rows, key=lambda r: r["tuning"])
        tests = sorted(r["test"] for r in rows)
        return {
            "symbol": symbol,
            "strategy": mod.META["id"],
            "tried": len(rows),
            "split_date": mkt.series.dates[k],
            "best": best,
            "median_test": tests[len(tests) // 2],
            "rows": sorted(rows, key=lambda r: -r["tuning"])[:MAX_SWEEP],
            "luck_odds": round(stats.best_of_k(len(rows)), 3),
            "notes": mkt.notes,
            "verdict": (
                f"Tried {len(rows)} settings and kept the best on the tuning years "
                f"(to {mkt.series.dates[k]}). It made {best['tuning'] * 100:.1f}% a "
                f"year there and {best['test'] * 100:.1f}% a year on the unseen years "
                "after. The drop between the two is what tuning flatters. With "
                f"{len(rows)} tries, a skill-free idea clears a 95% luck bar at "
                f"least once {stats.best_of_k(len(rows)) * 100:.0f}% of the time."
            ),
        }

    # ---- traders with no skill ------------------------------------------------

    def zero_skill(
        self,
        symbol: str,
        cfg: RunConfig,
        years: float = 1.0,
        runs: int = 300,
        trades_per_year: int = 50,
        hold_days: int = 3,
        start: str = "",
        end: str = "",
        seed: int = 1,
        venue_id: str = "cfd",
    ) -> dict:
        """Coin-flip traders on `runs` random windows of real history, each
        `years` long, paying every real cost: what share of them lose money
        and how their results spread out. The baseline any skill must beat."""
        venue, mod = self._pick(venue_id, "coin_flip")
        mkt = self.market(symbol, venue, start, end)
        if not venue.can_trade(mkt.inst.kind):
            raise LabError(f"A {venue.label} cannot trade {mkt.inst.name}.")
        n = len(mkt.series)
        span = min(n, max(30, round(years * 252)))
        rng = random.Random(seed)
        ends, ins, costs, closed = [], [], [], 0
        for _ in range(max(1, runs)):
            a = rng.randrange(0, n - span + 1)
            sub = mkt.series.slice(a, a + span)
            p = strategies.params_for(
                mod.META,
                {
                    "seed": rng.randrange(1, 10000),
                    "trades_per_year": trades_per_year,
                    "hold_days": hold_days,
                    "shorts": 1 if venue.allow_short else 0,
                },
            )
            rates = {c: r[a : a + span] for c, r in mkt.rates.items()}
            res = run(sub, mod.targets(sub, p), venue, mkt.inst, cfg, mkt.fx[a : a + span], rates)
            ends.append(res.equity[-1])
            ins.append(res.deposited)
            costs.append(sum(res.account.costs.values()))
            closed += res.account.closeouts > 0
        k = len(ends)
        order = sorted(ends)
        return {
            "symbol": symbol,
            "name": mkt.inst.name,
            "venue": venue.id,
            "leverage": cfg.leverage,
            "runs": k,
            "years": round(span / 252, 2),
            "first": mkt.series.dates[0],
            "last": mkt.series.dates[-1],
            "trades_per_year": trades_per_year,
            "hold_days": hold_days,
            "lost_share": round(sum(e < m for e, m in zip(ends, ins)) / k, 3),
            "lost_half_share": round(sum(e < m / 2 for e, m in zip(ends, ins)) / k, 3),
            "closeout_share": round(closed / k, 3),
            "money_in_median": round(statistics.median(ins), 2),
            "p10": round(order[k // 10], 2),
            "p50": round(statistics.median(ends), 2),
            "p90": round(order[(k * 9) // 10], 2),
            "median_profit": round(statistics.median(e - m for e, m in zip(ends, ins)), 2),
            "median_costs": round(statistics.median(costs), 2),
            "notes": mkt.notes,
        }

    # ---- helpers ---------------------------------------------------------------

    def _pick(self, venue_id: str, strategy_id: str):
        if venue_id not in self.venues:
            raise LabError(f"No venue called {venue_id}.")
        mods = strategies.load()
        if strategy_id not in mods:
            raise LabError(f"No strategy called {strategy_id}.")
        return self.venues[venue_id], mods[strategy_id]

    def _targets(self, mod, mkt: Market, p: dict) -> list[float]:
        """Decided on the whole history up to each day, then cut to the
        window, so a 200-day average is ready on the window's first day."""
        whole = mod.targets(mkt.full, p)
        a = mkt.targets_from
        return whole[a : a + len(mkt.series)]

    def _benchmark(
        self, full: Series, inst: venues.Instrument, like: Series, cfg: RunConfig
    ) -> RunResult:
        cash = self.venues.get("cash")
        venue = cash if cash and cash.can_trade(inst.kind) else self.venues["cfd"]
        s = full.window(like.dates[0], like.dates[-1])
        fx, _ = self.store.fx_for(s)
        rates, _ = self.store.rates_for(s, venue.benchmark_history, [inst.currency, "AUD"])
        plain = replace(cfg, leverage=1.0, stop_pct=0.0, min_trade=None)
        return run(s, [1.0] * len(s), venue, inst, plain, fx, rates)

    def _cash_rate(self, mkt: Market) -> float:
        aud = mkt.rates.get("AUD")
        return sum(aud) / len(aud) if aud else self.venues["cfd"].bench_pct("AUD")


def sweep_grid(meta: dict, steps: int = 6) -> list[dict]:
    """Evenly spaced values for each tunable parameter (seeds and on/off
    switches stay at their defaults), capped at MAX_SWEEP combinations."""
    axes = []
    for p in meta.get("params", []):
        if p["key"] == "seed" or (p["min"] == 0 and p["max"] == 1):
            continue
        axes.append(p)
    if not axes:
        return []
    per = max(2, steps)
    while per > 2 and per ** len(axes) > MAX_SWEEP:
        per -= 1
    values = []
    for p in axes:
        lo, hi, step = p["min"], p["max"], p.get("step", 1)
        raw = [lo + (hi - lo) * i / (per - 1) for i in range(per)]
        values.append(sorted({round(round(v / step) * step, 6) for v in raw}))
    combos = [dict(zip([p["key"] for p in axes], vs)) for vs in itertools.product(*values)]
    return combos[:MAX_SWEEP]


def verdict(r: dict) -> str:
    w, b = r["whole"], r["bench"]["whole"]
    t, bt = r["test"], r["bench"]["test"]
    if not w.get("days"):
        return "Not enough days to say anything."
    beat = w["final"] > b.get("final", 0)
    test_beat = (t.get("cagr") or -1) > (bt.get("cagr") or -1)
    words = (
        f"Put in ${w['money_in']:,.0f}, ended with ${w['final']:,.0f} after "
        f"${r['trades']['costs_total']:,.0f} of costs. Simply buying {r['bench']['symbol']} "
        f"with the same deposits ended with ${b.get('final', 0):,.0f}. "
    )
    if beat and test_beat:
        words += "It beat the plain fund overall and on the unseen test years: now check the luck test."
    elif beat:
        words += "It won overall but lost on the unseen test years, which points to luck or tuning."
    else:
        words += "The plain fund did better."
    return words


def _on_or_before(dates: list[str], day: str) -> str:
    import bisect

    i = bisect.bisect_right(dates, day) - 1
    return dates[max(0, i)]


def _curve(series: Series, res: RunResult, bench: RunResult, points: int = 500) -> dict:
    b_series = Series("b", bench.dates, bench.equity, bench.equity, bench.equity, bench.equity)
    b_on = align(series, b_series) if bench.dates else [0.0] * len(series)
    money = []
    total = 0.0
    for f in res.flows:
        total += f
        money.append(total)
    n = len(series)
    step = max(1, n // points)
    idx = list(range(0, n, step))
    if idx[-1] != n - 1:
        idx.append(n - 1)
    return {
        "dates": [series.dates[i] for i in idx],
        "equity": [round(res.equity[i], 2) for i in idx],
        "bench": [round(b_on[i], 2) for i in idx],
        "money_in": [round(money[i], 2) for i in idx],
        "exposure": [round(res.exposure[i], 3) for i in idx],
    }
