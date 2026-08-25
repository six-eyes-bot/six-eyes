"""The four analyst nodes T6 adds.

These live INSIDE engine/ as first-party code and are linted and typed like
anything else — verified: injecting an unused import into macro_analyst.py
makes `ruff check .` fail, which is what T1 refused a directory glob for.

No network, no LLM. T6 produces numbers; T7 produces prose.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from desk.data import Sourced
from desk.providers.base import DataQualityError, ProviderUnavailable

sys.path.insert(0, str(Path(__file__).parent.parent / "engine"))
from tradingagents.agents.analysts import (  # noqa: E402
    estimates_analyst,
    flow_analyst,
    macro_analyst,
    options_analyst,
)

FIXTURES = Path(__file__).parent / "fixtures" / "recorded"
TODAY = date(2026, 8, 21)
INFO = json.loads((FIXTURES / "nvda_info.json").read_text())
#: Read from the fixture, never assumed. An earlier version of this file
#: hardcoded 191 and two tests failed against the real recorded value.
SPOT = float(INFO["regularMarketPrice"])
TARGET = 220.0


#: Strikes bracket the real recorded spot so "nearest" is a meaningful test.
ATM_IV = 0.38


def _chain(put_volume: float = 500.0) -> pd.DataFrame:
    return pd.DataFrame({
        "strike": [SPOT - 15, SPOT + 1, SPOT + 20, SPOT + 1],
        "impliedVolatility": [0.42, ATM_IV, 0.41, 0.44],
        "openInterest": [1000.0, 2500.0, 800.0, 1200.0],
        "volume": [300.0, 900.0, 100.0, put_volume],
        "kind": ["call", "call", "call", "put"],
    })


@dataclass
class FakeData:
    """A MarketData stand-in driven by the recorded NVDA fixture."""

    fail: frozenset[str] = frozenset()
    degraded: bool = False
    put_volume: float = 500.0
    series_first: float = 20.0
    series_last: float = 25.0

    def _guard(self, method: str) -> None:
        if method in self.fail:
            raise ProviderUnavailable(f"simulated {method} outage")

    def estimates(self, ticker: str, as_of: date) -> Sourced[dict[str, float]]:
        self._guard("estimates")
        return Sourced(
            {"numberOfAnalystOpinions": 58.0, "recommendationMean": 1.6,
             "targetMeanPrice": TARGET},
            "yfinance", as_of, self.degraded,
        )

    def quote_scalars(
        self, ticker: str, fields: list[str], as_of: date
    ) -> Sourced[dict[str, float]]:
        self._guard("quote_scalars")
        missing = [f for f in fields if INFO.get(f) is None and f != "regularMarketPrice"]
        if missing:
            raise DataQualityError(f"absent {missing}")
        out = {f: float(INFO[f]) for f in fields}
        return Sourced(out, "yfinance", as_of, self.degraded)

    def option_chain(self, ticker: str, expiry: date | None, as_of: date) -> Sourced[pd.DataFrame]:
        self._guard("option_chain")
        return Sourced(_chain(self.put_volume), "yfinance", as_of, self.degraded)

    def macro_series(self, series_id: str, start: date, end: date) -> Sourced[pd.Series]:
        self._guard(f"macro_series:{series_id}")
        self._guard("macro_series")
        return Sourced(
            pd.Series([self.series_first, self.series_last],
                      index=pd.to_datetime([start, end]), name=series_id),
            "fred" if series_id == "DGS10" else "yfinance", end, self.degraded,
        )


def _named(report: object) -> dict[str, object]:
    return {m.name: m for m in report.metrics}  # type: ignore[attr-defined]


# ====================================================================== Estimates
def test_estimates_reports_the_design_metrics() -> None:
    report = estimates_analyst.analyse(FakeData(), "NVDA", TODAY)   # type: ignore[arg-type]
    assert set(_named(report)) == {
        "analyst count", "consensus rating", "consensus target", "implied %",
    }


def test_estimates_implied_percent_is_computed_from_spot() -> None:
    """Derived from the fixture's real spot, not a hardcoded number."""
    report = estimates_analyst.analyse(FakeData(), "NVDA", TODAY)   # type: ignore[arg-type]
    implied = _named(report)["implied %"]
    assert implied.value == pytest.approx((TARGET - SPOT) / SPOT * 100, rel=1e-6)  # type: ignore[attr-defined]


def test_estimates_provider_failure_is_unavailable_not_a_crash() -> None:
    report = estimates_analyst.analyse(
        FakeData(fail=frozenset({"estimates"})), "NVDA", TODAY)   # type: ignore[arg-type]
    assert report.missing
    assert all(not m.available for m in report.metrics)


def test_degraded_flag_propagates_to_every_metric() -> None:
    """A fallback answered. The number is real but its provenance is not the
    primary, and the report must say so."""
    report = estimates_analyst.analyse(FakeData(degraded=True), "NVDA", TODAY)  # type: ignore[arg-type]
    assert all(m.degraded for m in report.available)
    assert "[degraded]" in report.render()


# ================================================================== Flow/Ownership
def test_flow_reports_short_metrics_from_real_recorded_data() -> None:
    report = flow_analyst.analyse(FakeData(), "NVDA", TODAY)   # type: ignore[arg-type]
    named = _named(report)
    assert named["short % float"].value == pytest.approx(1.26, rel=1e-3)   # type: ignore[attr-defined]
    assert named["days to cover"].value == pytest.approx(2.23, rel=1e-3)   # type: ignore[attr-defined]


