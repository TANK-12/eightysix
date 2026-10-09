import json
import os

import pytest

from mint import data
from mint.series import Series, align

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "yahoo_vas_1mo.json")


def payload():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


def test_yahoo_parser_gives_adjusted_trading_days_and_drops_an_unfinished_day():
    p = payload()
    stamps = p["chart"]["result"][0]["timestamp"]
    end = p["chart"]["result"][0]["meta"]["currentTradingPeriod"]["regular"]["end"]
    s, facts = data.parse_yahoo(p, now=stamps[-1] + 60)
    assert facts["dropped_unfinished_day"] is True
    assert s.dates[-1] == "2026-10-08" and len(s) == 22
    assert s.adjusted and s.currency == "AUD" and s.symbol == "VAS.AX"
    assert len(set(s.dates)) == len(s.dates) and s.dates == sorted(s.dates)
    for o, h, lo, c in zip(s.open, s.high, s.low, s.close):
        assert lo <= min(o, c) and h >= max(o, c)
    s2, facts2 = data.parse_yahoo(p, now=end + 60)
    assert s2.dates[-1] == "2026-10-09" and not facts2["dropped_unfinished_day"]


def test_yahoo_parser_reports_an_error_answer():
    with pytest.raises(data.PriceError):
        data.parse_yahoo({"chart": {"result": None, "error": {"code": "Not Found"}}})


def test_csv_import_reads_australian_dates_and_adjusts():
    text = "Date,Open,High,Low,Close,Adj Close\n02/01/2024,10,11,9,10,5\n03/01/2024,10,12,10,11,5.5\nbad,row\n"
    s = data.parse_csv("MY", text)
    assert s.dates == ["2024-01-02", "2024-01-03"]
    assert s.close == [5.0, 5.5] and s.open[0] == 5.0 and s.adjusted
    with pytest.raises(data.PriceError):
        data.parse_csv("MY", "Date,Close\n2024-01-02,10\n")


def fake_series(sym="FAKE", n=5, currency="AUD"):
    dates = [f"2024-01-0{i + 1}" for i in range(n)]
    px = [100.0 + i for i in range(n)]
    return Series(sym, dates, px, px, px, px, currency=currency)


def test_store_caches_refreshes_and_falls_back(tmp_path):
    calls = []

    def fetcher(sym):
        calls.append(sym)
        if len(calls) > 1:
            raise data.PriceError("offline")
        return fake_series(sym), {"exchange": "TEST"}

    st = data.PriceStore(str(tmp_path), fetcher=fetcher)
    a = st.get("FAKE")
    b = st.get("FAKE")
    assert len(calls) == 1 and a.close == b.close
    c = st.get("FAKE", refresh=True)
    assert len(calls) == 2 and c.close == a.close
    assert c.notes and "saved prices" in c.notes[0]
    assert st.facts("FAKE")["bars"] == 5


def test_store_converts_currency_through_the_aud_pair(tmp_path):
    def fetcher(sym):
        assert sym == "AUDUSD=X"
        s = fake_series(sym)
        s.close = [0.5] * 5
        return s, {}

    st = data.PriceStore(str(tmp_path), fetcher=fetcher)
    fx, notes = st.fx_for(fake_series("US", currency="USD"))
    assert fx == [0.5] * 5 and not notes
    fx, notes = st.fx_for(fake_series("AU"))
    assert fx == [1.0] * 5


def test_align_carries_the_last_rate_over_gaps():
    a = Series("A", ["2024-01-01", "2024-01-02", "2024-01-03"], [1] * 3, [1] * 3, [1] * 3, [1] * 3)
    b = Series("B", ["2024-01-02"], [2.0], [2.0], [2.0], [2.0])
    assert align(a, b) == [2.0, 2.0, 2.0]


def test_rba_table_a2_becomes_a_rate_step_series():
    with open(os.path.join(os.path.dirname(__file__), "fixtures", "rba_a2_head.csv"), encoding="utf-8") as f:
        s = data.parse_rba_a2(f.read())
    assert s.dates[0] == "1990-01-23" and s.close[0] == pytest.approx(17.25)
    assert s.dates[-1] == "2026-09-30" and s.close[-1] == pytest.approx(4.60)


def test_broken_days_are_found_and_history_starts_after_them():
    px = [100.0, 101.0, 6.8, 6.9, 7.0, 104.0, 7.1]
    s = Series("BAD", [f"2024-01-{i + 1:02d}" for i in range(7)], px, px, px, px)
    assert [d for d, _ in data.breaks(s)] == ["2024-01-03", "2024-01-06", "2024-01-07"]
    clean, notes = data.after_breaks(s)
    assert clean.dates == ["2024-01-07"] and "left out" in notes[0]
    calm = Series("OK", s.dates[:2], px[:2], px[:2], px[:2], px[:2])
    assert data.after_breaks(calm) == (calm, [])
    btc = [100.0, 62.0, 64.0]
    s = Series("BTC", s.dates[:3], btc, btc, btc, btc)
    assert data.breaks(s, "crypto") == [] and data.breaks(s, "share")


def test_rates_follow_the_named_history(tmp_path):
    def fetcher(sym):
        assert sym == "^IRX"
        h = Series(sym, ["2024-01-01", "2024-01-04"], [1.0, 5.0], [1.0, 5.0], [1.0, 5.0], [1.0, 5.0])
        return h, {}

    st = data.PriceStore(str(tmp_path), fetcher=fetcher)
    s = fake_series("US", currency="USD")
    rates, notes = st.rates_for(s, {"USD": "^IRX"}, ["USD", "AUD"])
    assert rates == {"USD": [1.0, 1.0, 1.0, 5.0, 5.0]} and not notes
