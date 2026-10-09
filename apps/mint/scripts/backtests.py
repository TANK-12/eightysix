"""The backtests behind docs/library/money/2026-10-09-mint-backtests.md.

Real Yahoo prices (cached), the RBA cash rate and the US T-bill rate day by
day, broken-data days cut out, every cost in venues.json. Prints the tables
as Markdown; `--json FILE` also saves the raw numbers.

    .venv/bin/python scripts/backtests.py [--json FILE]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mint import data, lab  # noqa: E402
from mint.engine import RunConfig, run  # noqa: E402

PLAN = RunConfig(start_cash=100, deposit=300)  # Emerson: $100 now, $300 a week
LUMP = RunConfig(start_cash=1000, deposit=0)


def money(x) -> str:
    return "n/a" if x is None else f"${x:,.0f}"


def pct(x, places: int = 1) -> str:
    return "n/a" if x is None else f"{x * 100:.{places}f}%"


def backtest_rows(L: lab.Lab, jobs) -> tuple[list[str], list[dict]]:
    head = (
        "| Run | From | Put in | Ended with | Return a year (money-weighted) | Worst fall "
        "| Costs (of which overnight funding) | Round trips | Close-outs | Luck check "
        "| Test years: it / plain fund |\n|---|---|---|---|---|---|---|---|---|---|---|"
    )
    lines, raw = [head], []
    for label, sym, venue, strat, params, cfg in jobs:
        r = L.backtest(sym, venue, strat, params, cfg, luck_runs=200)
        w, t, tr = r["whole"], r["test"], r["trades"]
        luck = r.get("luck", {})
        luck_txt = "always in" if luck.get("skipped") else f"beat {luck.get('percentile')}%"
        lines.append(
            f"| {label} | {w['start']} | {money(w['money_in'])} | {money(w['final'])} "
            f"| {pct(w['money_weighted'])} | {pct(w['max_drawdown'], 0)} "
            f"| {money(tr['costs_total'])} ({money(tr['costs'].get('funding', 0))}) "
            f"| {tr['round_trips']} | {tr['closeouts']} | {luck_txt} "
            f"| {pct(t['cagr'])} / {pct(r['bench']['test']['cagr'])} |"
        )
        raw.append({"label": label, **{k: r[k] for k in r if k not in ("curve", "trade_log", "round_trips")}})
    return lines, raw


def savings_row(L: lab.Lab) -> tuple[str, dict]:
    """Deposits left as cash in the share account, earning the RBA cash rate:
    roughly a savings account (a bonus-rate account pays a little more)."""
    venue = L.venues["cash"]
    mkt = L.market("VAS.AX", venue)
    res = run(mkt.series, [0.0] * len(mkt.series), venue, mkt.inst, PLAN, mkt.fx, mkt.rates)
    from mint import stats

    w = stats.segment(res)
    line = (
        f"| Savings: cash earning the RBA cash rate | {w['start']} | {money(w['money_in'])} "
        f"| {money(w['final'])} | {pct(w['money_weighted'])} | {pct(w['max_drawdown'], 0)} "
        "| $0 | 0 | 0 | n/a | n/a |"
    )
    return line, w


def zero_rows(L: lab.Lab, jobs) -> tuple[list[str], list[dict]]:
    head = (
        "| Market | Leverage | Trades a year, hold | Window | Runs | Put in (median) "
        "| Lost money | Lost over half | Margin close-out hit | 10th / median / 90th ending "
        "| Median costs |\n|---|---|---|---|---|---|---|---|---|---|---|"
    )
    lines, raw = [head], []
    for sym, cfg, years, tpy, hold, runs in jobs:
        z = L.zero_skill(sym, cfg, years=years, runs=runs, trades_per_year=tpy, hold_days=hold)
        win = f"{z['years']:.0f} yr" if z["years"] < 10 else f"all ({z['first'][:4]} on)"
        lines.append(
            f"| {z['name']} | {cfg.leverage:g}x | {tpy}, {hold} d | {win} | {z['runs']} "
            f"| {money(z['money_in_median'])} | {pct(z['lost_share'], 0)} "
            f"| {pct(z['lost_half_share'], 0)} | {pct(z['closeout_share'], 0)} "
            f"| {money(z['p10'])} / {money(z['p50'])} / {money(z['p90'])} "
            f"| {money(z['median_costs'])} |"
        )
        raw.append(z)
    return lines, raw


def sweep_rows(L: lab.Lab, jobs) -> tuple[list[str], list[dict]]:
    head = (
        "| Strategy, market | Settings tried | Best on tuning years | Its tuning return "
        "| Same settings, test years | Median of all settings, test years "
        "| Chance one of that many skill-free tries clears a 95% bar |"
        "\n|---|---|---|---|---|---|---|"
    )
    lines, raw = [head], []
    for label, sym, venue, strat, cfg, steps in jobs:
        s = L.sweep(sym, venue, strat, cfg, steps=steps)
        best = ", ".join(f"{k} {v}" for k, v in s["best"]["params"].items())
        lines.append(
            f"| {label} | {s['tried']} | {best} | {pct(s['best']['tuning'])} a year "
            f"| {pct(s['best']['test'])} a year | {pct(s['median_test'])} a year "
            f"| {pct(s['luck_odds'], 0)} |"
        )
        raw.append({"label": label, **{k: s[k] for k in s if k != "rows"}})
    return lines, raw


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()
    L = lab.Lab(data.PriceStore(data.default_root()))
    lev = lambda x: RunConfig(start_cash=100, deposit=300, leverage=x)  # noqa: E731
    out: dict = {}

    print("## 1. The long-term pot: $100, then $300 a week, share account\n")
    lines, out["shares"] = backtest_rows(
        L,
        [
            ("VAS (Australia 300), buy and hold", "VAS.AX", "cash", "buy_and_hold", None, PLAN),
            ("IVV (US S&P 500), buy and hold", "IVV.AX", "cash", "buy_and_hold", None, PLAN),
            ("VAS, 200-day trend filter", "VAS.AX", "cash", "trend_200", None, PLAN),
            ("VAS, 20/100 average crossover", "VAS.AX", "cash", "sma_cross", None, PLAN),
            ("VAS, 12-month momentum", "VAS.AX", "cash", "momentum_12m", None, PLAN),
            ("VAS, 55-day breakout", "VAS.AX", "cash", "donchian_breakout", None, PLAN),
            ("VAS, RSI dip-buying", "VAS.AX", "cash", "rsi_reversion", None, PLAN),
        ],
    )
    line, out["savings"] = savings_row(L)
    print("\n".join(lines + [line]) + "\n")

    print("## 2. The same money through a CFD broker on the ASX 200\n")
    lines, out["cfd"] = backtest_rows(
        L,
        [
            ("ASX 200 CFD, hold, 1x", "^AXJO", "cfd", "buy_and_hold", None, lev(1)),
            ("ASX 200 CFD, hold, 2x", "^AXJO", "cfd", "buy_and_hold", None, lev(2)),
            ("ASX 200 CFD, hold, 5x", "^AXJO", "cfd", "buy_and_hold", None, lev(5)),
            ("ASX 200 CFD, hold, 20x", "^AXJO", "cfd", "buy_and_hold", None, lev(20)),
            ("ASX 200 CFD, trend filter, 5x", "^AXJO", "cfd", "trend_200", None, lev(5)),
            ("ASX 200 CFD, crossover, 5x", "^AXJO", "cfd", "sma_cross", None, lev(5)),
            ("ASX 200 CFD, momentum, 5x", "^AXJO", "cfd", "momentum_12m", None, lev(5)),
            ("ASX 200 CFD, breakout, 5x", "^AXJO", "cfd", "donchian_breakout", None, lev(5)),
            ("ASX 200 CFD, RSI dips, 5x", "^AXJO", "cfd", "rsi_reversion", None, lev(5)),
            ("S&P 500 CFD, hold, 5x", "^GSPC", "cfd", "buy_and_hold", None, lev(5)),
        ],
    )
    print("\n".join(lines) + "\n")

    print("## 3. Traders with no skill (coin flips) paying real CFD costs\n")
    lumps = [
        RunConfig(start_cash=1000, deposit=0, leverage=x) for x in (5, 10, 20, 30)
    ]
    lines, out["zero"] = zero_rows(
        L,
        [
            ("^AXJO", lumps[1], 1, 50, 3, 400),
            ("^AXJO", lumps[2], 1, 100, 2, 400),
            ("^GSPC", lumps[1], 1, 50, 3, 400),
            ("AUDUSD=X", lumps[2], 1, 100, 2, 400),
            ("AUDUSD=X", lumps[3], 1, 100, 2, 400),
            ("^AXJO", lev(5), 1, 25, 5, 400),
            ("^AXJO", lev(20), 1, 50, 3, 400),
            ("^AXJO", lev(5), 5, 25, 5, 300),
            ("^AXJO", lev(5), 50, 25, 5, 300),
            ("^AXJO", lev(20), 50, 25, 5, 300),
            ("AUDUSD=X", lev(20), 50, 25, 5, 300),
        ],
    )
    print("\n".join(lines) + "\n")

    print("## 5. With the 2008 crash in: STW (ASX 200 fund) from January 2008\n")
    lines, out["crash"] = backtest_rows(
        L,
        [
            ("STW, buy and hold", "STW.AX", "cash", "buy_and_hold", None, PLAN),
            ("STW, 200-day trend filter", "STW.AX", "cash", "trend_200", None, PLAN),
            ("STW, 20/100 average crossover", "STW.AX", "cash", "sma_cross", None, PLAN),
            ("STW, 12-month momentum", "STW.AX", "cash", "momentum_12m", None, PLAN),
            ("STW, 55-day breakout", "STW.AX", "cash", "donchian_breakout", None, PLAN),
        ],
    )
    print("\n".join(lines) + "\n")

    print("## 4. Tuning flatters: best settings on old years, then unseen years\n")
    lines, out["sweeps"] = sweep_rows(
        L,
        [
            ("Crossover, ASX 200 CFD 5x", "^AXJO", "cfd", "sma_cross", lev(5), 6),
            ("Breakout, ASX 200 CFD 5x", "^AXJO", "cfd", "donchian_breakout", lev(5), 6),
            ("Trend filter, VAS shares", "VAS.AX", "cash", "trend_200", PLAN, 12),
            ("RSI dips, VAS shares", "VAS.AX", "cash", "rsi_reversion", PLAN, 4),
        ],
    )
    print("\n".join(lines) + "\n")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1, default=str)


if __name__ == "__main__":
    main()
