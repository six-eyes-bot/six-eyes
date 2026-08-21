"""Shared provider contracts.

The error taxonomy is the load-bearing part. Whether a failure is eligible for
fallback is a property of the FAILURE, not of the provider, so it has to be
expressible in the type that gets raised.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable


class ProviderError(Exception):
    """Base for anything a provider raises."""


class ProviderUnavailable(ProviderError):
    """The upstream did not answer usefully — network, timeout, rate limit, 5xx.

    Fallback-eligible: a different provider may well succeed.
    """


class DataQualityError(ProviderError):
    """The upstream answered, and the answer failed a guard.

    Also fallback-eligible, and deliberately so: a bad response from provider A
    is precisely when provider B is worth trying. But the fallback's answer must
    clear the same guard, and if it does not, the ORIGINAL error is raised —
    never the fallback's, which would misattribute the failure.
    """


class TickerNotLive(ProviderError):
    """Delisted, or unknown to the provider.

    NOT fallback-eligible. Measured: a delisted ticker returns every field
    missing with no exception raised — only a note on stderr. TIVO and GIV, two
    of the five positions in DESK_DESIGN's own example book, are delisted today.
    Falling back would ask a second provider the same meaningless question.
    """


class LookAheadError(ProviderError):
    """An `as_of` in the future. A backtest bug, not a data problem."""


@runtime_checkable
class Provider(Protocol):
    """What MarketDataService needs from any upstream.

    `CAPABILITIES` is explicit rather than inferred from `hasattr`: a provider
    that half-implements a method by accident should not silently be routed
    traffic. Adding a name here is a review-worthy change.
    """

    name: str
    CAPABILITIES: frozenset[str]


def require_min_rows(frame_len: int, minimum: int, what: str, source: str) -> None:
    """Guard (a) — a short historical series must RAISE, not return.

    Measured 2026-08-18: yfinance `^TNX` returned 17 bars for `period="2y"` and
    1,254 for `"5y"`, with no exception and no warning. A macro analyst would
    have computed "UST 10Y y/y" from three weeks of data and reported it with
    full confidence.

    RE-MEASURED 2026-08-20 under yfinance 1.6.0: `^TNX` now returns 502 bars for
    `period="2y"`. The specific reproduction is gone. The guard stays — the
    failure class is real, it was observed in this system's own dependency, and
    a row-count floor costs one comparison. This project also no longer routes
    UST 10Y through `^TNX` at all; FRED's `DGS10` serves it keylessly.
    """
    if frame_len < minimum:
        raise DataQualityError(
            f"{source}: {what} returned {frame_len} rows, below the floor of "
            f"{minimum}. Refusing to compute on a truncated series."
        )


def require_fields(
    values: dict[str, float], requested: tuple[str, ...], source: str, ticker: str
) -> None:
    """Guard (b) — per-FIELD presence. NaN counts as MISSING.

    A row-count floor cannot catch this: the failure mode for `.info` scalars is
    a missing key, not a short series.

    Measured: `revenueQuarterlyGrowth` is simply absent from NVDA's `.info`
    (184 scalar keys, not one of them that). And SOUN's latest quarterly revenue
    is NaN while every surrounding quarter is populated — so treating NaN as a
    value would report "revenue: nan" as fact.
    """
    missing = [f for f in requested if f not in values]
    nan = [f for f in requested if f in values and _is_nan(values[f])]
    if missing or nan:
        parts = []
        if missing:
            parts.append(f"absent {missing}")
        if nan:
            parts.append(f"NaN (treated as missing) {nan}")
        raise DataQualityError(f"{source}: {ticker} — " + "; ".join(parts))


def _is_nan(value: object) -> bool:
    return isinstance(value, float) and value != value


def reject_lookahead(as_of: date, today: date) -> None:
    """No method may read the future. Enforced before any provider call."""
    if as_of > today:
        raise LookAheadError(f"as_of={as_of} is after today={today} — look-ahead read")