def test_institutional_net_is_unavailable_not_substituted() -> None:
    """The metric DESK_DESIGN asks for is a NET FLOW. What we can source is a
    LEVEL. Reporting the level under the net's name is the exact silent
    failure this project keeps finding."""
    named = _named(flow_analyst.analyse(FakeData(), "NVDA", TODAY))   # type: ignore[arg-type]
    net = named["institutional net"]
    assert not net.available                                    # type: ignore[attr-defined]
    reason = net.unavailable_reason                             # type: ignore[attr-defined]
    assert reason is not None
    assert "13F" in reason and "Ultimate" in reason
    # and the level IS reported, under its own name
    assert named["institutional held"].available                # type: ignore[attr-defined]


# ======================================================================== Options
def test_options_picks_the_strike_nearest_spot_for_atm_iv() -> None:
    """Strikes bracket the real spot; the nearest is spot+1, carrying ATM_IV."""
    named = _named(options_analyst.analyse(FakeData(), "NVDA", TODAY))   # type: ignore[arg-type]
    assert named["ATM IV"].value == pytest.approx(ATM_IV * 100, rel=1e-6)   # type: ignore[attr-defined]


def test_options_open_interest_sums_both_sides() -> None:
    named = _named(options_analyst.analyse(FakeData(), "NVDA", TODAY))   # type: ignore[arg-type]
    assert named["cycle open interest"].value == pytest.approx(5500.0)   # type: ignore[attr-defined]


def test_zero_put_volume_is_unavailable_not_infinity() -> None:
    """A zero denominator is not a ratio of infinity; it is no data."""
    named = _named(options_analyst.analyse(FakeData(put_volume=0.0), "NVDA", TODAY))  # type: ignore[arg-type]
    ratio = named["call/put volume"]
    assert not ratio.available                                   # type: ignore[attr-defined]
    why = ratio.unavailable_reason                               # type: ignore[attr-defined]
    assert why is not None and "zero put volume" in why


def test_options_failure_says_there_is_no_fallback() -> None:
    """ADR 0001: nothing under $3,500/mo sells options IV. The report should
    say why it cannot degrade, not just that it failed."""
    report = options_analyst.analyse(
        FakeData(fail=frozenset({"option_chain"})), "NVDA", TODAY)   # type: ignore[arg-type]
    assert all(not m.available for m in report.metrics)
    first = report.metrics[0].unavailable_reason
    assert first is not None and "3,500" in first


# ========================================================================== Macro
def test_macro_reports_the_design_metrics() -> None:
    report = macro_analyst.analyse(FakeData(), TODAY)   # type: ignore[arg-type]
    assert set(_named(report)) == {"VIX y/y", "DXY", "UST 10Y", "QQQ/SPY relative"}


def test_ust_10y_comes_from_fred_not_tnx() -> None:
    """^TNX is the series guard (a) was written for. FRED's DGS10 needs no
    API key and was measured returning 64 years of history."""
    named = _named(macro_analyst.analyse(FakeData(), TODAY))   # type: ignore[arg-type]
    assert named["UST 10Y"].source == "fred"                   # type: ignore[attr-defined]

    source = Path("engine/tradingagents/agents/analysts/macro_analyst.py").read_text()
    body = source.split('"""', 2)[-1]
    assert "^TNX" not in body, "macro analyst must not call ^TNX"
    assert "DGS10" in body


def test_macro_survives_one_series_failing() -> None:
    """One dead series must not take the whole macro read down."""
    report = macro_analyst.analyse(
        FakeData(fail=frozenset({"macro_series:^VIX"})), TODAY)   # type: ignore[arg-type]
    named = _named(report)
    assert not named["VIX y/y"].available      # type: ignore[attr-defined]
    assert named["UST 10Y"].available          # type: ignore[attr-defined]


def test_macro_is_ticker_free() -> None:
    """Macro takes no position, so it is evaluated once per run rather than
    once per holding."""
    assert macro_analyst.analyse(FakeData(), TODAY).ticker == "—"   # type: ignore[arg-type]


def test_macro_lookback_exceeds_a_year() -> None:
    """A y/y read needs a year plus slack for holidays and guard (a)'s floor."""
    assert macro_analyst.LOOKBACK > timedelta(days=365)


# ======================================================================= contract
def test_unavailable_metrics_render_with_their_reason() -> None:
    report = flow_analyst.analyse(FakeData(), "NVDA", TODAY)   # type: ignore[arg-type]
    assert "UNAVAILABLE" in report.render()


def test_no_analyst_calls_an_llm() -> None:
    """DESK_DESIGN §1 W1's rule, applied to W2: the LLM writes the words, not
    the numbers. T6 must not introduce a model call."""
    directory = Path("engine/tradingagents/agents/analysts")
    for name in ("_desk_base", "estimates_analyst", "flow_analyst",
                 "options_analyst", "macro_analyst"):
        source = (directory / f"{name}.py").read_text()
        for banned in ("litellm", "completion(", "LLMGateway", "openai", "anthropic"):
            assert banned not in source, f"{name}.py references {banned!r}"


def test_missing_consensus_target_does_not_crash() -> None:
    """Found by mypy, not by a test. A ticker with no published target would
    have raised TypeError inside the implied-% arithmetic; small caps
    routinely have none."""

    class NoTarget(FakeData):
        def estimates(self, ticker: str, as_of: date) -> Sourced[dict[str, float]]:
            return Sourced({"numberOfAnalystOpinions": 2.0}, "yfinance", as_of, False)

    named = _named(estimates_analyst.analyse(NoTarget(), "TINY", TODAY))  # type: ignore[arg-type]
    implied = named["implied %"]
    assert not implied.available                                  # type: ignore[attr-defined]
    assert "no consensus target" in implied.unavailable_reason    # type: ignore[attr-defined]
