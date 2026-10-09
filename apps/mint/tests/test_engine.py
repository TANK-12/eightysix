import math

import pytest

from conftest import bars, cash_venue, cfd_venue, inst
from mint.account import Account
from mint.engine import RunConfig, run
from mint.series import days_between


def cfg(**kw):
    base = dict(start_cash=1000.0, deposit=0.0, leverage=1.0)
    base.update(kw)
    return RunConfig(**base)


def test_trade_happens_at_the_next_open_not_the_signal_close():
    s = bars([100.0] * 10, opens=[100.0 + i for i in range(10)])
    targets = [0.0] * 5 + [1.0] * 5  # decided at the close of day 5
    res = run(s, targets, cash_venue(), inst(), cfg())
    first = res.account.trades[0]
    assert first["date"] == s.dates[6]
    assert first["price"] == pytest.approx(106.0)


def test_share_account_charges_brokerage_and_half_the_spread():
    s = bars([100.0] * 5)
    v = cash_venue(brokerage_flat=3.0, spread_pct={"default": 0.2})
    res = run(s, [1.0] * 5, v, inst(), cfg())
    acct = res.account
    units = 997.0 / 100.1
    assert acct.positions["TEST"].units == pytest.approx(units)
    assert acct.costs["brokerage"] == pytest.approx(3.0)
    assert acct.costs["spread"] == pytest.approx(units * 100 * 0.001)
    assert res.equity[-1] == pytest.approx(1000 - 3 - units * 0.1)


def test_whole_units_and_minimum_buy_wait_for_enough_cash():
    s = bars([100.0] * 30)
    v = cash_venue(whole_units=True, min_trade=500.0)
    res = run(s, [1.0] * 30, v, inst(), cfg(start_cash=100.0, deposit=300.0))
    buys = [t for t in res.account.trades if t["side"] == "buy"]
    assert buys, "deposits should add up to a buy"
    assert all(float(t["units"]).is_integer() for t in buys)
    assert all(t["value"] >= 500 - 1e-6 for t in buys)


def test_run_config_min_trade_overrides_the_venue():
    s = bars([100.0] * 10)
    v = cash_venue(min_trade=500.0)
    res = run(s, [1.0] * 10, v, inst(), cfg(start_cash=200.0, min_trade=0.0))
    assert res.account.trades and res.account.trades[0]["date"] == s.dates[1]


