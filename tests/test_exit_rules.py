"""Exit-rule engine.

The first block ports DanisHack's own stop-order tests at pinned SHA
6d7a3ab, adapted to our PositionState. Porting the tests alongside the code is
the reason vendoring is safer than rewriting — and per VENDORING.md §6, the
count is stated: upstream has 8 stop-order tests, all 8 are represented here.

Carried caveat from VENDORING.md §6: those tests were written by the same
author in the same burst as the code, so they establish self-consistency, not
correctness against a specification. Every one of them is re-derived by hand
below rather than copied on faith — the arithmetic in each docstring is the
check.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from desk.exit_rules import (
    EXIT,
    HOLD,
    PRECEDENCE,
    BadPositionState,
    Decision,
    PositionState,
    Rule,
    RuleConfigError,
    RuleKind,
    Unit,
    evaluate,
    summarise,
)

TODAY = date(2026, 8, 21)


def pos(
    price: float,
    cost: float = 100.0,
    *,
    ticker: str = "AAPL",
    qty: float = 10.0,
    opened_at: date | None = None,
    high_water_mark: float | None = None,
    thesis_invalidated: bool = False,
) -> PositionState:
    return PositionState(
        ticker=ticker,
        qty=qty,
        avg_cost=cost,
        current_price=price,
        as_of=TODAY,
        opened_at=opened_at,
        high_water_mark=high_water_mark,
        thesis_invalidated=thesis_invalidated,
    )


# ======================================================================
# Ported from DanisHack tests/test_portfolio_tracker.py (8 stop-order tests)
# ======================================================================
def test_fixed_stop_loss_triggers() -> None:
    """Upstream: cost 100, price 85, stop 10%. 15% loss >= 10% -> fires."""
    rules = [Rule(RuleKind.FIXED_STOP, 0.10, Unit.PCT)]
    got = evaluate(pos(85.0), rules)
    assert got.action == EXIT
    assert got.triggered is not None and got.triggered.reason == "fixed_stop"


def test_fixed_stop_loss_does_not_trigger_below_threshold() -> None:
    """cost 100, price 95, stop 10%. 5% loss < 10% -> holds."""
    assert evaluate(pos(95.0), [Rule(RuleKind.FIXED_STOP, 0.10, Unit.PCT)]).action == HOLD


def test_trailing_stop_triggers() -> None:
    """high-water 120, price 100, trail 10%. Down 16.67% >= 10% -> fires."""
    got = evaluate(
        pos(100.0, high_water_mark=120.0), [Rule(RuleKind.TRAILING_STOP, 0.10)]
    )
    assert got.action == EXIT
    assert got.triggered is not None and got.triggered.reason == "trailing_stop"


def test_trailing_stop_does_not_trigger_within_threshold() -> None:
    """high-water 120, price 115, trail 10%. Down 4.17% < 10% -> holds."""
    assert evaluate(
        pos(115.0, high_water_mark=120.0), [Rule(RuleKind.TRAILING_STOP, 0.10)]
    ).action == HOLD


def test_take_profit_triggers() -> None:
    """cost 100, price 125, target 20%. Up 25% >= 20% -> fires."""
    got = evaluate(pos(125.0), [Rule(RuleKind.TAKE_PROFIT, 0.20, Unit.PCT)])
    assert got.action == EXIT
    assert got.triggered is not None and got.triggered.reason == "take_profit"


def test_take_profit_does_not_trigger_below_threshold() -> None:
    """cost 100, price 115, target 20%. Up 15% < 20% -> holds."""
    assert evaluate(pos(115.0), [Rule(RuleKind.TAKE_PROFIT, 0.20, Unit.PCT)]).action == HOLD


def test_fixed_stop_takes_priority_over_trailing() -> None:
    """Upstream's precedence test, same name.

    cost 100, high-water 100, price 85, both stops at 10%. BOTH conditions
    hold — 15% off cost and 15% off the high-water mark. Upstream short-
    circuits and reports `stop_loss`; so do we.
    """
    rules = [
        Rule(RuleKind.TRAILING_STOP, 0.10),
        Rule(RuleKind.FIXED_STOP, 0.10, Unit.PCT),
    ]
    got = evaluate(pos(85.0, high_water_mark=100.0), rules)
    assert got.triggered is not None
    assert got.triggered.reason == "fixed_stop", "precedence inverted"
    # Our addition: the loser is retained rather than discarded.
    assert [t.reason for t in got.also_fired] == ["trailing_stop"]


def test_multiple_positions_checked_independently() -> None:
    """Upstream drops AAPL and keeps MSFT. Ours is per-position by
    construction, so this asserts the same outcome across two evaluations."""
    rules = [Rule(RuleKind.FIXED_STOP, 0.10, Unit.PCT)]
    aapl = evaluate(pos(85.0, 100.0, ticker="AAPL"), rules)
    msft = evaluate(pos(380.0, 400.0, ticker="MSFT"), rules)
    assert aapl.action == EXIT
    assert msft.action == HOLD, "MSFT is down 5%, below the 10% stop"


# ======================================================================
# Boundaries — upstream uses >=, and that is load-bearing
# ======================================================================
@pytest.mark.parametrize(
    ("price", "expected"),
    [(90.0, EXIT), (90.01, HOLD)],
    ids=["exactly at the stop fires", "a cent above holds"],
)
def test_fixed_stop_boundary_is_inclusive(price: float, expected: str) -> None:
    assert evaluate(pos(price), [Rule(RuleKind.FIXED_STOP, 0.10, Unit.PCT)]).action == expected


def test_take_profit_boundary_is_inclusive() -> None:
    assert evaluate(pos(120.0), [Rule(RuleKind.TAKE_PROFIT, 0.20, Unit.PCT)]).action == EXIT


# ======================================================================
# Units are explicit — the silent-failure class this project keeps finding
# ======================================================================
def test_absolute_price_stop() -> None:
    stop = Rule(RuleKind.FIXED_STOP, 150.0, Unit.PRICE)
    assert evaluate(pos(149.0, 160.0), [stop]).action == EXIT
    assert evaluate(pos(151.0, 160.0), [stop]).action == HOLD


def test_a_pct_threshold_of_one_or_more_is_refused() -> None:
    """8 is not 800%, it is a typo for 0.08 — and a rule that can never fire
    is a stop that silently is not there."""
    with pytest.raises(RuleConfigError, match="fraction"):
        Rule(RuleKind.TRAILING_STOP, 8.0, Unit.PCT)


def test_trailing_stop_cannot_be_an_absolute_price() -> None:
    """A trailing stop expressed as a fixed price is not a trailing stop."""
    with pytest.raises(RuleConfigError, match="cannot be expressed"):
        Rule(RuleKind.TRAILING_STOP, 150.0, Unit.PRICE)


def test_units_are_not_inferred_from_magnitude() -> None:
    """A sub-$1 stock with a $0.40 stop must not be read as 40%."""
    penny = pos(0.35, 0.50, ticker="PENNY")
    as_price = evaluate(penny, [Rule(RuleKind.FIXED_STOP, 0.40, Unit.PRICE)])
    as_pct = evaluate(penny, [Rule(RuleKind.FIXED_STOP, 0.40, Unit.PCT)])
    assert as_price.action == EXIT, "0.35 <= 0.40 stop"
    assert as_pct.action == HOLD, "down 30%, below a 40% stop"


def test_missing_threshold_is_refused() -> None:
    with pytest.raises(RuleConfigError, match="needs a threshold"):
        Rule(RuleKind.FIXED_STOP)


def test_non_positive_threshold_is_refused() -> None:
    with pytest.raises(RuleConfigError, match="must be positive"):
        Rule(RuleKind.TIME_STOP, -3.0)


# ======================================================================
# The two rules upstream lacks
# ======================================================================
def test_time_stop_fires_after_the_horizon() -> None:
    old = pos(100.0, opened_at=TODAY - timedelta(days=30))
    got = evaluate(old, [Rule(RuleKind.TIME_STOP, 21, Unit.DAYS)])
    assert got.action == EXIT
    assert got.triggered is not None and "held 30d" in got.triggered.detail


def test_time_stop_holds_inside_the_horizon() -> None:
    fresh = pos(100.0, opened_at=TODAY - timedelta(days=5))
    assert evaluate(fresh, [Rule(RuleKind.TIME_STOP, 21, Unit.DAYS)]).action == HOLD


def test_time_stop_does_not_fire_on_unknown_age() -> None:
    """Without opened_at we cannot know. Firing would exit every freshly
    imported position on its first health check."""
    assert evaluate(pos(100.0, opened_at=None), [Rule(RuleKind.TIME_STOP, 21)]).action == HOLD


def test_thesis_invalidation_fires_on_the_flag() -> None:
    got = evaluate(
        pos(100.0, thesis_invalidated=True),
        [Rule(RuleKind.THESIS_INVALIDATION, note="downgrade + guidance cut")],
    )
    assert got.action == EXIT
    assert got.triggered is not None
    assert got.triggered.detail == "downgrade + guidance cut"


def test_thesis_invalidation_holds_when_not_flagged() -> None:
    assert evaluate(pos(100.0), [Rule(RuleKind.THESIS_INVALIDATION)]).action == HOLD


# ======================================================================
# Precedence across all five
# ======================================================================
def test_precedence_order_is_the_documented_one() -> None:
    assert PRECEDENCE == (
        RuleKind.FIXED_STOP, RuleKind.TRAILING_STOP, RuleKind.TAKE_PROFIT,
        RuleKind.TIME_STOP, RuleKind.THESIS_INVALIDATION,
    ), "the ported precedence was changed; upstream's first three must lead"


def test_all_five_firing_at_once_resolves_to_the_fixed_stop() -> None:
    """Two simultaneous triggers resolve per the documented precedence — T4's
    Done criterion, taken to its extreme with all five armed."""
    state = PositionState(
        ticker="AAPL", qty=10, avg_cost=100.0, current_price=85.0, as_of=TODAY,
        opened_at=TODAY - timedelta(days=90), high_water_mark=200.0,
        thesis_invalidated=True,
    )
    rules = [
        Rule(RuleKind.THESIS_INVALIDATION),
        Rule(RuleKind.TIME_STOP, 21, Unit.DAYS),
        Rule(RuleKind.TAKE_PROFIT, 0.01, Unit.PCT),   # cannot fire: price < cost
        Rule(RuleKind.TRAILING_STOP, 0.10),
        Rule(RuleKind.FIXED_STOP, 0.10, Unit.PCT),
    ]
    got = evaluate(state, rules)
    assert got.triggered is not None and got.triggered.reason == "fixed_stop"
    assert [t.reason for t in got.also_fired] == [
        "trailing_stop", "time_stop", "thesis_invalidation",
    ], "losers must be retained in precedence order, and take_profit must not fire"


def test_rule_order_in_the_list_does_not_affect_the_outcome() -> None:
    """Precedence comes from PRECEDENCE, not from however book.yaml happens
    to be written."""
    state = pos(85.0, high_water_mark=100.0)
    a = [Rule(RuleKind.FIXED_STOP, 0.10, Unit.PCT), Rule(RuleKind.TRAILING_STOP, 0.10)]
    b = list(reversed(a))
    assert evaluate(state, a).triggered == evaluate(state, b).triggered


def test_one_exit_per_position_per_cycle() -> None:
    """Upstream's "one sell per position per cycle", preserved."""
    got = evaluate(
        pos(85.0, high_water_mark=200.0),
        [Rule(RuleKind.FIXED_STOP, 0.10, Unit.PCT), Rule(RuleKind.TRAILING_STOP, 0.10)],
    )
    assert got.triggered is not None
    assert isinstance(got.triggered.reason, str)   # exactly one winner, not a list


