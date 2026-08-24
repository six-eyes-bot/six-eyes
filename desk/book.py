"""`config/book.yaml` — the half of the truth a broker export does not contain.

§4.5: "A broker export contains what you hold. It does not contain why you
hold it or when you'd leave — no stops, no targets, no thesis. Those are yours
and they must survive re-import."

This module only READS. Nothing here is ever written by an import.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ExitRule:
    """`unit` is EXPLICIT and required for thresholded rules (T4).

    Inferring it from magnitude would read a $0.40 stop on a $0.50 stock as
    40%. `desk/exit_rules.Rule` defaults it per kind and rejects nonsense
    combinations, so a book that omits it gets the documented default rather
    than a guess.
    """

    kind: str
    threshold: float | None = None
    unit: str | None = None
    armed: bool = True
    note: str | None = None


@dataclass(frozen=True)
class BookEntry:
    ticker: str
    account: str = ""
    stop: float | None = None
    target: float | None = None
    horizon: str | None = None
    thesis_run_id: int | None = None
    #: Sourced by hand today. A provider-backed earnings date would need a new
    #: method on the MarketData Protocol (T2 ships none); recorded as a
    #: follow-up rather than widening a merged interface from T5.
    next_earnings: date | None = None
    thesis_invalidated: bool = False
    exit_rules: tuple[ExitRule, ...] = field(default_factory=tuple)

    @property
    def key(self) -> tuple[str, str]:
        return (self.ticker, self.account)


def _as_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def load_book(path: Path | str) -> dict[tuple[str, str], BookEntry]:
    """Empty is legitimate: a book with no overlay means every imported
    position is UNMANAGED, which is exactly what the health report should say."""
    p = Path(path)
    if not p.exists():
        return {}
    raw: Any = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    entries: dict[tuple[str, str], BookEntry] = {}
    for item in raw.get("positions") or []:
        ticker = str(item["ticker"]).strip().upper()
        rules = tuple(
            ExitRule(
                kind=str(r["kind"]),
                threshold=(None if r.get("threshold") is None else float(r["threshold"])),
                unit=(None if r.get("unit") is None else str(r["unit"])),
                armed=bool(r.get("armed", True)),
                note=r.get("note"),
            )
            for r in (item.get("exit_rules") or [])
        )
        entry = BookEntry(
            ticker=ticker,
            account=str(item.get("account") or "").strip(),
            stop=(None if item.get("stop") is None else float(item["stop"])),
            target=(None if item.get("target") is None else float(item["target"])),
            horizon=item.get("horizon"),
            thesis_run_id=item.get("thesis_run_id"),
            next_earnings=_as_date(item.get("next_earnings")),
            thesis_invalidated=bool(item.get("thesis_invalidated", False)),
            exit_rules=rules,
        )
        if entry.key in entries:
            raise ValueError(f"duplicate book entry for {entry.key}")
        entries[entry.key] = entry
    return entries
