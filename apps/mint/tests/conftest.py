import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import pytest  # noqa: E402

from mint.series import Series  # noqa: E402
from mint.venues import Instrument, Venue  # noqa: E402


@pytest.fixture(autouse=True)
def _data_dir(tmp_path, monkeypatch):
    """Every test writes into its own folder, never the real one."""
    monkeypatch.setenv("MINT_DATA_DIR", str(tmp_path / "mint-data"))


def weekdays(n: int, start: str = "2024-01-01") -> list[str]:
    import datetime as dt

    day = dt.date.fromisoformat(start)
    out: list[str] = []
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day.isoformat())
        day += dt.timedelta(days=1)
    return out


def bars(closes, opens=None, highs=None, lows=None, symbol="TEST", start="2024-01-01"):
    n = len(closes)
    opens = opens or list(closes)
    highs = highs or [max(o, c) for o, c in zip(opens, closes)]
    lows = lows or [min(o, c) for o, c in zip(opens, closes)]
    return Series(symbol, weekdays(n, start), list(opens), list(highs), list(lows), list(closes))


def cfd_venue(**kw) -> Venue:
    base = dict(
        id="cfd",
        label="test cfd",
        kind="cfd",
        allow_short=True,
        leverage_caps={"default": 20},
        spread_pct={"default": 0.0},
        funding_markup_pct=0.0,
        benchmark_rate_pct={"default": 0.0},
        fx_fee_pct=0.0,
        margin_closeout=0.5,
    )
    base.update(kw)
    return Venue(**base)


def cash_venue(**kw) -> Venue:
    base = dict(
        id="cash",
        label="test cash",
        kind="cash",
        spread_pct={"default": 0.0},
        brokerage_flat=0.0,
        min_trade=0.0,
        cash_interest_pct=0.0,
    )
    base.update(kw)
    return Venue(**base)


def inst(symbol="TEST", currency="AUD", cls="index_major") -> Instrument:
    return Instrument(symbol, symbol, cls, "index", currency)
