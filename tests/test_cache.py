"""The TTL cache — built, not adopted. See internal-docs/specs/T2-spec.md.

The interesting behaviour is that TTL depends on `as_of`: a past date is
immutable and cached for a month; today is volatile and expires in minutes.
DanisHack's cache.py has one flat TTL and cannot express that, which is why
T2 builds instead of adopting.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from desk.cache import HISTORICAL_TTL, TODAY_TTL, TTLCache

TODAY = date(2026, 8, 20)
NOW = datetime(2026, 8, 20, 12, 0, 0)


class FakeClock:
    """Injected so TTL tests assert on expiry rather than on sleeping."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(NOW)


@pytest.fixture
def cache(tmp_path: Path, clock: FakeClock) -> TTLCache:
    return TTLCache(root=tmp_path, clock=clock, today=lambda: TODAY)


# --------------------------------------------------------------- round-trip
def test_miss_returns_none(cache: TTLCache) -> None:
    assert cache.get("quote", "NVDA", TODAY) is None


def test_mapping_round_trip(cache: TTLCache) -> None:
    cache.set("quote", "NVDA", TODAY, {"pe": 41.2, "beta": 1.7})
    assert cache.get("quote", "NVDA", TODAY) == {"pe": 41.2, "beta": 1.7}


def test_bool_round_trip(cache: TTLCache) -> None:
    """is_live() caches a bool. False must survive as False, not as a miss."""
    cache.set("is_live", "TIVO", TODAY, False)
    assert cache.get("is_live", "TIVO", TODAY) is False


def test_frame_round_trip_is_exact(cache: TTLCache) -> None:
    """No pickle, and no float drift.

    Measured: to_json(orient="table") alone loses ~5e-11; with
    double_precision=15 the round-trip is bit-exact. A cache that returns
    something other than what it stored is a defect, however small.
    """
    df = pd.read_csv(
        "tests/fixtures/recorded/nvda_bars_6mo.csv", index_col=0, parse_dates=True
    )
    cache.set("bars", "NVDA", TODAY, df)
    back = cache.get("bars", "NVDA", TODAY)
    assert isinstance(back, pd.DataFrame)
    assert back.shape == df.shape
    num = df.select_dtypes("number")
    assert (num - back.select_dtypes("number")).abs().max().max() == 0.0


def test_series_round_trip(cache: TTLCache) -> None:
    s = pd.Series([4.71, 4.65], index=pd.to_datetime(["2026-08-18", "2026-08-19"]))
    cache.set("macro", "DGS10", TODAY, s)
    back = cache.get("macro", "DGS10", TODAY)
    assert isinstance(back, pd.Series)
    assert list(back.values) == [4.71, 4.65]


# --------------------------------------------------------------------- TTL
def test_today_expires_after_short_ttl(cache: TTLCache, clock: FakeClock) -> None:
    cache.set("quote", "NVDA", TODAY, {"pe": 41.2})
    clock.advance(TODAY_TTL - timedelta(seconds=1))
    assert cache.get("quote", "NVDA", TODAY) is not None
    clock.advance(timedelta(seconds=2))
    assert cache.get("quote", "NVDA", TODAY) is None


def test_past_is_cached_far_longer_than_today(cache: TTLCache, clock: FakeClock) -> None:
    """The whole reason this is not a flat-TTL cache."""
    past = date(2026, 1, 5)
    cache.set("bars", "NVDA", past, {"close": 1.0})
    cache.set("bars", "NVDA", TODAY, {"close": 2.0})
    clock.advance(TODAY_TTL + timedelta(minutes=1))
    assert cache.get("bars", "NVDA", TODAY) is None, "today should have expired"
    assert cache.get("bars", "NVDA", past) == {"close": 1.0}, "the past does not change"


def test_past_eventually_expires(cache: TTLCache, clock: FakeClock) -> None:
    past = date(2026, 1, 5)
    cache.set("bars", "NVDA", past, {"close": 1.0})
    clock.advance(HISTORICAL_TTL + timedelta(days=1))
    assert cache.get("bars", "NVDA", past) is None