def test_weekly_deposits_land_every_seven_calendar_days():
    s = bars([100.0] * 60)
    res = run(s, [0.0] * 60, cash_venue(), inst(), cfg(start_cash=0.0, deposit=300.0))
    span = days_between(s.dates[0], s.dates[-1])
    assert sum(1 for f in res.flows[1:] if f) == span // 7
    assert res.deposited == pytest.approx(300.0 * (span // 7))


def test_cfd_long_pays_benchmark_plus_markup_every_calendar_night():
    s = bars([100.0] * 10)  # Mon 1 Jan 2024 .. Fri 12 Jan, a weekend inside
    v = cfd_venue(funding_markup_pct=3.0, benchmark_rate_pct={"AUD": 4.0})
    res = run(s, [1.0] * 10, v, inst(), cfg(leverage=10.0))
    nights = days_between(s.dates[1], s.dates[-1])
    assert nights == 10  # opened Tue 2 Jan; Fri to Mon counts three
    funding = 10_000 * 0.07 * nights / 365
    assert res.account.costs["funding"] == pytest.approx(funding)
    assert res.equity[-1] == pytest.approx(1000 - funding)


def test_cfd_short_receives_when_the_benchmark_beats_the_markup():
    s = bars([100.0] * 10)
    v = cfd_venue(funding_markup_pct=3.0, benchmark_rate_pct={"AUD": 5.0})
    res = run(s, [-1.0] * 10, v, inst(), cfg(leverage=10.0))
    assert res.account.costs["funding"] < 0
    assert res.equity[-1] > 1000


def test_long_only_venue_ignores_short_targets():
    s = bars([100.0] * 10)
    res = run(s, [-1.0] * 10, cash_venue(), inst(), cfg())
    assert not res.account.trades


def test_leverage_is_cut_to_the_retail_cap():
    s = bars([100.0] * 5)
    v = cfd_venue(leverage_caps={"default": 2})
    res = run(s, [1.0] * 5, v, inst(), cfg(leverage=10.0))
    assert res.leverage_used == 2
    assert res.notes and "2x" in res.notes[0]
    assert res.account.positions["TEST"].units == pytest.approx(20.0)


def test_cfd_fx_fee_on_profit_in_another_currency():
    v = cfd_venue(fx_fee_pct=0.7)
    acct = Account(v)
    acct.instruments["US"] = inst("US", currency="USD")
    acct.deposit(1000.0)
    acct.trade("2024-01-01", "US", 10.0, 100.0, 0.5)
    acct.trade("2024-01-02", "US", -10.0, 110.0, 0.5)
    gained = 10 * 10 / 0.5  # 100 USD is 200 AUD at 0.5 USD per AUD
    assert acct.costs["fx"] == pytest.approx(gained * 0.007)
    assert acct.cash == pytest.approx(1000 + gained * (1 - 0.007))
    assert acct.round_trips[0]["result"] == pytest.approx(gained * (1 - 0.007), abs=0.01)


def test_cash_account_owns_the_whole_value_so_fx_moves_it():
    v = cash_venue()
    acct = Account(v)
    acct.instruments["US"] = inst("US", currency="USD")
    acct.deposit(1000.0)
    acct.trade("2024-01-01", "US", 5.0, 100.0, 0.5)  # 500 USD = 1000 AUD
    assert acct.cash == pytest.approx(0.0)
    assert acct.equity({"US": 100.0}, {"US": 0.5}) == pytest.approx(1000.0)
    assert acct.equity({"US": 100.0}, {"US": 0.625}) == pytest.approx(800.0)


def test_margin_close_out_fills_where_the_rule_bites():
    # 20x on $1,000: 200 units at 100. Equity < 50% of margin below 97.4359.
    closes = [100.0] * 3 + [96.0, 96.0]
    opens = [100.0] * 4 + [96.0]
    lows = [100.0] * 3 + [95.0, 96.0]
    s = bars(closes, opens=opens, lows=lows)
    v = cfd_venue(leverage_caps={"default": 20})
    res = run(s, [1.0, 1.0, 0.0, 0.0, 0.0], v, inst(), cfg(leverage=20.0))
    acct = res.account
    assert acct.closeouts == 0  # this one closes by signal, no fall
    res = run(s, [1.0] * 5, v, inst(), cfg(leverage=20.0, band=10.0))
    acct = res.account
    assert acct.closeouts == 1
    level = 19000 / 195
    trade = [t for t in acct.trades if t["reason"] == "margin close-out"][0]
    assert trade["price"] == pytest.approx(level, rel=1e-6)
    assert trade["date"] == s.dates[3]


def test_gap_through_close_out_level_fills_at_the_open_and_is_written_off():
    closes = [100.0, 100.0, 90.0, 90.0]
    opens = [100.0, 100.0, 90.0, 90.0]
    s = bars(closes, opens=opens)
    v = cfd_venue(leverage_caps={"default": 20})
    res = run(s, [1.0, 1.0, 0.0, 0.0], v, inst(), cfg(leverage=20.0, band=10.0))
    acct = res.account
    assert acct.closeouts == 1
    assert acct.protected == pytest.approx(1000.0)  # 200 units x -10 = -2000 on 1000
    assert acct.cash == 0.0
    assert min(res.equity) >= 0.0


def test_stop_loss_fills_at_the_stop_or_the_worse_open():
    s = bars([100.0, 100.0, 100.0, 99.0], lows=[100.0, 100.0, 100.0, 94.0])
    res = run(s, [1.0] * 4, cash_venue(), inst(), cfg(stop_pct=5.0))
    stop = [t for t in res.account.trades if t["reason"] == "stop"][0]
    assert stop["price"] == pytest.approx(95.0)
    s = bars([100.0, 100.0, 100.0, 92.0], opens=[100.0, 100.0, 100.0, 92.0])
    res = run(s, [1.0] * 4, cash_venue(), inst(), cfg(stop_pct=5.0))
    stop = [t for t in res.account.trades if t["reason"] == "stop"][0]
    assert stop["price"] == pytest.approx(92.0)


def test_round_trip_result_is_after_costs():
    s = bars([100.0, 100.0, 110.0, 110.0], opens=[100.0, 100.0, 110.0, 110.0])
    v = cash_venue(brokerage_flat=3.0)
    res = run(s, [1.0, 1.0, 0.0, 0.0], v, inst(), cfg())
    trip = res.account.round_trips[0]
    units = 997.0 / 100.0
    assert trip["result"] == pytest.approx(units * 10 - 6, abs=0.01)


def test_time_weighted_growth_ignores_deposits():
    s = bars([100.0] * 40)
    res = run(s, [0.0] * 40, cash_venue(), inst(), cfg(deposit=300.0))
    assert res.twr[-1] == pytest.approx(1.0)
    assert res.equity[-1] == pytest.approx(res.deposited)


def test_doubling_price_doubles_time_weighted_growth():
    closes = [100.0 * math.exp(math.log(2) * i / 9) for i in range(10)]
    s = bars(closes, opens=[closes[0]] * 2 + closes[1:-1])
    res = run(s, [1.0] * 10, cash_venue(), inst(), cfg())
    held_from = res.account.trades[0]["price"]
    assert res.twr[-1] == pytest.approx(closes[-1] / held_from)


def test_index_cfd_long_is_credited_dividends_and_a_short_pays_them():
    s = bars([100.0] * 10)
    i = inst()
    i.dividend_yield_pct = 4.0
    res = run(s, [1.0] * 10, cfd_venue(), i, cfg(leverage=10.0))
    nights = days_between(s.dates[1], s.dates[-1])
    assert res.account.dividends == pytest.approx(10_000 * 0.04 * nights / 365)
    res = run(s, [-1.0] * 10, cfd_venue(), i, cfg(leverage=10.0))
    assert res.account.dividends == pytest.approx(-10_000 * 0.04 * nights / 365)
    assert res.equity[-1] == pytest.approx(1000 - 10_000 * 0.04 * nights / 365)


def test_funding_and_cash_interest_follow_the_rate_of_each_day():
    s = bars([100.0] * 6)  # Mon 1 .. Mon 8 Jan 2024
    v = cfd_venue(funding_markup_pct=0.0, benchmark_rate_pct={"AUD": 50.0})
    hist = [0.0, 0.0, 0.0, 10.0, 10.0, 10.0]
    res = run(s, [1.0] * 6, v, inst(), cfg(leverage=10.0), rates={"AUD": hist})
    # nights after days 1, 2 at 0%; after day 3 (Thu) 1 night, Fri 3 nights at 10%
    assert res.account.costs["funding"] == pytest.approx(10_000 * 0.10 * 4 / 365)
    cv = cash_venue(cash_interest_pct=99.0, cash_interest_follows="AUD")
    res = run(s, [0.0] * 6, cv, inst(), cfg(), rates={"AUD": hist})
    assert res.account.interest == pytest.approx(1000 * 0.10 * 4 / 365, rel=1e-3)
