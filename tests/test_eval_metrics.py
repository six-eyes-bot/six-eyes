"""Expectancy, drawdown and Sharpe — the two numbers T8 says gate autonomy.

The first test is the fixture that showed DanisHack's `_analyze_trades` cannot
be ported wholesale. VENDORING.md §6 required verifying it independently
before trusting it; this is that verification, kept as a regression.
"""

from __future__ import annotations

import math
from datetime import date

import pytest

from desk.eval_metrics import (
    TRADING_DAYS,
    Fill,
    annualised_sharpe,
    expectancy,
    match_round_trips,
    max_drawdown,
    per_period_sharpe,
)


def d(day: int, month: int = 1) -> date:
    return date(2026, month, day)


# ======================================================================
# The fixture that rejected the port
# ======================================================================
def test_a_tiny_winner_and_a_large_loser_is_not_a_profitable_strategy() -> None:
    """DanisHack reports win_rate 50%, profit_factor 2.00 for this. It lost
    $4,990.

    Its round trips are appended once per FIFO match, unweighted by quantity,
    and its profit factor sums percentages rather than currency.
    """
    fills = [
        Fill(d(1), "A", "buy", 1, 100.0),
        Fill(d(2), "A", "sell", 1, 110.0),          # +$10
        Fill(d(3), "A", "buy", 1000, 100.0),
        Fill(d(4), "A", "sell", 1000, 95.0),        # -$5,000
    ]
    got = expectancy(fills)
    assert got.net_pnl == pytest.approx(-4990.0)
    assert got.expectancy_per_trade == pytest.approx(-2495.0)
    assert got.profit_factor is not None
    assert got.profit_factor == pytest.approx(10.0 / 5000.0)
    assert got.profit_factor < 1.0, "a losing strategy cannot have a profit factor above 1"


def test_expectancy_is_quantity_weighted() -> None:
    """The specific defect: size must change the answer."""
    small = expectancy([
        Fill(d(1), "A", "buy", 1, 100.0), Fill(d(2), "A", "sell", 1, 90.0),
    ])
    large = expectancy([
        Fill(d(1), "A", "buy", 500, 100.0), Fill(d(2), "A", "sell", 500, 90.0),
    ])
    assert small.expectancy_per_trade == pytest.approx(-10.0)
    assert large.expectancy_per_trade == pytest.approx(-5000.0)


# ======================================================================
# Net of costs — T8's actual criterion
# ======================================================================
def test_costs_are_subtracted() -> None:
    """T8: "per-trade expected value after spread, slippage, and commission
    ... do not assume frictionless fills.\""""
    gross = expectancy([
        Fill(d(1), "A", "buy", 100, 10.0), Fill(d(2), "A", "sell", 100, 11.0),
    ])
    net = expectancy([
        Fill(d(1), "A", "buy", 100, 10.0, commission=5.0, slippage=3.0, spread=2.0),
        Fill(d(2), "A", "sell", 100, 11.0, commission=5.0, slippage=3.0, spread=2.0),
    ])
    assert gross.net_pnl == pytest.approx(100.0)
    assert net.net_pnl == pytest.approx(80.0)
    assert net.total_costs == pytest.approx(20.0)


def test_costs_can_flip_a_winner_into_a_loser() -> None:
    """The reason the criterion says 'net'. This is how retail algo systems
    die: real directional skill, eaten by turnover."""
    got = expectancy([
        Fill(d(1), "A", "buy", 10, 100.0, commission=6.0),
        Fill(d(2), "A", "sell", 10, 100.5, commission=6.0),
    ])
    assert got.net_pnl == pytest.approx(-7.0)
    assert got.wins == 0 and got.losses == 1


def test_partial_exit_amortises_the_entry_cost() -> None:
    """Selling half a lot should carry half its entry cost, not all of it."""
    trips, _ = match_round_trips([
        Fill(d(1), "A", "buy", 100, 10.0, commission=10.0),
        Fill(d(2), "A", "sell", 50, 11.0),
    ])
    assert len(trips) == 1
    assert trips[0].quantity == 50
    assert trips[0].costs == pytest.approx(5.0)


# ======================================================================
# The smaller defects found in the same read
# ======================================================================
def test_a_flat_round_trip_is_neither_a_win_nor_a_loss() -> None:
    """Upstream counts 0 as a loss, biasing win rate down and inflating the
    loss side of the profit factor."""
    got = expectancy([
        Fill(d(1), "A", "buy", 10, 100.0), Fill(d(2), "A", "sell", 10, 100.0),
        Fill(d(3), "A", "buy", 10, 100.0), Fill(d(4), "A", "sell", 10, 110.0),
    ])
    assert got.flat == 1
    assert got.wins == 1 and got.losses == 0
    assert got.win_rate_pct == pytest.approx(100.0), "one win, one flat, zero losses"


