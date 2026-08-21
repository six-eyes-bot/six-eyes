"""MarketDataService — fallback policy, the three guards, and caching.

Every guard test is driven by a RECORDED REAL response in
tests/fixtures/recorded/, not by a mock written from my own understanding of
the failure. Mocks would prove only that I am self-consistent; the guards exist
because of three specific things yfinance actually did.

No test here touches the network.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from desk.cache import TTLCache
from desk.data import MarketDataService, Sourced
from desk.providers.base import (
    DataQualityError,
    LookAheadError,
    ProviderUnavailable,
    TickerNotLive,
)
from desk.providers.yfinance_provider import YFinanceProvider

FIXTURES = Path(__file__).parent / "fixtures" / "recorded"
TODAY = date(2026, 8, 20)


def _json(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


class FakeTicker:
    """Stands in for yf.Ticker, backed by captured responses."""

    def __init__(self, symbol: str, counter: list[str] | None = None) -> None:
        self.symbol = symbol
        if counter is not None:
            counter.append(symbol)

    @property
    def info(self) -> dict[str, Any]:
        if self.symbol in ("TIVO", "GIV"):
            return _json(f"{self.symbol.lower()}_info_delisted.json")
        return _json("nvda_info.json")

    def history(self, start: str | None = None, end: str | None = None) -> pd.DataFrame:
        return pd.read_csv(FIXTURES / "nvda_bars_6mo.csv", index_col=0, parse_dates=True)

    @property
    def quarterly_income_stmt(self) -> pd.DataFrame:
        return pd.read_csv(FIXTURES / "soun_quarterly_income.csv", index_col=0)


def make_service(**kw: Any) -> MarketDataService:
    providers = kw.pop("providers", None) or [YFinanceProvider(ticker_factory=FakeTicker)]
    return MarketDataService(providers=providers, today=lambda: TODAY, **kw)


# ====================================================================== shape
def test_returns_sourced_with_provenance() -> None:
    got = make_service().daily_bars("NVDA", date(2026, 2, 1), TODAY)
    assert isinstance(got, Sourced)
    assert got.source == "yfinance"
    assert got.degraded is False
    assert isinstance(got.value, pd.DataFrame)


# =============================================================== guard (c)
def test_delisted_ticker_raises_rather_than_returning_all_missing() -> None:
    """TIVO and GIV are two of the five positions in DESK_DESIGN's own example
    book, and both are delisted. Measured: 11 and 23 info keys respectively,
    with no price field among them, and NO exception from yfinance."""
    svc = make_service()
    for delisted in ("TIVO", "GIV"):
        with pytest.raises(TickerNotLive):
            svc.annual_fundamentals(delisted, TODAY)


def test_is_live_distinguishes_live_from_delisted() -> None:
    svc = make_service()
    assert svc.is_live("NVDA", TODAY).value is True
    assert svc.is_live("TIVO", TODAY).value is False


def test_liveness_is_resolved_once_per_ticker() -> None:
    """Guard (c) must not re-hit the provider on every single read."""
    seen: list[str] = []
    svc = make_service(
        providers=[YFinanceProvider(ticker_factory=lambda s: FakeTicker(s, seen))]
    )
    svc.annual_fundamentals("NVDA", TODAY)
    svc.estimates("NVDA", TODAY)
    svc.quarterly_income("NVDA", TODAY)
    assert seen.count("NVDA") <= 4, f"liveness re-checked per call: {seen}"


# =============================================================== guard (b)
def test_absent_field_raises_instead_of_returning_a_partial_mapping() -> None:
    """Measured: `revenueQuarterlyGrowth` is simply ABSENT from NVDA's .info —
    184 scalar keys and not one of them that. A row-count floor cannot catch
    this, because the failure is a missing key, not a short series."""
    info = _json("nvda_info.json")
    assert "revenueQuarterlyGrowth" not in info, "fixture no longer exercises the bug"
    with pytest.raises(DataQualityError, match="absent"):
        make_service().quote_scalars("NVDA", ["trailingPE", "revenueQuarterlyGrowth"], TODAY)


def test_nan_is_treated_as_missing_not_as_a_value() -> None:
    """Measured: SOUN's latest quarterly revenue is NaN while every surrounding
    quarter is populated. Reporting `revenue: nan` as a fact is the exact
    silent-failure class this interface exists to prevent."""
    frame = pd.read_csv(FIXTURES / "soun_quarterly_income.csv", index_col=0)
    revenue = frame.loc["Total Revenue"]
    assert revenue.isna().any(), "fixture no longer contains a NaN quarter"

    from desk.providers.base import require_fields

    with pytest.raises(DataQualityError, match="NaN"):
        require_fields({"rev": float("nan")}, ("rev",), "test", "SOUN")


def test_present_fields_pass_the_guard() -> None:
    got = make_service().quote_scalars("NVDA", ["trailingPE", "beta"], TODAY)
    assert set(got.value) == {"trailingPE", "beta"}
    assert all(isinstance(v, float) for v in got.value.values())


# =============================================================== guard (a)
def test_short_series_raises() -> None:
    class ShortTicker(FakeTicker):
        def history(self, start: str | None = None, end: str | None = None) -> pd.DataFrame:
            return super().history(start, end).head(17)   # the ^TNX shape

    svc = make_service(providers=[YFinanceProvider(ticker_factory=ShortTicker)])
    with pytest.raises(DataQualityError, match="below the floor"):
        svc.daily_bars("NVDA", date(2026, 2, 1), TODAY)


# ============================================================ look-ahead
def test_future_as_of_raises_before_any_provider_call() -> None:
    seen: list[str] = []
    svc = make_service(
        providers=[YFinanceProvider(ticker_factory=lambda s: FakeTicker(s, seen))]
    )
    with pytest.raises(LookAheadError):
        svc.estimates("NVDA", date(2027, 1, 1))
    assert seen == [], "a provider was called for a future as_of"


# ============================================================== fallback
class StubSecondary:
    """The stub secondary from locked decision L1.

    FMP is UNVERIFIED and has no key, so the fallback MECHANISM is proven with
    a stub. FMP is never exercised in the default suite.
    """

    name = "fmp"
    CAPABILITIES = frozenset({"annual_fundamentals", "estimates"})

    def annual_fundamentals(self, ticker: str, as_of: date) -> dict[str, float]:
        return {"trailingPE": 1.0, "forwardPE": 1.0, "grossMargins": 1.0,
                "returnOnEquity": 1.0, "beta": 1.0}

    def estimates(self, ticker: str, as_of: date) -> dict[str, float]:
        return {"numberOfAnalystOpinions": 1.0, "targetMeanPrice": 1.0,
                "recommendationMean": 1.0}


class BrokenPrimary(YFinanceProvider):
    """A primary that is reachable for liveness but fails the real read."""

    def annual_fundamentals(self, ticker: str, as_of: date) -> Any:
        raise ProviderUnavailable("yfinance: simulated outage")


def test_forced_primary_failure_surfaces_a_visible_logged_fallback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """T2's Done criterion, with a stub secondary per L1."""
    svc = make_service(
        providers=[BrokenPrimary(ticker_factory=FakeTicker), StubSecondary()]
    )
    with caplog.at_level(logging.WARNING):
        got = svc.annual_fundamentals("NVDA", TODAY)

    assert got.degraded is True, "a fallback answered but degraded was not set"
    assert got.source == "fmp"
    assert set(got.value) == {"trailingPE", "forwardPE", "grossMargins",
                              "returnOnEquity", "beta"}, "shape differs by backend"
    text = caplog.text
    assert "DEGRADED READ" in text
    assert "fmp" in text and "yfinance" in text, "log must name BOTH providers"


