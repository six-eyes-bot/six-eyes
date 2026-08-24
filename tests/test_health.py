"""W1 health report and the staleness guard.

The two things the ticket is emphatic about: a stale book produces a REFUSAL
rather than a report, and an UNMANAGED position is flagged rather than
counted as HOLD.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from desk.book import load_book
from desk.db import init_db, set_meta
from desk.exit_rules import RuleKind, Unit
from desk.health import (
    DEFAULT_MAX_STALE_DAYS,
    BookNeverImported,
    BookStale,
    assert_fresh,
    check,
    rules_for,
)
from desk.ingest import ingest

FIXTURES = Path(__file__).parent / "fixtures"
SEED_CSV = FIXTURES / "positions_seeded_5.csv"
SEED_BOOK = FIXTURES / "book_seeded_5.yaml"
TODAY = date(2026, 8, 21)

#: Spot prices: every one inside its stop/target band.
PRICES = {"NVDA": 191.0, "MU": 106.0, "GOOG": 189.0, "TIVO": 3.10, "GIV": 12.40}


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "desk.db"
    ingest(SEED_CSV, path, SEED_BOOK, commit=True, imports_dir=tmp_path / "imports")
    return path


def _age(db: Path, days: int) -> None:
    conn = init_db(db)
    with conn:
        set_meta(conn, "last_import_at", (TODAY - timedelta(days=days)).isoformat())
    conn.close()


# ======================================================================
# THE Done criterion
# ======================================================================
def test_seeded_five_position_book_yields_five_hold_zero_exits(db: Path) -> None:
    conn = init_db(db)
    report = check(conn, load_book(SEED_BOOK), PRICES, TODAY)
    conn.close()
    assert "5× HOLD · 0 EXITS TRIGGERED" in report.render()
    assert report.unmanaged == []


def test_flipping_one_stop_above_spot_flips_exactly_one_position(db: Path) -> None:
    """DESK_DESIGN §5 Phase 2 Done: "flipping one stop above spot flips
    exactly one position to triggered"."""
    book = dict(load_book(SEED_BOOK))
    mu_key = ("MU", "brokerage")
    # MU trades at 106; move its stop to 110.
    book[mu_key] = type(book[mu_key])(**{**book[mu_key].__dict__, "stop": 110.0})

    conn = init_db(db)
    report = check(conn, book, PRICES, TODAY)
    conn.close()

    assert len(report.exits) == 1, "exactly one position should have triggered"
    assert report.exits[0].ticker == "MU"
    assert report.exits[0].triggered is not None
    assert report.exits[0].triggered.reason == "fixed_stop"
    assert "4× HOLD · 1 EXITS TRIGGERED" in report.render()


# ======================================================================
# Staleness — a refusal, not a report
# ======================================================================
def test_stale_book_refuses(db: Path) -> None:
    _age(db, DEFAULT_MAX_STALE_DAYS + 1)
    conn = init_db(db)
    with pytest.raises(BookStale, match="REFUSING"):
        check(conn, load_book(SEED_BOOK), PRICES, TODAY)
    conn.close()


def test_fresh_book_at_the_limit_is_allowed(db: Path) -> None:
    """The boundary: exactly N days is fine, N+1 refuses."""
    _age(db, DEFAULT_MAX_STALE_DAYS)
    conn = init_db(db)
    assert assert_fresh(conn, today=TODAY) == DEFAULT_MAX_STALE_DAYS
    conn.close()


def test_never_imported_is_distinguished_from_stale(tmp_path: Path) -> None:
    """Told to import, not to re-import."""
    conn = init_db(tmp_path / "empty.db")
    with pytest.raises(BookNeverImported, match="never been imported"):
        assert_fresh(conn, today=TODAY)
    conn.close()


def test_staleness_is_checked_before_any_evaluation(db: Path) -> None:
    """The refusal must not depend on prices being available, or a stale book
    with missing prices would report 'not evaluated' instead of refusing."""
    _age(db, 30)
    conn = init_db(db)
    with pytest.raises(BookStale):
        check(conn, load_book(SEED_BOOK), {}, TODAY)
    conn.close()