def test_an_unmatched_sell_is_surfaced_not_discarded() -> None:
    """Upstream drops it silently. A short sale or a data gap should be
    visible."""
    got = expectancy([
        Fill(d(1), "A", "buy", 10, 100.0),
        Fill(d(2), "A", "sell", 25, 110.0),
    ])
    assert got.round_trips == 1
    assert got.unmatched_sell_quantity == pytest.approx(15.0)


def test_fifo_order_is_preserved_across_lots() -> None:
    trips, _ = match_round_trips([
        Fill(d(1), "A", "buy", 10, 100.0),
        Fill(d(2), "A", "buy", 10, 200.0),
        Fill(d(3), "A", "sell", 15, 150.0),
    ])
    assert [t.quantity for t in trips] == [10, 5]
    assert trips[0].entry_price == 100.0, "the first lot must close first"
    assert trips[1].entry_price == 200.0


def test_tickers_do_not_cross_match() -> None:
    got = expectancy([
        Fill(d(1), "A", "buy", 10, 100.0),
        Fill(d(2), "B", "sell", 10, 100.0),
    ])
    assert got.round_trips == 0
    assert got.unmatched_sell_quantity == pytest.approx(10.0)


def test_no_trades_is_not_an_error() -> None:
    got = expectancy([])
    assert got.round_trips == 0 and got.expectancy_per_trade is None
    assert "no closed round trips" in got.render()


# ======================================================================
# Drawdown — magnitude AND duration
# ======================================================================
def test_drawdown_reports_magnitude_and_duration() -> None:
    """T8: "Report drawdown duration alongside magnitude. The number that
    decides whether a system keeps running is the one you can sit through.\""""
    curve = [(d(1), 100.0), (d(5), 120.0), (d(10), 90.0), (d(20), 130.0)]
    got = max_drawdown(curve)
    assert got.max_drawdown_pct == pytest.approx(-25.0)   # 120 -> 90
    assert got.peak_date == d(5) and got.trough_date == d(10)
    assert got.recovered is True and got.recovered_date == d(20)
    assert got.duration_days == 15, "peak to recovery, not peak to trough"


def test_unrecovered_drawdown_runs_to_the_end_of_the_curve() -> None:
    """An underwater system has a duration too — and it is the one you would
    actually have had to sit through."""
    curve = [(d(1), 100.0), (d(5), 120.0), (d(28), 80.0)]
    got = max_drawdown(curve)
    assert got.recovered is False
    assert got.duration_days == 23


def test_a_monotonic_curve_has_no_drawdown() -> None:
    got = max_drawdown([(d(1), 100.0), (d(2), 110.0), (d(3), 120.0)])
    assert got.max_drawdown_pct == 0.0 and got.duration_days == 0


def test_the_deepest_drawdown_wins_not_the_first() -> None:
    curve = [(d(1), 100.0), (d(2), 95.0), (d(3), 100.0), (d(4), 60.0), (d(5), 100.0)]
    assert max_drawdown(curve).max_drawdown_pct == pytest.approx(-40.0)


# ======================================================================
# Sharpe — the convention is the number
# ======================================================================
def test_sharpe_is_annualised_and_says_so() -> None:
    """SUPERSEDED.md: financetoolkit is PER-PERIOD, empyrical annualises,
    "15.88x apart under an identical name". A Sharpe with an unstated
    convention is not a number."""
    returns = [0.001, -0.002, 0.003, 0.0005, -0.001] * 40
    annual = annualised_sharpe(returns)
    per_period = per_period_sharpe(returns)
    assert annual is not None and per_period is not None
    assert annual / per_period == pytest.approx(math.sqrt(TRADING_DAYS), rel=1e-9)
    assert abs(annual / per_period - 15.87) < 0.05, "the recorded 15.88x gap"


def test_sharpe_needs_at_least_two_observations() -> None:
    assert annualised_sharpe([0.01]) is None
    assert annualised_sharpe([]) is None


def test_zero_volatility_has_no_sharpe() -> None:
    """Not infinity — undefined. A constant series has no risk-adjusted
    return to report."""
    assert annualised_sharpe([0.001] * 10) is None


def test_higher_risk_free_rate_lowers_sharpe() -> None:
    returns = [0.002, 0.001, 0.003, 0.0015] * 30
    assert annualised_sharpe(returns, 0.10) < annualised_sharpe(returns, 0.01)  # type: ignore[operator]


def test_near_constant_series_does_not_produce_an_astronomical_sharpe() -> None:
    """Regression. `sd == 0` was not enough: a constant series has zero
    variance in exact arithmetic but ~1e-19 in floating point, and dividing by
    that produced a Sharpe of 5.8e16 — a number that would sail through any
    plausibility check a human applied to a report."""
    for constant in (0.0, 0.001, -0.02, 1e-9):
        assert annualised_sharpe([constant] * 10) is None, f"constant {constant}"


def test_a_genuinely_tiny_but_real_variance_still_reports() -> None:
    """The guard must not swallow a real signal — it is scaled to the data,
    not an absolute floor."""
    returns = [0.001, 0.0011] * 20
    assert annualised_sharpe(returns) is not None
