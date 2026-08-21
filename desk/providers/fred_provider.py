"""FRED — macro series, and it needs NO API KEY.

Measured 2026-08-20:

    GET fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10
        -> HTTP 200, 268,427 bytes, 1962-01-02 through 2026-08-19
    GET api.stlouisfed.org/fred/series/observations (no key)
        -> HTTP 400 "Variable api_key is not set"

That measurement is why `macro_series` is fully functional in T2 with zero
credentials, and why UST 10Y is served by DGS10 rather than by yfinance's
`^TNX` — the series guard (a) was written for.

`fredgraph.csv` is a graph-EXPORT endpoint, not the documented API. It is
stable and widely used but carries no contract, so this provider prefers the
official API whenever FRED_API_KEY is set and falls back to the CSV export
otherwise. Recorded as working-but-undocumented rather than presented as
supported.
"""

from __future__ import annotations

import csv
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import date, datetime
from io import StringIO

import pandas as pd

from desk.providers.base import DataQualityError, ProviderUnavailable, require_min_rows

log = logging.getLogger(__name__)

CSV_ENDPOINT = "https://fred.stlouisfed.org/graph/fredgraph.csv"
API_ENDPOINT = "https://api.stlouisfed.org/fred/series/observations"

#: A macro series with fewer points than this cannot support a y/y read.
MIN_OBSERVATIONS = 30


def _urlopen_text(url: str, timeout: int = 30) -> str:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            if response.status != 200:
                raise ProviderUnavailable(f"fred: HTTP {response.status} for {url}")
            return response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProviderUnavailable(f"fred: {exc}") from exc


class FredProvider:
    name = "fred"
    CAPABILITIES = frozenset({"macro_series"})

    def __init__(
        self,
        fetch: Callable[[str], str] | None = None,
        api_key: str | None = None,
    ) -> None:
        self._fetch = fetch or _urlopen_text
        self._api_key = api_key if api_key is not None else os.environ.get("FRED_API_KEY")

    def macro_series(self, series_id: str, start: date, end: date) -> pd.Series:
        url = self._url(series_id, start, end)
        text = self._fetch(url)
        series = self._parse_csv(text, series_id)
        window = series.loc[
            (series.index >= pd.Timestamp(start)) & (series.index <= pd.Timestamp(end))
        ]
        require_min_rows(len(window), MIN_OBSERVATIONS, f"macro_series({series_id})", self.name)
        return window

    def _url(self, series_id: str, start: date, end: date) -> str:
        if self._api_key:
            query = urllib.parse.urlencode(
                {
                    "series_id": series_id,
                    "api_key": self._api_key,
                    "file_type": "json",
                    "observation_start": start.isoformat(),
                    "observation_end": end.isoformat(),
                }
            )
            return f"{API_ENDPOINT}?{query}"
        return f"{CSV_ENDPOINT}?{urllib.parse.urlencode({'id': series_id})}"

    @staticmethod
    def _parse_csv(text: str, series_id: str) -> pd.Series:
        """FRED writes '.' for a missing observation. That is NOT zero, and
        coercing it to one would put a fabricated 0.0 into a yield series."""
        rows = list(csv.reader(StringIO(text)))
        if len(rows) < 2:
            raise DataQualityError(f"fred: {series_id} returned no observations")
        header = rows[0]
        if len(header) < 2:
            raise DataQualityError(f"fred: unexpected header {header!r}")
        index, values = [], []
        for row in rows[1:]:
            if len(row) < 2 or row[1] in (".", ""):
                continue
            # Parse BOTH before appending EITHER. Appending the value first
            # and the date second desyncs the two lists whenever a date fails
            # to parse, silently shifting every later observation by one day.
            try:
                stamp = datetime.fromisoformat(row[0])
                value = float(row[1])
            except ValueError:
                continue
            index.append(stamp)
            values.append(value)
        if not values:
            raise DataQualityError(f"fred: {series_id} had no numeric observations")
        return pd.Series(values, index=pd.DatetimeIndex(index), name=series_id)
