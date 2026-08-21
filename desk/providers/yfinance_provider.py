"""yfinance — the primary for everything except macro and the screener.

ADR 0001: yfinance is primary because no measured paid configuration removes it
below $3,500/month. It is the ONLY source in the recommended set for options
chain IV and short interest, which is why those two methods have no fallback.

The `ticker_factory` seam exists so the default test suite makes no network
calls: tests inject a factory backed by the recorded fixtures in
tests/fixtures/recorded/, which are real captured responses rather than mocks
written from my own understanding of the failure.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from typing import Any

import pandas as pd

from desk.providers.base import (
    DataQualityError,
    ProviderUnavailable,
    require_fields,
    require_min_rows,
)


def _as_floats(
    values: dict[str, Any], fields: tuple[str, ...], source: str, ticker: str
) -> dict[str, float]:
    """Coerce, and turn a bad coercion into a DataQualityError.

    `.info` is loosely typed: a field the caller asked for as a number can come
    back as a string. A bare float() would raise ValueError, which reads to the
    caller as a bug in us rather than bad data from upstream.
    """
    out: dict[str, float] = {}
    bad: list[str] = []
    for field in fields:
        try:
            out[field] = float(values[field])
        except (TypeError, ValueError):
            bad.append(f"{field}={values[field]!r}")
    if bad:
        raise DataQualityError(f"{source}: {ticker} — non-numeric {bad}")
    return out

log = logging.getLogger(__name__)

#: Any one of these present and non-null means the symbol is quoting.
#: Measured 2026-08-20: NVDA has 184 scalar .info keys and all three; delisted
#: TIVO has 11 keys and none; delisted GIV has 23 keys and none.
_LIVENESS_FIELDS = ("regularMarketPrice", "currentPrice", "previousClose")

#: Below this, a daily series is not worth computing a trend from.
MIN_BARS = 30


class YFinanceProvider:
    name = "yfinance"
    CAPABILITIES = frozenset(
        {
            "is_live",
            "daily_bars",
            "quote_scalars",
            "quarterly_income",
            "annual_fundamentals",
            "estimates",
            "option_chain",
            "macro_series",
        }
    )

    def __init__(self, ticker_factory: Callable[[str], Any] | None = None) -> None:
        self._factory = ticker_factory or self._default_factory

    @staticmethod
    def _default_factory(symbol: str) -> Any:
        import yfinance as yf

        return yf.Ticker(symbol)

    def _ticker(self, symbol: str) -> Any:
        try:
            return self._factory(symbol)
        except Exception as exc:  # noqa: BLE001 - upstream raises bare Exception
            raise ProviderUnavailable(f"yfinance: constructing {symbol}: {exc}") from exc

    @staticmethod
    def _info(tk: Any, symbol: str) -> dict[str, Any]:
        try:
            info = tk.info
        except Exception as exc:  # noqa: BLE001
            raise ProviderUnavailable(f"yfinance: .info for {symbol}: {exc}") from exc
        if not isinstance(info, dict):
            raise ProviderUnavailable(f"yfinance: .info for {symbol} was not a mapping")
        return info

    # ------------------------------------------------------------ liveness
    def is_live(self, ticker: str, as_of: date) -> bool:
        info = self._info(self._ticker(ticker), ticker)
        return any(info.get(f) is not None for f in _LIVENESS_FIELDS)

    # --------------------------------------------------------------- bars
    def daily_bars(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        tk = self._ticker(ticker)
        try:
            frame = tk.history(start=start.isoformat(), end=end.isoformat())
        except Exception as exc:  # noqa: BLE001
            raise ProviderUnavailable(f"yfinance: history for {ticker}: {exc}") from exc
        if frame is None or not isinstance(frame, pd.DataFrame):
            raise ProviderUnavailable(f"yfinance: history for {ticker} was not a frame")
        require_min_rows(len(frame), MIN_BARS, f"daily_bars({ticker})", self.name)
        return frame

    # ------------------------------------------------------------- scalars
    def quote_scalars(
        self, ticker: str, fields: Sequence[str], as_of: date
    ) -> Mapping[str, float]:
        info = self._info(self._ticker(ticker), ticker)
        # `f in info` is NOT enough: a key present with value None passes the
        # guard and then dies in float() with a TypeError, which is a crash
        # rather than the clean DataQualityError the caller can act on.
        present = {f: info[f] for f in fields if info.get(f) is not None}
        require_fields(present, tuple(fields), self.name, ticker)
        return _as_floats(present, tuple(fields), self.name, ticker)

    # -------------------------------------------------------- fundamentals
    def quarterly_income(self, ticker: str, as_of: date) -> pd.DataFrame:
        """The `rev Q/Q` source, and single-sourced here: FMP Starter is ANNUAL
        fundamentals, so at $19/mo there is no licensed fallback for this."""
        tk = self._ticker(ticker)
        try:
            frame = tk.quarterly_income_stmt
        except Exception as exc:  # noqa: BLE001
            raise ProviderUnavailable(
                f"yfinance: quarterly_income_stmt for {ticker}: {exc}"
            ) from exc
        if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
            raise DataQualityError(f"yfinance: {ticker} returned no quarterly income")
        return frame

    def annual_fundamentals(self, ticker: str, as_of: date) -> Mapping[str, float]:
        info = self._info(self._ticker(ticker), ticker)
        wanted = ("trailingPE", "forwardPE", "grossMargins", "returnOnEquity", "beta")
        present = {k: info[k] for k in wanted if info.get(k) is not None}
        require_fields(present, wanted, self.name, ticker)
        return _as_floats(present, wanted, self.name, ticker)

    def estimates(self, ticker: str, as_of: date) -> Mapping[str, float]:
        info = self._info(self._ticker(ticker), ticker)
        wanted = ("numberOfAnalystOpinions", "targetMeanPrice", "recommendationMean")
        present = {k: info[k] for k in wanted if info.get(k) is not None}
        require_fields(present, wanted, self.name, ticker)
        return _as_floats(present, wanted, self.name, ticker)

    # ------------------------------------------------------------- options
    def option_chain(
        self, ticker: str, expiry: date | None, as_of: date
    ) -> pd.DataFrame:
        """No fallback exists for this at any price the ADR found under
        $3,500/month. If it fails, the honest answer is to fail."""
        tk = self._ticker(ticker)
        try:
            expiries = list(tk.options or ())
            if not expiries:
                raise DataQualityError(f"yfinance: {ticker} has no option expiries")
            chosen = expiry.isoformat() if expiry else expiries[0]
            if chosen not in expiries:
                raise DataQualityError(
                    f"yfinance: {ticker} has no expiry {chosen}; available {expiries[:3]}"
                )
            chain = tk.option_chain(chosen)
        except DataQualityError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderUnavailable(
                f"yfinance: option_chain for {ticker}: {exc}"
            ) from exc
        calls, puts = chain.calls.copy(), chain.puts.copy()
        calls["kind"], puts["kind"] = "call", "put"
        both = pd.concat([calls, puts], ignore_index=True)
        if both.empty:
            raise DataQualityError(f"yfinance: {ticker} option chain is empty")
        return both

    # --------------------------------------------------------------- macro
    def macro_series(self, series_id: str, start: date, end: date) -> pd.Series:
        """Fallback for FRED. ^VIX and DX-Y.NYB live here natively; UST 10Y
        deliberately does NOT — that is FRED's DGS10, because ^TNX is the
        series guard (a) was written for."""
        frame = self.daily_bars(series_id, start, end)
        if "Close" not in frame.columns:
            raise DataQualityError(f"yfinance: {series_id} has no Close column")
        series = frame["Close"]
        series.name = series_id
        return series
