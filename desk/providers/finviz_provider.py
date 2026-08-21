"""finvizfinance — SCREENER ONLY.

ADR 0001 is explicit: `ticker_fundament()` is broken upstream and this project
must never call it. `tests/test_invariants.py` asserts by source grep that no
call to it exists anywhere in desk/, so the constraint survives the memory of
whoever wrote it.

There is no fallback for the screener. If it fails, W3's morning screen has no
candidates, and inventing some would be worse than reporting none.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from datetime import date
from typing import Any

import pandas as pd

from desk.providers.base import DataQualityError, ProviderUnavailable

log = logging.getLogger(__name__)


class FinvizProvider:
    name = "finviz"
    CAPABILITIES = frozenset({"screen"})

    def __init__(self, screener_factory: Callable[[], Any] | None = None) -> None:
        self._factory = screener_factory or self._default_factory

    @staticmethod
    def _default_factory() -> Any:
        from finvizfinance.screener.overview import Overview

        return Overview()

    def screen(self, filters: Mapping[str, str], as_of: date) -> pd.DataFrame:
        try:
            screener = self._factory()
            screener.set_filter(filters_dict=dict(filters))
            frame = screener.screener_view()
        except Exception as exc:  # noqa: BLE001 - upstream raises bare Exception
            raise ProviderUnavailable(f"finviz: screener: {exc}") from exc
        if frame is None or not isinstance(frame, pd.DataFrame):
            raise ProviderUnavailable("finviz: screener did not return a frame")
        if frame.empty:
            raise DataQualityError(f"finviz: screen {dict(filters)} matched nothing")
        return frame
