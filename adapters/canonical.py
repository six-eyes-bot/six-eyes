"""CSV header normalisation.

§4.5 draws the seam here deliberately: everything downstream is built and
tested against the canonical schema, and when the real Wells Fargo export
arrives (T15) you write a mapping dict and nothing else changes. "If adding
the adapter requires touching reconciliation logic, the seam was drawn in the
wrong place."

The rule that matters: **fail loudly on an unrecognised column; never silently
drop one.** A dropped column is how a cost basis quietly becomes NULL.
"""

from __future__ import annotations

import csv
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

CANONICAL_COLUMNS = ("ticker", "qty", "cost_basis", "market_value", "account")
REQUIRED_COLUMNS = ("ticker", "qty")


class UnknownColumn(ValueError):
    """An unmapped column. Refused rather than ignored."""


class MissingColumn(ValueError):
    """A required canonical column is absent."""


@dataclass(frozen=True)
class Row:
    ticker: str
    qty: float
    cost_basis: float | None = None
    market_value: float | None = None
    account: str = ""

    @property
    def key(self) -> tuple[str, str]:
        """§4.5: positions are matched on (ticker, account)."""
        return (self.ticker, self.account)


def _canonicalise(header: str) -> str:
    return header.strip().lower().replace(" ", "_").replace("-", "_")


def normalise_headers(
    headers: list[str], mapping: Mapping[str, str] | None = None
) -> dict[str, str]:
    """{source header: canonical name}. Raises on anything unrecognised."""
    lookup = {_canonicalise(k): v for k, v in (mapping or {}).items()}
    resolved: dict[str, str] = {}
    unknown: list[str] = []
    for header in headers:
        key = _canonicalise(header)
        if key in lookup:
            resolved[header] = lookup[key]
        elif key in CANONICAL_COLUMNS:
            resolved[header] = key
        else:
            unknown.append(header)
    if unknown:
        raise UnknownColumn(
            f"unrecognised column(s) {unknown}. Canonical columns are "
            f"{list(CANONICAL_COLUMNS)}. Add a mapping in the adapter — a "
            "column is never silently dropped, because that is how a cost "
            "basis quietly becomes NULL."
        )
    missing = [c for c in REQUIRED_COLUMNS if c not in resolved.values()]
    if missing:
        raise MissingColumn(f"required column(s) absent: {missing}")
    return resolved


def _number(raw: str | None) -> float | None:
    """Broker exports write '$1,234.56', '(123.00)' for negatives, and ''."""
    if raw is None:
        return None
    text = raw.strip().replace("$", "").replace(",", "")
    if not text or text in {"-", "--", "N/A", "n/a"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    try:
        value = float(text)
    except ValueError as exc:
        raise ValueError(f"not a number: {raw!r}") from exc
    return -value if negative else value


def load_csv(path: Path | str, mapping: Mapping[str, str] | None = None) -> list[Row]:
    with Path(path).open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise MissingColumn(f"{path}: no header row")
        resolved = normalise_headers(list(reader.fieldnames), mapping)
        rows: list[Row] = []
        for lineno, raw in enumerate(reader, start=2):
            record: dict[str, object] = {}
            for source, canonical in resolved.items():
                record[canonical] = raw.get(source)
            ticker = str(record.get("ticker") or "").strip().upper()
            if not ticker:
                raise MissingColumn(f"{path}:{lineno}: empty ticker")
            try:
                qty = _number(record.get("qty"))  # type: ignore[arg-type]
                cost_basis = _number(record.get("cost_basis"))  # type: ignore[arg-type]
                market_value = _number(record.get("market_value"))  # type: ignore[arg-type]
            except ValueError as exc:
                raise ValueError(f"{path}:{lineno}: {exc}") from exc
            if qty is None:
                raise MissingColumn(f"{path}:{lineno}: {ticker} has no qty")
            rows.append(
                Row(
                    ticker=ticker,
                    qty=qty,
                    cost_basis=cost_basis,
                    market_value=market_value,
                    account=str(record.get("account") or "").strip(),
                )
            )
    return rows
