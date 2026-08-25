"""Expectancy, drawdown and Sharpe for the eval harness.

    "Expectancy net of costs ... Answers 'could this trade unattended.'
     ... Nothing climbs the autonomy ladder without (2)."  -- TICKETS T8

WHY _analyze_trades WAS NOT PORTED
----------------------------------
T8 says to port DanisHack's backtest module wholesale, and VENDORING.md §6
says to verify `_analyze_trades` independently first "before trusting it"
because it gates a real decision. Verified at pinned SHA 6d7a3ab, against a
hand-built fixture:

    buy 1 share @ 100, sell @ 110      ->  +$10
    buy 1000 shares @ 100, sell @ 95   ->  -$5,000
                                           net -$4,990

    DanisHack reports:  win_rate 50.0%, profit_factor 2.00

A profit factor of 2.00 describes a strategy that lost four thousand nine
hundred and ninety dollars. Three causes, all structural:

  1. a round trip is appended ONCE per FIFO match, **unweighted by quantity**,
     so a 1-share match and a 1000-share match count equally;
  2. `profit_factor` sums **percentages**, not currency;
  3. returns come from raw trade prices, so the number is **gross** — while
     T8's criterion is explicitly "net of spread, slippage and commission",
     and "do not assume frictionless fills".

Two further defects found in the same read: a flat round trip (0%) is counted
as a loss, and a sell with no matching buy is silently discarded.

So this module computes expectancy in **currency, quantity-weighted, net of
costs**. DanisHack's Sharpe and drawdown are fine and are used as written --
its Sharpe IS annualised, which is the thing SUPERSEDED.md flagged.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

#: Annualisation factor for daily returns. Named, because SUPERSEDED.md
#: records that `financetoolkit.get_sharpe_ratio` is PER-PERIOD while
#: empyrical/quantstats annualise -- "15.88x apart under an identical name".
TRADING_DAYS = 252
DEFAULT_RISK_FREE = 0.04


@dataclass(frozen=True)
class Fill:
    """One execution. Costs are per-fill and in CURRENCY, never assumed away."""

    date: date
    ticker: str
    action: str          # "buy" | "sell"
    quantity: float
    price: float
    commission: float = 0.0
    slippage: float = 0.0
    spread: float = 0.0

    @property
    def costs(self) -> float:
        return self.commission + self.slippage + self.spread


@dataclass
class _Lot:
    """An open buy lot in the FIFO queue.

    A dataclass rather than a heterogeneous list: the first version used
    `list[float | date]` and every field access needed a cast, which is how a
    date ends up multiplied by a quantity.
    """

    quantity: float
    price: float
    cost_per_share: float
    opened: date


@dataclass(frozen=True)
class RoundTrip:
    """A matched buy->sell pair, carrying the quantity it was actually done in."""

    ticker: str
    quantity: float
    entry_price: float
    exit_price: float
    costs: float
    opened: date
    closed: date

    @property
    def gross_pnl(self) -> float:
        return (self.exit_price - self.entry_price) * self.quantity

    @property
    def net_pnl(self) -> float:
        """The only P&L this module reports. T8: net of costs, or it is not
        the number that gates autonomy."""
        return self.gross_pnl - self.costs

    @property
    def held_days(self) -> int:
        return (self.closed - self.opened).days


@dataclass(frozen=True)
class Expectancy:
    round_trips: int
    unmatched_sell_quantity: float
    wins: int
    losses: int
    flat: int
    win_rate_pct: float | None
    avg_win: float | None
    avg_loss: float | None
    expectancy_per_trade: float | None
    profit_factor: float | None
    net_pnl: float
    total_costs: float

    def render(self) -> str:
        if self.expectancy_per_trade is None:
            return "expectancy: no closed round trips"
        return (
            f"expectancy ${self.expectancy_per_trade:,.2f}/trade net of costs · "
            f"win rate {self.win_rate_pct:.1f}% · "
            f"profit factor {self.profit_factor or float('nan'):.2f} · "
            f"net ${self.net_pnl:,.2f} after ${self.total_costs:,.2f} of costs"
        )


def match_round_trips(fills: list[Fill]) -> tuple[list[RoundTrip], float]:
    """FIFO, quantity-weighted, cost-carrying.

    Returns the round trips AND the sell quantity that matched nothing.
    Upstream discards that silently; a short sale or a data gap should be
    visible, not absorbed.
    """
    queue: dict[str, list[_Lot]] = {}
    trips: list[RoundTrip] = []
    unmatched = 0.0

    for fill in sorted(fills, key=lambda f: (f.date, f.action)):
        book = queue.setdefault(fill.ticker, [])
        if fill.action == "buy":
            # Cost of entry is amortised across the shares it bought, so a
            # partial exit carries only its share of it.
            book.append(_Lot(
                quantity=fill.quantity,
                price=fill.price,
                cost_per_share=fill.costs / max(fill.quantity, 1e-9),
                opened=fill.date,
            ))
            continue

        remaining = fill.quantity
        exit_cost_per_share = fill.costs / max(fill.quantity, 1e-9)
        while remaining > 1e-9 and book:
            lot = book[0]
            matched = min(remaining, lot.quantity)
            trips.append(RoundTrip(
                ticker=fill.ticker,
                quantity=matched,
                entry_price=lot.price,
                exit_price=fill.price,
                costs=(lot.cost_per_share + exit_cost_per_share) * matched,
                opened=lot.opened,
                closed=fill.date,
            ))
            remaining -= matched
            lot.quantity -= matched
            if lot.quantity <= 1e-9:
                book.pop(0)
        if remaining > 1e-9:
            unmatched += remaining

    return trips, unmatched


def expectancy(fills: list[Fill]) -> Expectancy:
    """Per-trade expected value in CURRENCY, net of costs."""
    trips, unmatched = match_round_trips(fills)
    if not trips:
        return Expectancy(
            round_trips=0, unmatched_sell_quantity=unmatched, wins=0, losses=0,
            flat=0, win_rate_pct=None, avg_win=None, avg_loss=None,
            expectancy_per_trade=None, profit_factor=None, net_pnl=0.0,
            total_costs=0.0,
        )

    pnls = [t.net_pnl for t in trips]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    # A flat trade is neither. Upstream counts 0 as a loss, which biases the
    # win rate down and inflates the loss side of the profit factor.
    flat = [p for p in pnls if p == 0]

    gross_wins = sum(wins)
    gross_losses = abs(sum(losses))
    decided = len(wins) + len(losses)

    return Expectancy(
        round_trips=len(trips),
        unmatched_sell_quantity=unmatched,
        wins=len(wins),
        losses=len(losses),
        flat=len(flat),
        win_rate_pct=(len(wins) / decided * 100) if decided else None,
        avg_win=(gross_wins / len(wins)) if wins else None,
        avg_loss=(-gross_losses / len(losses)) if losses else None,
        expectancy_per_trade=sum(pnls) / len(pnls),
        profit_factor=(gross_wins / gross_losses) if gross_losses > 0 else None,
        net_pnl=sum(pnls),
        total_costs=sum(t.costs for t in trips),
    )


@dataclass(frozen=True)
class Drawdown:
    """T8: "Report drawdown DURATION alongside magnitude. The number that
    decides whether a system keeps running is the one you can sit through
    without switching it off at the worst possible moment.\""""

    max_drawdown_pct: float
    peak_date: date | None = None
    trough_date: date | None = None
    recovered_date: date | None = None
    duration_days: int = 0
    recovered: bool = False


def max_drawdown(curve: list[tuple[date, float]]) -> Drawdown:
    if len(curve) < 2:
        return Drawdown(0.0)

    peak_value = curve[0][1]
    peak_date = curve[0][0]
    worst = 0.0
    worst_peak = worst_trough = None
    recovered_on: date | None = None
    tracking_peak: date | None = None

    for when, value in curve:
        if value > peak_value:
            peak_value, peak_date = value, when
            if worst_trough is not None and recovered_on is None and tracking_peak == worst_peak:
                recovered_on = when
        elif peak_value > 0:
            drop = (value - peak_value) / peak_value
            if drop < worst:
                worst, worst_peak, worst_trough = drop, peak_date, when
                tracking_peak, recovered_on = peak_date, None

    end = recovered_on or curve[-1][0]
    duration = (end - worst_peak).days if worst_peak is not None else 0
    return Drawdown(
        max_drawdown_pct=round(worst * 100, 4),
        peak_date=worst_peak,
        trough_date=worst_trough,
        recovered_date=recovered_on,
        duration_days=duration,
        recovered=recovered_on is not None,
    )


def annualised_sharpe(
    daily_returns: list[float], risk_free_annual: float = DEFAULT_RISK_FREE
) -> float | None:
    """ANNUALISED. The convention is in the name, and asserted by a test.

    SUPERSEDED.md: `financetoolkit.get_sharpe_ratio` is PER-PERIOD while
    empyrical and quantstats annualise — "15.88x apart under an identical
    name". A Sharpe with an unstated convention is not a number.
    """
    if len(daily_returns) < 2:
        return None
    mean = sum(daily_returns) / len(daily_returns)
    variance = sum((r - mean) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
    sd = math.sqrt(variance)
    # `sd == 0` is not enough. A constant series has zero variance in exact
    # arithmetic but ~1e-19 in floating point, and dividing by that produced a
    # Sharpe of 5.8e16 — a number that would sail through any plausibility
    # check a human applied to a report. Scale the threshold to the data.
    scale = max(abs(mean), 1e-12)
    if sd <= scale * 1e-9:
        return None
    excess_daily = mean - risk_free_annual / TRADING_DAYS
    return (excess_daily / sd) * math.sqrt(TRADING_DAYS)


def per_period_sharpe(
    daily_returns: list[float], risk_free_annual: float = DEFAULT_RISK_FREE
) -> float | None:
    """The OTHER convention, provided only so a test can show they differ.

    Never report this one. It exists to make the gap measurable rather than
    theoretical.
    """
    annual = annualised_sharpe(daily_returns, risk_free_annual)
    return None if annual is None else annual / math.sqrt(TRADING_DAYS)