# ======================================================================
# Unevaluated positions are flagged, never counted as HOLD
# ======================================================================
def test_unmanaged_position_is_flagged_not_held(db: Path) -> None:
    """§4.5: flagged "as needing stops before it can be evaluated". Counting
    it as HOLD would report an all-clear for a position with no stop."""
    book = dict(load_book(SEED_BOOK))
    del book[("GOOG", "brokerage")]
    conn = init_db(db)
    report = check(conn, book, PRICES, TODAY)
    conn.close()
    assert len(report.decisions) == 4
    assert [u.ticker for u in report.unmanaged] == ["GOOG"]
    assert "4× HOLD · 0 EXITS TRIGGERED" in report.render()
    assert "UNMANAGED" in report.render()
    assert "1 position(s) NOT evaluated" in report.render()


def test_missing_price_is_not_a_hold(db: Path) -> None:
    """A position we could not price is one we did not check."""
    prices = {k: v for k, v in PRICES.items() if k != "TIVO"}
    conn = init_db(db)
    report = check(conn, load_book(SEED_BOOK), prices, TODAY)
    conn.close()
    assert [u.ticker for u in report.unmanaged] == ["TIVO"]
    assert "NO PRICE" in report.render()
    assert all(d.ticker != "TIVO" for d in report.decisions)


def test_closed_positions_are_excluded(db: Path) -> None:
    conn = init_db(db)
    with conn:
        conn.execute("UPDATE positions SET status='CLOSED' WHERE ticker='GIV'")
    report = check(conn, load_book(SEED_BOOK), PRICES, TODAY)
    conn.close()
    assert all(d.ticker != "GIV" for d in report.decisions)
    assert all(u.ticker != "GIV" for u in report.unmanaged)
    assert "4× HOLD" in report.render()


# ======================================================================
# book.yaml -> rules
# ======================================================================
def test_stop_and_target_become_absolute_price_rules() -> None:
    book = load_book(SEED_BOOK)
    rules = rules_for(book[("NVDA", "brokerage")])
    kinds = {(r.kind, r.unit) for r in rules}
    assert (RuleKind.FIXED_STOP, Unit.PRICE) in kinds
    assert (RuleKind.TAKE_PROFIT, Unit.PRICE) in kinds


def test_horizon_is_not_silently_turned_into_a_time_stop() -> None:
    """`horizon: 2w+` is free text. Inventing a day count from it would
    fabricate an exit rule the operator never wrote."""
    book = load_book(Path("config/book.example.yaml"))
    entry = book[("MU", "brokerage")]
    assert entry.horizon is not None
    assert all(r.kind != RuleKind.TIME_STOP for r in rules_for(entry))


def test_example_book_still_translates_after_the_unit_change() -> None:
    """T4 made units explicit; config/book.example.yaml predates that."""
    for entry in load_book(Path("config/book.example.yaml")).values():
        rules_for(entry)   # raises RuleConfigError if a unit is wrong


# ======================================================================
# Earnings-proximity ALERT (DESK_DESIGN §5 Phase 2)
# ======================================================================
def test_earnings_alert_does_not_trigger_an_exit(db: Path) -> None:
    """§5 calls it an "alert". Auto-exiting before every earnings date would
    quietly close half the book four times a year."""
    book = dict(load_book(SEED_BOOK))
    key = ("NVDA", "brokerage")
    entry = book[key]
    book[key] = type(entry)(**{
        **entry.__dict__,
        "next_earnings": TODAY + timedelta(days=3),
        "exit_rules": (
            *entry.exit_rules,
            __import__("desk.book", fromlist=["ExitRule"]).ExitRule(
                kind="earnings_proximity", threshold=7, unit="days"
            ),
        ),
    })
    conn = init_db(db)
    report = check(conn, book, PRICES, TODAY)
    conn.close()

    nvda = next(d for d in report.decisions if d.ticker == "NVDA")
    assert nvda.exited is False, "an alert must never cause an exit"
    assert [a.reason for a in nvda.alerts] == ["earnings_proximity"]
    assert "earnings in 3d" in report.render()
    assert "5× HOLD · 0 EXITS TRIGGERED" in report.render()


def test_example_book_has_no_duplicate_rules_for_one_condition() -> None:
    """`stop:`/`target:` ARE the fixed-stop and take-profit rules. Listing
    them again under exit_rules produces two identical rules for one
    condition — harmless at runtime, but a confusing thing to ship as the
    example people copy."""
    for key, entry in load_book(Path("config/book.example.yaml")).items():
        kinds = [r.kind for r in rules_for(entry)]
        assert len(kinds) == len(set(kinds)), f"{key} has duplicate rule kinds: {kinds}"