def test_unarmed_rules_are_skipped() -> None:
    assert evaluate(
        pos(85.0), [Rule(RuleKind.FIXED_STOP, 0.10, Unit.PCT, armed=False)]
    ).action == HOLD


def test_no_rules_means_hold() -> None:
    """An UNMANAGED position has no overlay. It holds, and the health report
    flags it as needing stops — it must not be treated as an exit."""
    assert evaluate(pos(1.0, 100.0), []).action == HOLD


# ======================================================================
# Bad data must not read as an all-clear
# ======================================================================
@pytest.mark.parametrize(
    ("price", "cost", "hwm"),
    [(0.0, 100.0, None), (-5.0, 100.0, None), (100.0, 0.0, None), (100.0, 100.0, -1.0)],
    ids=["zero price", "negative price", "zero cost", "negative high-water"],
)
def test_bad_position_state_raises(price: float, cost: float, hwm: float | None) -> None:
    """DELIBERATE DEVIATION: upstream `continue`s past a non-positive price.
    Here that would render HOLD on the strength of unreadable data, and a
    health report that says HOLD because it could not read the price reads as
    an all-clear."""
    with pytest.raises(BadPositionState):
        PositionState(ticker="X", qty=1, avg_cost=cost, current_price=price,
                      as_of=TODAY, high_water_mark=hwm)


