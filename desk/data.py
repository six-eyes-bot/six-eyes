"""The market-data seam.

Three vendored codebases repoint at this module — DanisHack (built on
Polygon.io), dafahentra (built on yfinance) and the TradingAgents engine (built
on its own dataflows). It is the single interface they all reduce to.

T1 ships the Protocol only. T2 implements it. The Protocol is here in T1 so
that mypy enforces the contract from T2's first commit rather than after it.

GUARD CONTRACT — every implementation MUST enforce these, and T2 MUST test them.
Each is a measured failure, not a hypothetical:

  (a) Historical series -> minimum-row-count assertion. A short series must
      RAISE, not return.
      Measured 2026-08-18: yfinance ^TNX returns 17 bars for period="2y" and
      16 for an explicit two-year start/end, but 1,254 for period="5y".
      No exception, no warning. A macro analyst would compute "UST 10Y y/y"
      from three weeks of data and report it with full confidence.

  (b) `.info` scalars (ATM IV, shortPercentOfFloat, shortRatio) -> per-FIELD
      schema assertion. The failure mode here is a MISSING KEY, not a short
      series, so a row-count floor cannot catch it.
      Measured: `revenueQuarterlyGrowth` is simply absent.
      TREAT NaN AS MISSING, not as a value: SOUN's latest quarterly revenue
      is NaN while every surrounding quarter is populated.

  (c) Ticker liveness -> `is_live()` before anything else.
      Measured: delisted tickers return ALL fields MISSING with no exception
      raised — only a note on stderr. TIVO and GIV, two of the five positions
      in DESK_DESIGN's own example book, are both delisted today. A health
      check on one would silently report nothing rather than refusing.

Every method returns `Sourced[T]`, carrying which provider answered and
whether a fallback was used. That is not decoration: T2's Done criterion is
"a forced failure surfaces a visible fallback, never silent", which is only
expressible if provenance rides along with the value.

Every method takes `as_of`. T2's TTL cache is keyed on (ticker, metric, date);
without the date in the signature that cache cannot be written.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Generic, Protocol, TypeVar

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps import cost off the hot path
    from pandas import DataFrame, Series

T = TypeVar("T")

#: Providers permitted to answer. Anything else is a bug, not a new provider.
Source = str  # "yfinance" | "fmp" | "fred" | "sec" | "finviz"


@dataclass(frozen=True)
class Sourced(Generic[T]):
    """A value plus the provenance needed to audit and debug it."""

    value: T
    source: Source
    as_of: date
    #: True when the primary provider failed and a fallback answered.
    #: T2 MUST log every degraded read — silent fallback is the thing this
    #: whole interface exists to prevent.
    degraded: bool = False


class MarketData(Protocol):
    """Provider-agnostic market data.

    Deliberately NOT encoded here: which provider serves which metric, and at
    what subscription tier. Those are T18/T19 decisions and both are still
    open; baking them into a provider-agnostic interface would be a category
    error. See internal-docs/SUPERSEDED.md for the current policy note.
    """

    def is_live(self, ticker: str, as_of: date) -> Sourced[bool]:
        """False for delisted or unknown tickers. Guard (c). Call this first."""
        ...

    def daily_bars(self, ticker: str, start: date, end: date) -> Sourced[DataFrame]:
        """OHLCV. MUST enforce a minimum-row-count floor — guard (a)."""
        ...

    def quote_scalars(
        self, ticker: str, fields: Sequence[str], as_of: date
    ) -> Sourced[Mapping[str, float]]:
        """Point-in-time scalars. MUST enforce per-field presence — guard (b).

        A requested field that is absent, or present as NaN, MUST raise.
        Returning a partial mapping is how a silent gap becomes a confident
        wrong number downstream.
        """
        ...

    def quarterly_income(self, ticker: str, as_of: date) -> Sourced[DataFrame]:
        """Quarterly income statements — the source for rev Q/Q."""
        ...

    def annual_fundamentals(self, ticker: str, as_of: date) -> Sourced[Mapping[str, float]]:
        """Annual fundamentals and ratios."""
        ...

    def estimates(self, ticker: str, as_of: date) -> Sourced[Mapping[str, float]]:
        """Analyst count, consensus rating, consensus target."""
        ...

    def option_chain(
        self, ticker: str, expiry: date | None, as_of: date
    ) -> Sourced[DataFrame]:
        """ATM IV, open interest, call/put volume. `expiry=None` = nearest cycle."""
        ...

    def macro_series(self, series_id: str, start: date, end: date) -> Sourced[Series]:
        """A macro series by provider id, e.g. FRED `DGS10`. Guard (a) applies."""
        ...

    def screen(self, filters: Mapping[str, str], as_of: date) -> Sourced[DataFrame]:
        """Screener. Day gainers, SMA-cross filters."""
        ...


class _Unimplemented:
    """Not a usable backend — it exists so mypy has a conformance check to fail.

    `Protocol` is structural, so nothing verifies the interface until some
    module asserts it. T1 ships no real consumer, so without this the Protocol
    would be unenforced prose and could drift freely until T2.
    """

    def __getattr__(self, name: str) -> object:  # pragma: no cover
        raise NotImplementedError(f"MarketData.{name} lands in T2, not T1")


if TYPE_CHECKING:  # pragma: no cover
    # mypy fails here the moment the Protocol and this stub disagree.
    _conformance: MarketData = _Unimplemented()  # type: ignore[assignment]
