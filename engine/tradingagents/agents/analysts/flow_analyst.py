"""Flow / Ownership analyst — DESK_DESIGN §1 W2.

Metrics: short % float, institutional net, days to cover.

INSTITUTIONAL *NET* IS NOT AVAILABLE AT OUR TIER, and is reported as
unavailable rather than substituted. ADR 0001 measured that 13F holdings are
FMP **Ultimate** ($99/mo); we are at $19 Starter, and T18 is still open. What
is available is `heldPercentInstitutions` — a LEVEL, not a net flow — so it is
reported under its own name. Presenting a level where a delta was asked for is
precisely the silent-failure class this project keeps finding.

Short interest has NO fallback at any price the ADR found under $3,500/month,
so a yfinance failure here fails the metric rather than degrading it.
"""

from __future__ import annotations

from datetime import date

from desk.data import MarketData
from desk.providers.base import ProviderError

from ._desk_base import AnalystReport, Metric, unavailable

NAME = "Flow/Ownership"

_FIELDS = ("shortPercentOfFloat", "shortRatio", "heldPercentInstitutions")


def analyse(data: MarketData, ticker: str, as_of: date) -> AnalystReport:
    try:
        got = data.quote_scalars(ticker, list(_FIELDS), as_of)
    except ProviderError as exc:
        return AnalystReport(
            NAME, ticker, as_of,
            (unavailable("short % float", str(exc)),
             unavailable("days to cover", str(exc)),
             unavailable("institutional net", str(exc))),
        )

    values, source, degraded = got.value, got.source, got.degraded
    return AnalystReport(NAME, ticker, as_of, (
        Metric("short % float", values["shortPercentOfFloat"] * 100, source,
               unit="%", degraded=degraded),
        Metric("days to cover", values["shortRatio"], source, unit="d",
               degraded=degraded),
        Metric("institutional held", values["heldPercentInstitutions"] * 100, source,
               unit="%", degraded=degraded),
        unavailable(
            "institutional net",
            "13F net flow is FMP Ultimate ($99/mo); this desk is at Starter "
            "($19) and T18 is open. A held-percent LEVEL is reported above "
            "instead — it is not the same number",
        ),
    ))
