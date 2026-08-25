"""Options analyst — DESK_DESIGN §1 W2.

Metrics: ATM implied volatility, cycle open interest, call/put volume ratio.

NO FALLBACK EXISTS. ADR 0001 measured that nothing under $3,500/month sells
options-chain IV, so `option_chain` is a single-provider chain in
FALLBACK_POLICY and a failure here is reported as unavailable, never degraded
to a substitute.
"""

from __future__ import annotations

from datetime import date

from desk.data import MarketData
from desk.providers.base import ProviderError

from ._desk_base import AnalystReport, Metric, unavailable

NAME = "Options"


def analyse(data: MarketData, ticker: str, as_of: date) -> AnalystReport:
    try:
        chain = data.option_chain(ticker, None, as_of)
    except ProviderError as exc:
        reason = f"{exc} (no source under $3,500/mo sells options IV)"
        return AnalystReport(NAME, ticker, as_of, (
            unavailable("ATM IV", reason),
            unavailable("cycle open interest", reason),
            unavailable("call/put volume", reason),
        ))

    frame, source, degraded = chain.value, chain.source, chain.degraded
    try:
        spot = data.quote_scalars(ticker, ["regularMarketPrice"], as_of).value
        price = spot["regularMarketPrice"]
    except (ProviderError, KeyError) as exc:
        return AnalystReport(NAME, ticker, as_of,
                             (unavailable("ATM IV", f"no spot price: {exc}"),))

    calls = frame[frame["kind"] == "call"]
    puts = frame[frame["kind"] == "put"]

    metrics: list[Metric] = []
    if calls.empty:
        metrics.append(unavailable("ATM IV", "no calls in the front cycle"))
    else:
        atm = calls.iloc[(calls["strike"] - price).abs().argsort().iloc[0]]
        metrics.append(
            Metric("ATM IV", float(atm["impliedVolatility"]) * 100, source,
                   unit="%", degraded=degraded)
        )

    metrics.append(
        Metric("cycle open interest", float(frame["openInterest"].sum()), source,
               degraded=degraded)
    )

    put_volume = float(puts["volume"].sum())
    if put_volume <= 0:
        # A zero denominator is not a ratio of infinity; it is no data.
        metrics.append(unavailable("call/put volume", "zero put volume in the cycle"))
    else:
        metrics.append(
            Metric("call/put volume", float(calls["volume"].sum()) / put_volume,
                   source, unit="x", degraded=degraded)
        )
    return AnalystReport(NAME, ticker, as_of, tuple(metrics))
