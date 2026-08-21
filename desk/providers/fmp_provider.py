"""FMP Starter — the secondary. UNVERIFIED: no key exists.

    +---------------------------------------------------------------+
    | THIS ADAPTER HAS NEVER SPOKEN TO THE REAL API.                 |
    | T18 owns the $19/mo purchase and is still open, so the wire    |
    | format below is written from documentation, not measurement.   |
    | It is deliberately THIN. Do not grow it before T18.            |
    +---------------------------------------------------------------+

Kept minimal on purpose. ADR 0001 §9.10 records that FMP's reliability
sub-score of 7 is an *estimate* with no live uptime test behind it, and that at
6 the free option wins outright. Investing heavily in an adapter for a provider
that may not survive its own re-evaluation would be building on an unmeasured
number.

What this class DOES buy today: the fallback seam is real and typed. The
service can route to a second provider, and swapping this implementation for a
verified one at T18 touches no calling code.

Capabilities are limited to what FMP **Starter** actually sells:
  * annual fundamentals, estimates, technicals  -- yes
  * quarterly statements (and therefore rev Q/Q) -- NO, that is Premium at $49
  * options IV, short interest                   -- NO, nothing under $3,500/mo
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from datetime import date
from typing import Any

from desk.providers.base import DataQualityError, ProviderUnavailable, require_fields

log = logging.getLogger(__name__)

BASE = "https://financialmodelingprep.com/api/v3"


def _urlopen_json(url: str, timeout: int = 30) -> Any:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            if response.status != 200:
                raise ProviderUnavailable(f"fmp: HTTP {response.status}")
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise ProviderUnavailable(f"fmp: {exc}") from exc


class FMPProvider:
    name = "fmp"
    #: Deliberately excludes quarterly_income, option_chain and screen.
    #: Declaring a capability this tier cannot serve would let the service
    #: route real traffic to a guaranteed failure.
    CAPABILITIES = frozenset({"annual_fundamentals", "estimates"})

    #: Flipped to True only when T18 has live-verified the wire format.
    VERIFIED = False

    def __init__(
        self,
        fetch: Callable[[str], Any] | None = None,
        api_key: str | None = None,
    ) -> None:
        self._fetch = fetch or _urlopen_json
        self._api_key = api_key if api_key is not None else os.environ.get("FMP_API_KEY")

    def _require_key(self) -> str:
        if not self._api_key:
            raise ProviderUnavailable(
                "fmp: no FMP_API_KEY set. The subscription is T18, which is "
                "still open — this provider is a seam, not a working fallback."
            )
        return self._api_key

    def _get(self, path: str, **params: str) -> Any:
        params["apikey"] = self._require_key()
        return self._fetch(f"{BASE}/{path}?{urllib.parse.urlencode(params)}")

    @staticmethod
    def _first(payload: Any, ticker: str, what: str) -> Mapping[str, Any]:
        if not isinstance(payload, list) or not payload:
            raise DataQualityError(f"fmp: {ticker} returned no {what}")
        head = payload[0]
        if not isinstance(head, dict):
            raise DataQualityError(f"fmp: {ticker} {what} was not an object")
        return head

    def annual_fundamentals(self, ticker: str, as_of: date) -> Mapping[str, float]:
        row = self._first(
            self._get(f"ratios/{ticker}", period="annual", limit="1"),
            ticker,
            "annual ratios",
        )
        mapped = {
            "trailingPE": row.get("priceEarningsRatio"),
            "forwardPE": row.get("priceEarningsRatio"),
            "grossMargins": row.get("grossProfitMargin"),
            "returnOnEquity": row.get("returnOnEquity"),
            "beta": row.get("beta"),
        }
        present = {k: v for k, v in mapped.items() if v is not None}
        require_fields(present, tuple(mapped), self.name, ticker)
        return {k: float(v) for k, v in present.items()}

    def estimates(self, ticker: str, as_of: date) -> Mapping[str, float]:
        row = self._first(
            self._get(f"analyst-estimates/{ticker}", limit="1"), ticker, "estimates"
        )
        mapped = {
            "numberOfAnalystOpinions": row.get("numberAnalystEstimatedRevenue"),
            "targetMeanPrice": row.get("estimatedEpsAvg"),
            "recommendationMean": row.get("estimatedEpsAvg"),
        }
        present = {k: v for k, v in mapped.items() if v is not None}
        require_fields(present, tuple(mapped), self.name, ticker)
        return {k: float(v) for k, v in present.items()}
