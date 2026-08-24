"""Exit-rule evaluation. Deterministic, pure, and no LLM calls — T4 says so
explicitly, and DESK_DESIGN §1 W1 says why: "This is deterministic rule
evaluation, not an LLM committee. The LLM only writes the summary prose. Keep
it that way — it's the cheapest and most reliable part of the system."

PORTED FROM
-----------
`DanisHack/ai-hedge-fund`, `src/backtest/portfolio_tracker.py::check_stop_orders`
at pinned SHA 6d7a3abb269c96c7e25ac89bf05c8208784ccd18 (MIT). See
desk/vendor/danishack/PROVENANCE.md for the statement of changes.

Three of the five rules, and — the part actually worth adopting — the trigger
precedence. Upstream resolves it by short-circuiting on `if reason is None` in
a fixed order: fixed stop, then trailing, then take-profit. That ordering is
preserved here EXACTLY, including the boundary being `>=` rather than `>`.
Upstream has a test named `test_fixed_stop_takes_priority_over_trailing`; ours
is `test_fixed_stop_takes_priority_over_trailing` too, for the same reason.

THIS MODULE IS PURE
-------------------
No database, no network, no clock. `PositionState` carries everything a rule
needs, and `desk/health.py` (T5) is what assembles one from the book and a
market feed. That split is what makes 100% branch coverage reachable rather
than aspirational.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

HOLD = "HOLD"
EXIT = "EXIT"


class RuleKind(StrEnum):
    FIXED_STOP = "fixed_stop"
    TRAILING_STOP = "trailing_stop"
    TAKE_PROFIT = "take_profit"
    #: The two rules upstream lacks (T4).
    TIME_STOP = "time_stop"
    THESIS_INVALIDATION = "thesis_invalidation"


class Unit(StrEnum):
    PRICE = "price"      # an absolute price, e.g. stop at $150.00
    PCT = "pct"          # a fraction of cost or of the high-water mark, e.g. 0.08
    DAYS = "days"        # calendar days held
    FLAG = "flag"        # no threshold; the rule is a switch


#: PRECEDENCE IS THE POINT OF ADOPTING THIS.
#:
#: "That precedence detail is exactly the kind of thing you get wrong on a
#:  first pass and only notice when two rules fire on the same bar." (T4)
#:
#: The first three are upstream's order, unchanged. The two new rules are
#: APPENDED rather than interleaved, so adopting the port did not quietly
#: rewrite the semantics it was adopted for. Rationale for the tail order:
#: a time stop is the weakest signal (nothing has gone wrong, the clock ran
#: out), and thesis invalidation is a human judgement that should be reported
#: as itself rather than masked by whichever price rule happened to fire.
PRECEDENCE: tuple[RuleKind, ...] = (
    RuleKind.FIXED_STOP,
    RuleKind.TRAILING_STOP,
    RuleKind.TAKE_PROFIT,
    RuleKind.TIME_STOP,
    RuleKind.THESIS_INVALIDATION,
)

#: Which units are meaningful for which rule. A trailing stop expressed as an
#: absolute price is not a trailing stop, so it is refused rather than
#: silently reinterpreted.
VALID_UNITS: dict[RuleKind, frozenset[Unit]] = {
    RuleKind.FIXED_STOP: frozenset({Unit.PRICE, Unit.PCT}),
    RuleKind.TRAILING_STOP: frozenset({Unit.PCT}),
    RuleKind.TAKE_PROFIT: frozenset({Unit.PRICE, Unit.PCT}),
    RuleKind.TIME_STOP: frozenset({Unit.DAYS}),
    RuleKind.THESIS_INVALIDATION: frozenset({Unit.FLAG}),
}

DEFAULT_UNITS: dict[RuleKind, Unit] = {
    RuleKind.FIXED_STOP: Unit.PRICE,
    RuleKind.TRAILING_STOP: Unit.PCT,
    RuleKind.TAKE_PROFIT: Unit.PRICE,
    RuleKind.TIME_STOP: Unit.DAYS,
    RuleKind.THESIS_INVALIDATION: Unit.FLAG,
}


class RuleConfigError(ValueError):
    """A rule that cannot be evaluated as written. Refused at construction."""


class BadPositionState(ValueError):
    """Non-positive price or cost.

    DELIBERATE DEVIATION FROM UPSTREAM: `check_stop_orders` does
    `if price is None or price <= 0: continue`, silently skipping the
    position. For a backtester that is reasonable. Here it would render a
    position as HOLD on the strength of bad data, and a health report that
    says HOLD because it could not read the price is worse than one that
    refuses — it reads as an all-clear. T2's guards exist to make this
    unreachable; this is the backstop.
    """


@dataclass(frozen=True)
class Rule:
    kind: RuleKind
    threshold: float | None = None
    unit: Unit | None = None
    armed: bool = True
    note: str | None = None

    def __post_init__(self) -> None:
        unit = self.unit or DEFAULT_UNITS[self.kind]
        object.__setattr__(self, "unit", unit)
        if unit not in VALID_UNITS[self.kind]:
            raise RuleConfigError(
                f"{self.kind.value} cannot be expressed in {unit.value}; "
                f"valid units are {sorted(u.value for u in VALID_UNITS[self.kind])}"
            )
        if unit is Unit.FLAG:
            return
        if self.threshold is None:
            raise RuleConfigError(f"{self.kind.value} needs a threshold")
        if self.threshold <= 0:
            raise RuleConfigError(
                f"{self.kind.value} threshold must be positive, got {self.threshold}"
            )
        if unit is Unit.PCT and self.threshold >= 1:
            # 0.08 is 8%; 8 is not 800%, it is a typo. Refusing beats
            # interpreting -- a rule that can never fire is a stop that
            # silently is not there.
            raise RuleConfigError(
                f"{self.kind.value} is a fraction: {self.threshold} should be "
                f"{self.threshold / 100:g} for {self.threshold:g}%. A pct "
                "threshold >= 1 would never fire."
            )


@dataclass(frozen=True)
class PositionState:
    """Everything a rule needs, and nothing it does not.

    `high_water_mark` defaults to `avg_cost`, matching upstream's
    `pos.get("high_water_mark", avg_cost)`.
    """

    ticker: str
    qty: float
    avg_cost: float
    current_price: float
    as_of: date
    opened_at: date | None = None
    high_water_mark: float | None = None
    thesis_invalidated: bool = False
    account: str = ""

    def __post_init__(self) -> None:
        if self.current_price <= 0:
            raise BadPositionState(f"{self.ticker}: price {self.current_price} is not positive")
        if self.avg_cost <= 0:
            raise BadPositionState(f"{self.ticker}: avg_cost {self.avg_cost} is not positive")
        if self.high_water_mark is None:
            object.__setattr__(self, "high_water_mark", self.avg_cost)
        elif self.high_water_mark <= 0:
            raise BadPositionState(
                f"{self.ticker}: high_water_mark {self.high_water_mark} is not positive"
            )

    @property
    def days_held(self) -> int | None:
        return None if self.opened_at is None else (self.as_of - self.opened_at).days


@dataclass(frozen=True)
class Trigger:
    kind: RuleKind
    reason: str
    detail: str


@dataclass(frozen=True)
class Decision:
    """At most ONE exit per position per cycle — upstream's "one sell per
    position per cycle", preserved.

    `also_fired` is an ADDITION. Upstream returns a single reason and discards
    the rest; for an audit trail, knowing that the thesis was already dead
    when the stop fired is worth more than the two bytes it costs.
    """

    ticker: str
    action: str
    triggered: Trigger | None = None
    also_fired: tuple[Trigger, ...] = field(default_factory=tuple)

    @property
    def exited(self) -> bool:
        return self.action == EXIT


# --------------------------------------------------------------- predicates
def _fixed_stop(state: PositionState, rule: Rule) -> Trigger | None:
    assert rule.threshold is not None
    if rule.unit is Unit.PRICE:
        if state.current_price <= rule.threshold:
            return Trigger(rule.kind, "fixed_stop",
                           f"price {state.current_price:g} <= stop {rule.threshold:g}")
        return None
    loss_pct = (state.avg_cost - state.current_price) / state.avg_cost
    if loss_pct >= rule.threshold:
        return Trigger(rule.kind, "fixed_stop",
                       f"down {loss_pct:.2%} from cost, limit {rule.threshold:.2%}")
    return None


def _trailing_stop(state: PositionState, rule: Rule) -> Trigger | None:
    assert rule.threshold is not None and state.high_water_mark is not None
    drop = (state.high_water_mark - state.current_price) / state.high_water_mark
    if drop >= rule.threshold:
        return Trigger(rule.kind, "trailing_stop",
                       f"down {drop:.2%} from high {state.high_water_mark:g}, "
                       f"limit {rule.threshold:.2%}")
    return None


def _take_profit(state: PositionState, rule: Rule) -> Trigger | None:
    assert rule.threshold is not None
    if rule.unit is Unit.PRICE:
        if state.current_price >= rule.threshold:
            return Trigger(rule.kind, "take_profit",
                           f"price {state.current_price:g} >= target {rule.threshold:g}")
        return None
    gain = (state.current_price - state.avg_cost) / state.avg_cost
    if gain >= rule.threshold:
        return Trigger(rule.kind, "take_profit",
                       f"up {gain:.2%} from cost, target {rule.threshold:.2%}")
    return None


def _time_stop(state: PositionState, rule: Rule) -> Trigger | None:
    assert rule.threshold is not None
    held = state.days_held
    if held is None:
        # No opened_at means we cannot know. Not firing is correct: a time
        # stop that triggers on unknown age would exit every freshly imported
        # position on its first health check.
        return None
    if held >= rule.threshold:
        return Trigger(rule.kind, "time_stop",
                       f"held {held}d, limit {rule.threshold:g}d")
    return None


def _thesis_invalidation(state: PositionState, rule: Rule) -> Trigger | None:
    if state.thesis_invalidated:
        return Trigger(rule.kind, "thesis_invalidation",
                       rule.note or "thesis marked invalid")
    return None


_PREDICATES = {
    RuleKind.FIXED_STOP: _fixed_stop,
    RuleKind.TRAILING_STOP: _trailing_stop,
    RuleKind.TAKE_PROFIT: _take_profit,
    RuleKind.TIME_STOP: _time_stop,
    RuleKind.THESIS_INVALIDATION: _thesis_invalidation,
}


def evaluate(state: PositionState, rules: list[Rule]) -> Decision:
    """Evaluate in PRECEDENCE order. First armed rule that fires wins."""
    fired: list[Trigger] = []
    by_kind: dict[RuleKind, list[Rule]] = {}
    for rule in rules:
        if rule.armed:
            by_kind.setdefault(rule.kind, []).append(rule)

    for kind in PRECEDENCE:
        for rule in by_kind.get(kind, []):
            hit = _PREDICATES[kind](state, rule)
            if hit is not None:
                fired.append(hit)
                # One trigger per KIND. Two armed rules of the same kind is
                # unusual but legal (two fixed stops from an edited book);
                # the first that fires, in book order, is the one reported.
                # Reporting both would double-count a single condition.
                break

    if not fired:
        return Decision(ticker=state.ticker, action=HOLD)
    return Decision(
        ticker=state.ticker, action=EXIT, triggered=fired[0], also_fired=tuple(fired[1:])
    )


def summarise(decisions: list[Decision]) -> str:
    """The observed W1 output format: `5× HOLD · 0 EXITS TRIGGERED`."""
    exits = [d for d in decisions if d.exited]
    holds = len(decisions) - len(exits)
    return f"{holds}× HOLD · {len(exits)} EXITS TRIGGERED"