def test_high_water_mark_defaults_to_cost() -> None:
    """Matches upstream's pos.get("high_water_mark", avg_cost)."""
    assert pos(100.0, 100.0).high_water_mark == 100.0


# ======================================================================
# The seeded-book Done criterion
# ======================================================================
def test_seeded_five_position_book_yields_five_hold_zero_exits() -> None:
    """T4 Done: 'seeded 5-position book yields 5x HOLD · 0 EXITS TRIGGERED'.

    The five names are DESK_DESIGN §1 W1's own example book.
    """
    book = [
        ("TIVO", 3.10, 3.00), ("NVDA", 191.0, 150.0), ("MU", 106.0, 92.0),
        ("GOOG", 189.0, 164.0), ("GIV", 12.40, 12.00),
    ]
    rules = [
        Rule(RuleKind.FIXED_STOP, 0.25, Unit.PCT),
        Rule(RuleKind.TAKE_PROFIT, 0.50, Unit.PCT),
    ]
    decisions = [
        evaluate(pos(price, cost, ticker=ticker), rules) for ticker, price, cost in book
    ]
    assert summarise(decisions) == "5× HOLD · 0 EXITS TRIGGERED"


def test_summarise_counts_exits() -> None:
    decisions = [
        Decision(ticker="A", action=HOLD),
        Decision(ticker="B", action=HOLD),
        evaluate(pos(50.0), [Rule(RuleKind.FIXED_STOP, 0.10, Unit.PCT)]),
    ]
    assert summarise(decisions) == "2× HOLD · 1 EXITS TRIGGERED"


