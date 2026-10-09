"""Luck check: is a strategy's result better than coin-flipping?

A few hundred random traders trade the same market on the same days, as
often, for as long, with the same leverage, deposits and costs. Where the
strategy lands among them says how unusual its result is. Beating 95% of
them is "maybe skill"; anything less cannot be told apart from luck.
"""

from __future__ import annotations

import random

from .engine import RunConfig, RunResult, run
from .series import Series
from .venues import Instrument, Venue


def profile(res: RunResult, targets: list[float]) -> dict:
    live = [x for x in targets if abs(x) > 1e-9]
    entries = max(1, res.account.entries)
    return {
        "entries": res.account.entries,
        "avg_hold": max(1.0, res.bars_in_market / entries),
        "size": (sum(abs(x) for x in live) / len(live)) if live else 1.0,
        "long_share": (sum(1 for x in live if x > 0) / len(live)) if live else 1.0,
        "time_in_market": res.bars_in_market / max(1, len(res.dates) - 1),
    }


def random_targets(n: int, prof: dict, rng: random.Random) -> list[float]:
    """Random entries matching the profile. Two draws per day, always, so a
    shorter series gives the same start (no peeking either)."""
    hold = prof["avg_hold"]
    q = min(0.95, prof["time_in_market"])
    trips_per_bar = prof["entries"] / max(1, n)
    p_enter = min(1.0, trips_per_bar / max(0.05, 1 - q))
    p_exit = 1 / hold
    pos = 0.0
    out: list[float] = []
    for _ in range(n):
        u, v = rng.random(), rng.random()
        if pos == 0.0:
            if u < p_enter:
                pos = prof["size"] * (1 if v < prof["long_share"] else -1)
        elif u < p_exit:
            pos = 0.0
        out.append(pos)
    return out


def check(
    series: Series,
    targets: list[float],
    venue: Venue,
    inst: Instrument,
    cfg: RunConfig,
    res: RunResult,
    fx: list[float] | None = None,
    runs: int = 200,
    seed: int = 1,
    rates: dict[str, list[float]] | None = None,
) -> dict:
    prof = profile(res, targets)
    mine = res.equity[-1] if res.equity else 0.0
    if prof["time_in_market"] > 0.95 or prof["entries"] < 2:
        return {
            "skipped": True,
            "verdict": "Always invested, so there is nothing to luck-check: "
            "compare it with the benchmark instead.",
            "profile": _round(prof),
        }
    rng = random.Random(seed)
    finals = []
    for _ in range(runs):
        rt = random_targets(len(series), prof, rng)
        finals.append(run(series, rt, venue, inst, cfg, fx, rates).equity[-1])
    finals.sort()
    below = sum(1 for x in finals if x < mine) + 0.5 * sum(1 for x in finals if x == mine)
    pct = 100 * below / runs
    return {
        "skipped": False,
        "runs": runs,
        "percentile": round(pct, 1),
        "median": round(finals[len(finals) // 2], 2),
        "p10": round(finals[len(finals) // 10], 2),
        "p90": round(finals[(len(finals) * 9) // 10], 2),
        "hist": histogram(finals, mine),
        "verdict": verdict(pct),
        "profile": _round(prof),
    }


def verdict(pct: float) -> str:
    if pct >= 95:
        return (
            f"Beat {pct:.0f}% of coin-flip traders paying the same costs. That is "
            "rare for luck alone, but one market and one stretch of years can "
            "still fool you."
        )
    if pct >= 75:
        return (
            f"Beat {pct:.0f}% of coin-flip traders. A coin-flipper does this well "
            f"about {100 - pct:.0f}% of the time, so this could easily be luck."
        )
    return (
        f"A coin-flip trader did better {100 - pct:.0f}% of the time. "
        "No sign of skill here."
    )


def histogram(values: list[float], mark: float, bins: int = 24) -> dict:
    lo = min(values + [mark])
    hi = max(values + [mark])
    width = (hi - lo) / bins or 1.0
    counts = [0] * bins
    for v in values:
        counts[min(bins - 1, int((v - lo) / width))] += 1
    return {"lo": round(lo, 2), "hi": round(hi, 2), "counts": counts, "mark": round(mark, 2)}


def _round(d: dict) -> dict:
    return {k: round(v, 3) if isinstance(v, float) else v for k, v in d.items()}