def test_ttl_for_past_and_today_differ(cache: TTLCache) -> None:
    assert cache.ttl_for(date(2026, 1, 5)) == HISTORICAL_TTL
    assert cache.ttl_for(TODAY) == TODAY_TTL


# ----------------------------------------------------------------- mutation
def test_get_returns_a_copy_not_the_cached_object(cache: TTLCache) -> None:
    """Two callers must not share one frame. Mutating a result must not
    poison the cache for everyone else."""
    df = pd.DataFrame({"Close": [1.0, 2.0]})
    cache.set("bars", "NVDA", TODAY, df)
    first = cache.get("bars", "NVDA", TODAY)
    assert first is not None
    first.loc[0, "Close"] = 999.0
    second = cache.get("bars", "NVDA", TODAY)
    assert second is not None
    assert second.loc[0, "Close"] == 1.0


# ------------------------------------------------------------------ safety
def test_corrupt_entry_is_a_miss_not_an_exception(cache: TTLCache, tmp_path: Path) -> None:
    cache.set("quote", "NVDA", TODAY, {"pe": 41.2})
    for f in tmp_path.rglob("*.json"):
        f.write_text("{ this is not json")
    assert cache.get("quote", "NVDA", TODAY) is None


def test_cache_file_contains_no_pickle(cache: TTLCache, tmp_path: Path) -> None:
    """A cache file must never be able to execute code on read."""
    cache.set("bars", "NVDA", TODAY, pd.DataFrame({"Close": [1.0]}))
    files = list(tmp_path.rglob("*.json"))
    assert files, "nothing was written"
    for f in files:
        json.loads(f.read_text())  # parses as plain JSON or this raises
        assert b"\x80\x04" not in f.read_bytes(), "pickle protocol marker present"


def test_awkward_symbols_do_not_escape_the_cache_root(cache: TTLCache, tmp_path: Path) -> None:
    """Real symbols include ^VIX, DX-Y.NYB, BRK.B. A naive path join with
    '../..' or a slash would write outside the cache root."""
    for sym in ("^VIX", "DX-Y.NYB", "BRK.B", "../../etc/passwd"):
        cache.set("quote", sym, TODAY, {"v": 1})
        assert cache.get("quote", sym, TODAY) == {"v": 1}
    for f in tmp_path.rglob("*"):
        assert tmp_path in f.resolve().parents or f.resolve() == tmp_path


def test_distinct_keys_do_not_collide(cache: TTLCache) -> None:
    cache.set("quote", "NVDA", TODAY, {"v": 1})
    cache.set("quote", "AMD", TODAY, {"v": 2})
    cache.set("bars", "NVDA", TODAY, {"v": 3})
    cache.set("quote", "NVDA", date(2026, 1, 5), {"v": 4})
    assert cache.get("quote", "NVDA", TODAY) == {"v": 1}
    assert cache.get("quote", "AMD", TODAY) == {"v": 2}
    assert cache.get("bars", "NVDA", TODAY) == {"v": 3}
    assert cache.get("quote", "NVDA", date(2026, 1, 5)) == {"v": 4}


def test_metadata_round_trips_with_the_value(cache: TTLCache) -> None:
    """Provenance must survive the cache — see Sourced.cached."""
    cache.set("estimates", "NVDA", TODAY, {"n": 42.0}, meta={"source": "yfinance"})
    entry = cache.get_entry("estimates", "NVDA", TODAY)
    assert entry is not None
    value, meta = entry
    assert value == {"n": 42.0}
    assert meta["source"] == "yfinance"


def test_entry_without_metadata_is_still_readable(cache: TTLCache) -> None:
    cache.set("estimates", "NVDA", TODAY, {"n": 1.0})
    entry = cache.get_entry("estimates", "NVDA", TODAY)
    assert entry is not None and entry[1] == {}
