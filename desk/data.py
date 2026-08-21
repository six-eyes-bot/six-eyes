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
      Measured 2026-08-18: yfinance ^TNX returned 17 bars for period="2y" and
      16 for an explicit two-year start/end, but 1,254 for period="5y".
      No exception, no warning. A macro analyst would compute "UST 10Y y/y"
      from three weeks of data and report it with full confidence.
      RE-MEASURED 2026-08-20 under yfinance 1.6.0: ^TNX now returns 502 bars
      for period="2y". That specific reproduction is GONE. The guard stays --
      the failure class is real and was observed in this system's own
      dependency, and a row-count floor costs one comparison. Separately, T2
      no longer routes UST 10Y through ^TNX at all: FRED's DGS10 serves it,
      keylessly (measured 2026-08-20).

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

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any, Generic, Protocol, TypeVar

from desk.cache import TTLCache
from desk.providers.base import (
    DataQualityError,
    Provider,
    ProviderUnavailable,
    TickerNotLive,
    reject_lookahead,
)

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps import cost off the hot path
    from pandas import DataFrame, Series

log = logging.getLogger(__name__)

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
    #: True when this came from the TTL cache. Orthogonal to `source`, which
    #: always names the PROVIDER that originally answered — a cached read is
    #: still yfinance data, and reporting source="cache" would throw away the
    #: provenance this type exists to carry.
    cached: bool = False


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




# ==========================================================================
# The implementation (T2)
# ==========================================================================

#: Ordered provider chain per method. THIS TABLE IS THE TICKET.
#:
#: It is not decoration and it is not uniform, because the ADR measured that
#: the real fallback matrix is not uniform:
#:
#:   * FMP **Starter** ($19/mo) sells ANNUAL fundamentals. Quarterly statements
#:     are Premium ($49), so `rev Q/Q` has no licensed fallback at our tier.
#:   * NOTHING measured under $3,500/month sells options-chain IV or short
#:     interest, so `option_chain` has no fallback at any price we would pay.
#:   * The screener has one source.
#:
#: A chain of length one means: on failure, RAISE. Wrapping every method in a
#: generic try-primary-else-secondary would manufacture exactly the silent
#: failure this whole interface exists to prevent — it would report a number
#: from somewhere as though it came from the right place.
FALLBACK_POLICY: dict[str, tuple[str, ...]] = {
    "is_live": ("yfinance",),
    "daily_bars": ("yfinance",),
    "quote_scalars": ("yfinance",),
    "quarterly_income": ("yfinance",),          # rev Q/Q -- Premium-only elsewhere
    "annual_fundamentals": ("yfinance", "fmp"),
    "estimates": ("yfinance", "fmp"),
    "option_chain": ("yfinance",),              # no source under $3,500/mo
    "macro_series": ("fred", "yfinance"),
    "screen": ("finviz",),
}

#: Methods scoped to a single company, and therefore gated on guard (c).
#: `macro_series` and `screen` are not — a macro series has no ticker, and the
#: screener's whole job is to discover them.
_TICKER_SCOPED = frozenset(
    {
        "daily_bars",
        "quote_scalars",
        "quarterly_income",
        "annual_fundamentals",
        "estimates",
        "option_chain",
    }
)


