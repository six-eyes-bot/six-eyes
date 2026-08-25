"""Estimates analyst — DESK_DESIGN §1 W2.

Metrics: analyst count, consensus rating, consensus target, implied %.

AUDITED BEFORE AUTHORING, per T6. Neither the vendored engine nor
virattt/ai-hedge-fund has an estimates analyst: the engine's five analysts are
market, fundamentals, news, sentiment and social-media, and virattt has been
restructured into a quant library whose `signals/` are investor personas
(buffett, munger, graham, lynch, druckenmiller, pead), not per-analyst agents.
There was nothing to port.
"""

from __future__ import annotations

from datetime import date

from desk.data import MarketData
from desk.providers.base import ProviderError

from ._desk_base import AnalystReport, Metric, unavailable

NAME = "Estimates"


def analyse(data: MarketData, ticker: str, as_of: date) -> AnalystReport:
    try:
        got = data.estimates(ticker, as_of)
    except ProviderError as exc:
        return AnalystReport(NAME, ticker, as_of, (unavailable("estimates", str(exc)),))

    values, source, degraded = got.value, got.source, got.degraded
    metrics = [
        Metric("analyst count", values.get("numberOfAnalystOpinions"), source,
               degraded=degraded),
        Metric("consensus rating", values.get("recommendationMean"), source,
               unit=" (1=buy…5=sell)", degraded=degraded),
        Metric("consensus target", values.get("targetMeanPrice"), source,
               unit=" USD", degraded=degraded),
    ]

    target = values.get("targetMeanPrice")
    if target is None:
        # Caught by mypy, not by a test: a ticker with no consensus target
        # would have raised TypeError inside the arithmetic below. Small
        # caps routinely have no target at all.
        metrics.append(unavailable("implied %", "no consensus target published"))
        return AnalystReport(NAME, ticker, as_of, tuple(metrics))

    try:
        spot = data.quote_scalars(ticker, ["regularMarketPrice"], as_of).value
        price = spot["regularMarketPrice"]
    except (ProviderError, KeyError) as exc:
        metrics.append(unavailable("implied %", f"no spot price: {exc}"))
        return AnalystReport(NAME, ticker, as_of, tuple(metrics))

    metrics.append(
        Metric("implied %", (target - price) / price * 100, source, unit="%",
               degraded=degraded)
    )
    return AnalystReport(NAME, ticker, as_of, tuple(metrics))