def test_absolute_price_take_profit() -> None:
    """The form config/book.example.yaml actually uses (`take_profit: 220.00`).

    Found by the branch-coverage gate at 97%: the price branch of _take_profit
    was the one path with no test, and it is the path the shipped example
    config takes.
    """
    target = Rule(RuleKind.TAKE_PROFIT, 220.0, Unit.PRICE)
    assert evaluate(pos(221.0, 150.0), [target]).action == EXIT
    assert evaluate(pos(219.0, 150.0), [target]).action == HOLD
    assert evaluate(pos(220.0, 150.0), [target]).action == EXIT, "boundary is inclusive"


def test_absolute_price_stop_boundary_is_inclusive() -> None:
    stop = Rule(RuleKind.FIXED_STOP, 150.0, Unit.PRICE)
    assert evaluate(pos(150.0, 160.0), [stop]).action == EXIT


def test_two_rules_of_the_same_kind_report_one_trigger() -> None:
    """Found by mutation testing, NOT by coverage.

    Deleting the `break` in evaluate() left all 37 tests green at 100% branch
    coverage, because no test had two armed rules of the same kind. Two fixed
    stops both firing is one condition, not two, and double-counting it would
    inflate `also_fired` with a duplicate reason.
    """
    rules = [
        Rule(RuleKind.FIXED_STOP, 0.10, Unit.PCT),
        Rule(RuleKind.FIXED_STOP, 0.05, Unit.PCT),   # also fires at price 85
    ]
    got = evaluate(pos(85.0), rules)
    assert got.action == EXIT
    assert got.triggered is not None and got.triggered.reason == "fixed_stop"
    assert got.also_fired == (), "the same kind must not be counted twice"