class MarketDataService:
    """Composes providers into the `MarketData` Protocol.

    Owns the three decisions no single provider can make: which chain serves a
    method, whether a ticker is worth asking about at all, and what may be
    cached.
    """

    def __init__(
        self,
        providers: Sequence[Provider],
        cache: TTLCache | None = None,
        today: Callable[[], date] | None = None,
        policy: Mapping[str, tuple[str, ...]] | None = None,
    ) -> None:
        self._by_name = {p.name: p for p in providers}
        self._cache = cache
        self._today = today or date.today
        self._policy = dict(policy or FALLBACK_POLICY)
        self._liveness: dict[tuple[str, date], bool] = {}

    # ------------------------------------------------------------- plumbing
    def _chain(self, method: str) -> list[Provider]:
        names = self._policy.get(method, ())
        chain = [self._by_name[n] for n in names if n in self._by_name]
        if not chain:
            raise ProviderUnavailable(
                f"no provider configured for {method}; policy wants {list(names)}, "
                f"registered are {sorted(self._by_name)}"
            )
        return [p for p in chain if method in p.CAPABILITIES]

    def _attempt(
        self, method: str, cache_key: tuple[str, str] | None, as_of: date, *args: object
    ) -> Sourced[Any]:
        """Walk the chain. First success wins; a second-place win is degraded."""
        chain = self._chain(method)
        if not chain:
            raise ProviderUnavailable(f"no provider declares the capability {method!r}")

        if cache_key is not None and self._cache is not None:
            entry = self._cache.get_entry(cache_key[0], cache_key[1], as_of)
            if entry is not None:
                value, meta = entry
                return Sourced(
                    value=value,
                    source=str(meta.get("source", "unknown")),
                    as_of=as_of,
                    degraded=False,
                    cached=True,
                )

        first_error: Exception | None = None
        for index, provider in enumerate(chain):
            try:
                value = getattr(provider, method)(*args)
            except TickerNotLive:
                # Not fallback-eligible: asking a second provider the same
                # meaningless question about a delisted symbol wastes a call
                # and risks dressing up an empty answer as a real one.
                raise
            except (ProviderUnavailable, DataQualityError) as exc:
                if first_error is None:
                    first_error = exc
                log.warning(
                    "provider %s failed %s (%s: %s)%s",
                    provider.name, method, type(exc).__name__, exc,
                    "" if index + 1 < len(chain) else " — no fallback remains",
                )
                continue

            degraded = index > 0
            if degraded:
                log.warning(
                    "DEGRADED READ: %s served by fallback %r after %r failed. "
                    "Value is real but its provenance is not the primary.",
                    method, provider.name, chain[0].name,
                )
            # Only clean primary reads are cached. Caching a degraded answer
            # would make one transient upstream failure sticky for a whole TTL.
            if cache_key is not None and self._cache is not None and not degraded:
                self._cache.set(
                    cache_key[0], cache_key[1], as_of, value,
                    meta={"source": provider.name},
                )
            return Sourced(value=value, source=provider.name, as_of=as_of, degraded=degraded)

        # Every provider failed. Raise the FIRST error: it describes the
        # primary, which is the one whose failure actually matters.
        assert first_error is not None
        raise first_error

    def _guard_live(self, ticker: str, as_of: date) -> None:
        """Guard (c). Resolved once per (ticker, as_of); `is_live` itself does
        not re-enter this, which would be infinite."""
        key = (ticker, as_of)
        if key not in self._liveness:
            self._liveness[key] = self.is_live(ticker, as_of).value
        if not self._liveness[key]:
            raise TickerNotLive(
                f"{ticker} is not quoting as of {as_of}. Measured: delisted "
                "tickers return every field missing with no exception raised. "
                "TIVO and GIV, two of the five positions in DESK_DESIGN's own "
                "example book, are delisted today."
            )

    def _preflight(self, as_of: date, ticker: str | None = None) -> None:
        reject_lookahead(as_of, self._today())
        if ticker is not None:
            self._guard_live(ticker, as_of)

    # -------------------------------------------------------------- methods
    def is_live(self, ticker: str, as_of: date) -> Sourced[bool]:
        reject_lookahead(as_of, self._today())
        return self._attempt("is_live", ("is_live", ticker), as_of, ticker, as_of)

    def daily_bars(self, ticker: str, start: date, end: date) -> Sourced[DataFrame]:
        self._preflight(end, ticker)
        key = (f"daily_bars:{start.isoformat()}:{end.isoformat()}", ticker)
        return self._attempt("daily_bars", key, end, ticker, start, end)

    def quote_scalars(
        self, ticker: str, fields: Sequence[str], as_of: date
    ) -> Sourced[Mapping[str, float]]:
        self._preflight(as_of, ticker)
        key = (f"quote_scalars:{','.join(sorted(fields))}", ticker)
        return self._attempt("quote_scalars", key, as_of, ticker, fields, as_of)

    def quarterly_income(self, ticker: str, as_of: date) -> Sourced[DataFrame]:
        self._preflight(as_of, ticker)
        return self._attempt("quarterly_income", ("quarterly_income", ticker), as_of, ticker, as_of)

    def annual_fundamentals(self, ticker: str, as_of: date) -> Sourced[Mapping[str, float]]:
        self._preflight(as_of, ticker)
        return self._attempt(
            "annual_fundamentals", ("annual_fundamentals", ticker), as_of, ticker, as_of
        )

    def estimates(self, ticker: str, as_of: date) -> Sourced[Mapping[str, float]]:
        self._preflight(as_of, ticker)
        return self._attempt("estimates", ("estimates", ticker), as_of, ticker, as_of)

    def option_chain(
        self, ticker: str, expiry: date | None, as_of: date
    ) -> Sourced[DataFrame]:
        self._preflight(as_of, ticker)
        key = (f"option_chain:{expiry.isoformat() if expiry else 'front'}", ticker)
        return self._attempt("option_chain", key, as_of, ticker, expiry, as_of)

    def macro_series(self, series_id: str, start: date, end: date) -> Sourced[Series]:
        self._preflight(end)
        key = (f"macro_series:{start.isoformat()}:{end.isoformat()}", series_id)
        return self._attempt("macro_series", key, end, series_id, start, end)

    def screen(self, filters: Mapping[str, str], as_of: date) -> Sourced[DataFrame]:
        self._preflight(as_of)
        key = ("screen", ",".join(f"{k}={v}" for k, v in sorted(filters.items())))
        return self._attempt("screen", key, as_of, filters, as_of)


if TYPE_CHECKING:  # pragma: no cover
    # mypy fails here the moment the implementation and the Protocol disagree.
    _conformance: MarketData = MarketDataService(providers=[])
