"""W1 — Book Health Check.

DESK_DESIGN §1 W1: "This is deterministic rule evaluation, not an LLM
committee. The LLM only writes the summary prose. Keep it that way — it's the
cheapest and most reliable part of the system." Nothing in this module calls a
model.

Two responsibilities the ticket is emphatic about:

  1. **A stale book produces a REFUSAL, not a report.** §4.5: "have W1 refuse
     to run — loudly, not silently — if the book is more than N days stale
     (default 3). A health report computed against a week-old book is worse
     than no health report, because it reads as current."

  2. **UNMANAGED positions are flagged, not evaluated.** §4.5 wants them
     "flagged in the next health report as needing stops before it can be
     evaluated". Counting them as HOLD would report an all-clear for a
     position that has no stop at all.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date

from desk.book import BookEntry, ExitRule
from desk.exit_rules import (
    Decision,
    PositionState,
    Rule,
    RuleKind,
    Unit,
    evaluate,
    summarise,
)
from desk.ingest import days_stale

log = logging.getLogger(__name__)

#: §4.5's default.
DEFAULT_MAX_STALE_DAYS = 3


class BookStale(RuntimeError):
    """The refusal. Deliberately an exception rather than a report field —
    a caller that forgets to check a field still gets stopped."""


class BookNeverImported(BookStale):
    """No import has ever run. Distinct from 'stale' so the operator is told
    to import rather than to re-import."""


def assert_fresh(
    conn: sqlite3.Connection,
    max_days: int = DEFAULT_MAX_STALE_DAYS,
    today: date | None = None,
) -> int:
    """Return the book's age in days, or refuse."""
    age = days_stale(conn, today)
    if age is None:
        raise BookNeverImported(
            "the book has never been imported. Run `python -m desk.ingest "
            "<csv> --commit` before a health check — there is nothing to "
            "check against."
        )
    if age > max_days:
        raise BookStale(
            f"book is {age} days stale (limit {max_days}). REFUSING to render "
            "a health report. A report computed against a stale book is worse "
            "than none, because it reads as current. Re-import first."
        )
    return age


def rules_for(entry: BookEntry) -> list[Rule]:
    """Translate a book entry into engine rules.

    `stop` and `target` are absolute PRICES — that is how a human writes a
    book ("my stop is $150"), and T4's engine takes units explicitly rather
    than guessing.

    `horizon` is deliberately NOT parsed into a time stop. It is free text
    ("2w+") and inventing a day count from it would fabricate an exit rule
    the operator never wrote. A time stop must be stated as one.
    """
    rules: list[Rule] = []
    if entry.stop is not None:
        rules.append(Rule(RuleKind.FIXED_STOP, entry.stop, Unit.PRICE))
    if entry.target is not None:
        rules.append(Rule(RuleKind.TAKE_PROFIT, entry.target, Unit.PRICE))
    for raw in entry.exit_rules:
        rules.append(_rule_from_book(raw))
    return rules


def _rule_from_book(raw: ExitRule) -> Rule:
    return Rule(
        kind=RuleKind(raw.kind),
        threshold=raw.threshold,
        unit=None if raw.unit is None else Unit(raw.unit),
        armed=raw.armed,
        note=raw.note,
    )


@dataclass(frozen=True)
class Unevaluated:
    """A position that exists but cannot be judged."""

    ticker: str
    account: str
    reason: str


@dataclass
class HealthReport:
    as_of: date
    book_age_days: int
    decisions: list[Decision] = field(default_factory=list)
    unmanaged: list[Unevaluated] = field(default_factory=list)

    @property
    def exits(self) -> list[Decision]:
        return [d for d in self.decisions if d.exited]

    def render(self) -> str:
        lines = [
            f"BOOK HEALTH — {self.as_of.isoformat()}",
            f"  book imported {self.book_age_days}d ago",
            "",
        ]
        for decision in self.decisions:
            mark = "EXIT" if decision.exited else "HOLD"
            detail = ""
            if decision.triggered is not None:
                detail = f"  {decision.triggered.reason}: {decision.triggered.detail}"
            lines.append(f"  {decision.ticker:<6} {mark}{detail}")
            for alert in decision.alerts:
                lines.append(f"  {'':<6}   ! {alert.detail}")
            for also in decision.also_fired:
                lines.append(f"  {'':<6}   (also {also.reason}: {also.detail})")
        for item in self.unmanaged:
            lines.append(f"  {item.ticker:<6} ---- {item.reason}")
        lines += ["", f"  {summarise(self.decisions)}"]
        if self.unmanaged:
            lines.append(
                f"  {len(self.unmanaged)} position(s) NOT evaluated — see above"
            )
        return "\n".join(lines)


def check(
    conn: sqlite3.Connection,
    book: Mapping[tuple[str, str], BookEntry],
    prices: Mapping[str, float],
    as_of: date,
    high_water: Mapping[str, float] | None = None,
    max_stale_days: int = DEFAULT_MAX_STALE_DAYS,
) -> HealthReport:
    """Evaluate every OPEN position. Refuses outright on a stale book."""
    age = assert_fresh(conn, max_stale_days, as_of)
    report = HealthReport(as_of=as_of, book_age_days=age)

    rows = conn.execute(
        "SELECT * FROM positions WHERE status != 'CLOSED' ORDER BY ticker"
    ).fetchall()

    for row in rows:
        key = (row["ticker"], row["account"])
        entry = book.get(key)
        price = prices.get(row["ticker"])

        if entry is None:
            report.unmanaged.append(
                Unevaluated(row["ticker"], row["account"],
                            "UNMANAGED — no stops in book.yaml; not evaluated")
            )
            continue
        if price is None:
            # Not a HOLD. A position we could not price is a position we did
            # not check, and saying HOLD would be a false all-clear.
            report.unmanaged.append(
                Unevaluated(row["ticker"], row["account"],
                            "NO PRICE — not evaluated")
            )
            continue
        if not row["qty"] or row["cost_basis"] is None:
            report.unmanaged.append(
                Unevaluated(row["ticker"], row["account"],
                            "NO COST BASIS — not evaluated")
            )
            continue

        state = PositionState(
            ticker=row["ticker"],
            account=row["account"],
            qty=row["qty"],
            avg_cost=row["cost_basis"] / row["qty"],
            current_price=price,
            as_of=as_of,
            opened_at=date.fromisoformat(row["opened_at"]) if row["opened_at"] else None,
            high_water_mark=(high_water or {}).get(row["ticker"]),
            thesis_invalidated=entry.thesis_invalidated,
            next_earnings=entry.next_earnings,
        )
        report.decisions.append(evaluate(state, rules_for(entry)))

    return report