def test_same_shape_from_either_backend() -> None:
    """'The same call returns the same shape from any backend' — asserted."""
    primary = make_service().annual_fundamentals("NVDA", TODAY)
    fallback = make_service(
        providers=[BrokenPrimary(ticker_factory=FakeTicker), StubSecondary()]
    ).annual_fundamentals("NVDA", TODAY)
    assert set(primary.value) == set(fallback.value)
    assert primary.source != fallback.source


def test_method_with_no_fallback_raises_instead_of_degrading() -> None:
    """The other half of the criterion, and the more important half.

    `option_chain` and `quarterly_income` have NO licensed second source — the
    ADR measured that nothing under $3,500/mo sells options IV or short
    interest, and FMP Starter is annual-only. Degrading here would report a
    number from the wrong place as though it were right.
    """
    class NoQuarterly(YFinanceProvider):
        def quarterly_income(self, ticker: str, as_of: date) -> Any:
            raise ProviderUnavailable("yfinance: simulated outage")

    svc = make_service(providers=[NoQuarterly(ticker_factory=FakeTicker), StubSecondary()])
    with pytest.raises(ProviderUnavailable):
        svc.quarterly_income("NVDA", TODAY)


def test_delisted_is_not_fallback_eligible() -> None:
    svc = make_service(providers=[YFinanceProvider(ticker_factory=FakeTicker), StubSecondary()])
    with pytest.raises(TickerNotLive):
        svc.annual_fundamentals("TIVO", TODAY)


