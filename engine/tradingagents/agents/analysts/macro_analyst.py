"""Macro analyst — DESK_DESIGN §1 W2.

Metrics: VIX y/y, QQQ/SPY relative, UST 10Y, DXY.

The engine ships `agents/utils/macro_data_tools.py`, but no macro analyst
NODE — measured during T6's audit. The tools call upstream dataflows
(alpha_vantage, fred) rather than desk/data.py, and T6's ticket says the new
nodes consume desk/data.py, so this node does.

UST 10Y comes from FRED's DGS10, NOT from yfinance's ^TNX — ^TNX is the series
guard (a) was written for, and FRED needs no API key (measured 2026-08-20).
This node is ticker-free: it takes no position, so it is evaluated once per
run rather than once per holding.
"""

from __future__ import annotations

from datetime import date, timedelta

from desk.data import MarketData
from desk.providers.base import ProviderError

from ._desk_base import AnalystReport, Metric, unavailable

NAME = "Macro"

#: A y/y read needs a year plus enough slack for holidays and the guard's
#: minimum-row floor.
LOOKBACK = timedelta(days=400)


def _series_change(data: MarketData, series_id: str, as_of: date) -> tuple[float, str, bool]:
    got = data.macro_series(series_id, as_of - LOOKBACK, as_of)
    series = got.value
    latest = float(series.iloc[-1])
    year_ago = float(series.iloc[0])
    return (latest - year_ago) / year_ago * 100, got.source, got.degraded


def analyse(data: MarketData, as_of: date) -> AnalystReport:
    metrics: list[Metric] = []

    for label, series_id in (("VIX y/y", "^VIX"), ("DXY", "DX-Y.NYB")):
        try:
            change, source, degraded = _series_change(data, series_id, as_of)
            metrics.append(Metric(label, change, source, unit="%", degraded=degraded))
        except (ProviderError, IndexError, ZeroDivisionError) as exc:
            metrics.append(unavailable(label, str(exc)))

    try:
        got = data.macro_series("DGS10", as_of - LOOKBACK, as_of)
        metrics.append(
            Metric("UST 10Y", float(got.value.iloc[-1]), got.source, unit="%",
                   degraded=got.degraded)
        )
    except (ProviderError, IndexError) as exc:
        metrics.append(unavailable("UST 10Y", str(exc)))

    try:
        qqq, source, _ = _series_change(data, "QQQ", as_of)
        spy, _, _ = _series_change(data, "SPY", as_of)
        metrics.append(Metric("QQQ/SPY relative", qqq - spy, source, unit="pp"))
    except (ProviderError, IndexError, ZeroDivisionError) as exc:
        metrics.append(unavailable("QQQ/SPY relative", str(exc)))

    return AnalystReport(NAME, "—", as_of, tuple(metrics))
