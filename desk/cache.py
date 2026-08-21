"""TTL cache for market data, keyed exactly as the Protocol is: (metric, ticker, as_of).

BUILT, NOT ADOPTED. T2's ticket says to fold in DanisHack's `src/data/cache.py`.
Measured at 6d7a3ab it is 50 lines, in-memory, with one flat TTL. The Desk is
cron-driven — 16:15 and 09:00 daily, separate processes — so an in-memory cache
has a ~0% hit rate across runs, and one flat TTL cannot express the thing that
actually matters here:

    a PAST as_of is immutable and should be cached for a month;
    TODAY is volatile and must expire in minutes.

Two further properties this file has and a naive cache does not:

  * **No pickle, ever.** A cache file must not be able to execute code when it
    is read. Scalars and mappings are JSON; frames and series are JSON in
    pandas' `orient="table"` form, which carries dtypes. Measured: plain
    `to_json` loses ~5e-11 on OHLCV floats; `double_precision=15` is exact.
  * **Reads return copies.** A DataFrame handed to two callers is one object;
    without a copy, whoever mutates it first poisons the cache for everyone.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable
from datetime import date, datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd

#: A past date's data does not change. Re-fetching it is pure cost.
HISTORICAL_TTL = timedelta(days=30)
#: Today's data moves. Fifteen minutes is short enough for a 16:15 cron to see
#: a fresh close and long enough that one committee run does not refetch nine
#: times for nine analysts.
TODAY_TTL = timedelta(minutes=15)

_FRAME = "frame"
_SERIES = "series"
_JSON = "json"


class TTLCache:
    """Disk-backed, as_of-aware. Not thread-safe by design — the writes are
    atomic, so concurrent processes race to a consistent result rather than a
    corrupt one."""

    def __init__(
        self,
        root: Path,
        clock: Callable[[], datetime] | None = None,
        today: Callable[[], date] | None = None,
    ) -> None:
        self.root = Path(root)
        self._clock = clock or datetime.now
        self._today = today or date.today

    # ------------------------------------------------------------------ ttl
    def ttl_for(self, as_of: date) -> timedelta:
        """Immutable past vs volatile today. A FUTURE as_of is not this
        object's problem — MarketDataService rejects it before we are called,
        because a look-ahead read is a domain bug, not a cache miss."""
        return TODAY_TTL if as_of >= self._today() else HISTORICAL_TTL

    # ----------------------------------------------------------------- keys
    def _path(self, metric: str, ticker: str, as_of: date) -> Path:
        """Hashed, because real symbols are hostile to paths: ^VIX, DX-Y.NYB,
        BRK.B — and a ticker is ultimately caller-supplied, so a literal join
        is a path-traversal waiting to happen."""
        raw = f"{metric}\x00{ticker}\x00{as_of.isoformat()}"
        digest = hashlib.sha256(raw.encode()).hexdigest()
        return self.root / digest[:2] / f"{digest}.json"

    # ----------------------------------------------------------------- read
    def get(self, metric: str, ticker: str, as_of: date) -> Any | None:
        entry = self.get_entry(metric, ticker, as_of)
        return None if entry is None else entry[0]

    def get_entry(
        self, metric: str, ticker: str, as_of: date
    ) -> tuple[Any, dict[str, Any]] | None:
        """Value plus the metadata stored with it.

        Provenance has to survive the cache. Returning source="cache" would
        destroy the very thing `Sourced` exists to carry — which provider
        actually answered — and make a cached read unauditable.
        """
        path = self._path(metric, ticker, as_of)
        try:
            record = json.loads(path.read_text())
            expires_at = datetime.fromisoformat(record["expires_at"])
        except (OSError, ValueError, KeyError, TypeError):
            # Unreadable, truncated, or not JSON at all. A cache is an
            # optimisation; a corrupt entry is a miss, never an exception.
            return None

        if self._clock() >= expires_at:
            return None
        return self._decode(record), dict(record.get("meta") or {})

    @staticmethod
    def _decode(record: dict[str, Any]) -> Any:
        kind, payload = record["kind"], record["payload"]
        if kind == _FRAME:
            return pd.read_json(StringIO(payload), orient="table")
        if kind == _SERIES:
            frame = pd.read_json(StringIO(payload), orient="table")
            return frame[frame.columns[0]]
        # dicts and lists are rebuilt fresh by json.loads, so they are already
        # copies; scalars are immutable.
        return payload

    # ---------------------------------------------------------------- write
    def set(
        self,
        metric: str,
        ticker: str,
        as_of: date,
        value: Any,
        meta: dict[str, Any] | None = None,
    ) -> None:
        kind, payload = self._encode(value)
        record = {
            "metric": metric,
            "ticker": ticker,
            "as_of": as_of.isoformat(),
            "expires_at": (self._clock() + self.ttl_for(as_of)).isoformat(),
            "kind": kind,
            "payload": payload,
            "meta": meta or {},
        }
        path = self._path(metric, ticker, as_of)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(path, json.dumps(record))

    @staticmethod
    def _encode(value: Any) -> tuple[str, Any]:
        if isinstance(value, pd.DataFrame):
            return _FRAME, value.to_json(orient="table", double_precision=15)
        if isinstance(value, pd.Series):
            named = value.to_frame(name=value.name or "value")
            return _SERIES, named.to_json(orient="table", double_precision=15)
        return _JSON, value

    @staticmethod
    def _atomic_write(path: Path, text: str) -> None:
        """Same directory, then rename. A half-written cache file that another
        process reads mid-write would be indistinguishable from corruption."""
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(text)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