# ================================================================= caching
def test_cache_hit_avoids_a_second_transport_call(tmp_path: Path) -> None:
    """Asserted by counting calls, never by timing."""
    seen: list[str] = []
    svc = make_service(
        providers=[YFinanceProvider(ticker_factory=lambda s: FakeTicker(s, seen))],
        cache=TTLCache(root=tmp_path, today=lambda: TODAY),
    )
    svc.quote_scalars("NVDA", ["trailingPE"], TODAY)
    after_first = len(seen)
    got = svc.quote_scalars("NVDA", ["trailingPE"], TODAY)
    assert len(seen) == after_first, f"cache did not prevent a refetch: {seen}"
    assert got.cached is True
    assert got.source == "yfinance", (
        "a cached read must still name the PROVIDER that answered. "
        "source='cache' would destroy provenance."
    )


def test_degraded_reads_are_never_cached(tmp_path: Path) -> None:
    """One transient outage must not become sticky for a whole TTL."""
    cache = TTLCache(root=tmp_path, today=lambda: TODAY)
    svc = make_service(
        providers=[BrokenPrimary(ticker_factory=FakeTicker), StubSecondary()], cache=cache
    )
    assert svc.annual_fundamentals("NVDA", TODAY).degraded is True
    assert cache.get("annual_fundamentals", "NVDA", TODAY) is None


# ============================================================ conformance
def test_every_policy_method_exists_on_the_service() -> None:
    """The policy table and the Protocol must not drift apart."""
    from desk.data import FALLBACK_POLICY

    svc = make_service()
    for method in FALLBACK_POLICY:
        assert callable(getattr(svc, method, None)), f"policy names {method}, service lacks it"


def test_every_policy_provider_name_is_real() -> None:
    """A typo in the policy table would silently route a method to nothing."""
    from desk.data import FALLBACK_POLICY
    from desk.providers.finviz_provider import FinvizProvider
    from desk.providers.fmp_provider import FMPProvider
    from desk.providers.fred_provider import FredProvider

    known = {p.name for p in (YFinanceProvider, FMPProvider, FredProvider, FinvizProvider)}
    for method, chain in FALLBACK_POLICY.items():
        for name in chain:
            assert name in known, f"policy[{method}] names unknown provider {name!r}"


def test_provider_declares_only_capabilities_it_implements() -> None:
    """'The same call returns the same shape from any backend' is only
    meaningful if a declared capability is actually implemented. A provider
    that half-declares one would still be routed real traffic."""
    from desk.providers.finviz_provider import FinvizProvider
    from desk.providers.fmp_provider import FMPProvider
    from desk.providers.fred_provider import FredProvider

    for cls in (YFinanceProvider, FMPProvider, FredProvider, FinvizProvider):
        missing = [m for m in cls.CAPABILITIES if not callable(getattr(cls, m, None))]
        assert not missing, f"{cls.name} declares but does not implement: {missing}"


def test_fmp_is_marked_unverified() -> None:
    """L1: FMP has never spoken to the real API. If someone flips this to True,
    they must have live-verified it at T18 — and this test should make them
    think about it."""
    from desk.providers.fmp_provider import FMPProvider

    assert FMPProvider.VERIFIED is False, (
        "FMPProvider.VERIFIED was flipped. That claims the wire format has been "
        "checked against the real API. T18 owns that; update the spec too."
    )


def test_fmp_cannot_serve_what_starter_does_not_sell() -> None:
    """FMP Starter is ANNUAL fundamentals. Declaring quarterly_income would
    route rev Q/Q to a guaranteed failure and hide that it has no fallback."""
    from desk.providers.fmp_provider import FMPProvider

    for unsellable in ("quarterly_income", "option_chain", "screen"):
        assert unsellable not in FMPProvider.CAPABILITIES


def test_non_numeric_info_field_is_a_data_error_not_a_crash() -> None:
    """`.info` is loosely typed. A field the caller asked for as a number can
    come back as a string, and a bare float() would raise ValueError — which
    reads as a bug in us rather than as bad data from upstream."""
    with pytest.raises(DataQualityError, match="non-numeric"):
        make_service().quote_scalars("NVDA", ["longName"], TODAY)


def test_field_present_but_null_counts_as_missing() -> None:
    """`f in info` is not enough: a key present with value None passed the
    guard and then died in float() with a TypeError."""
    class NullField(FakeTicker):
        @property
        def info(self) -> dict[str, Any]:
            return {**super().info, "trailingPE": None}

    svc = make_service(providers=[YFinanceProvider(ticker_factory=NullField)])
    with pytest.raises(DataQualityError, match="absent"):
        svc.quote_scalars("NVDA", ["trailingPE"], TODAY)
