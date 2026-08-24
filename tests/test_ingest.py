"""Book ingest and reconciliation.

The governing sentence for this whole module, from DESK_DESIGN §4.5:

    "An import that silently clobbers a stop loss is the single most damaging
     bug this system can have."

So the first test is the ticket's Done criterion, and it is mutation-tested.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from adapters.canonical import MissingColumn, UnknownColumn, load_csv, normalise_headers
from desk.book import load_book
from desk.db import get_meta, init_db, set_meta
from desk.ingest import CLOSED, UNCHANGED, UPDATED, days_stale, ingest

FIXTURES = Path(__file__).parent / "fixtures"
BOOK = Path("config/book.example.yaml")


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path


def _seed(workspace: Path, csv: str = "positions_1.csv") -> Path:
    db = workspace / "desk.db"
    ingest(FIXTURES / csv, db, BOOK, commit=True, imports_dir=workspace / "imports")
    return db


def _make_run(conn: sqlite3.Connection, run_id: int) -> int:
    """A thesis_run_id must reference a real run — the FK enforces it, which
    an earlier version of these tests discovered by inventing one."""
    conn.execute(
        "INSERT INTO runs(id, workflow, started_at, status) VALUES(?, 'W2', ?, 'DONE')",
        (run_id, "2026-08-20T00:00:00+00:00"),
    )
    return run_id


def _row(db: Path, ticker: str) -> sqlite3.Row:
    conn = init_db(db)
    try:
        got = conn.execute("SELECT * FROM positions WHERE ticker = ?", (ticker,)).fetchone()
        assert got is not None, f"{ticker} not in positions"
        return got
    finally:
        conn.close()


# ======================================================================
# THE Done criterion
# ======================================================================
def test_reimport_with_changed_quantities_preserves_stops_targets_and_thesis(
    workspace: Path,
) -> None:
    """TICKETS T3 Done, asserted directly.

    NVDA's qty goes 100 -> 140 between the two fixtures. Its stop, target and
    thesis link must come through untouched.
    """
    db = _seed(workspace)
    conn = init_db(db)
    with conn:
        _make_run(conn, 4242)
        conn.execute(
            "UPDATE positions SET stop = ?, target = ?, thesis_run_id = ? WHERE ticker = 'NVDA'",
            (150.0, 220.0, 4242),
        )
    conn.close()

    before = _row(db, "NVDA")
    assert before["qty"] == 100.0

    ingest(FIXTURES / "positions_2_qty_changed.csv", db, BOOK,
           commit=True, imports_dir=workspace / "imports")

    after = _row(db, "NVDA")
    assert after["qty"] == 140.0, "the CSV-owned field should have updated"
    assert after["cost_basis"] == 21000.0
    # The whole ballgame:
    assert after["stop"] == 150.0, "STOP WAS CLOBBERED BY AN IMPORT"
    assert after["target"] == 220.0, "target was clobbered by an import"
    assert after["thesis_run_id"] == 4242, "thesis link was clobbered by an import"
    assert after["opened_at"] == before["opened_at"]


def test_no_executed_sql_ever_writes_a_book_owned_column(workspace: Path, monkeypatch) -> None:
    """A structural guard on top of the behavioural one above.

    The behavioural test only catches a clobber of the three fields it happens
    to set. This traces EVERY statement SQLite actually executes during a real
    reconciliation and asserts none of them assigns a book-owned column.

    An earlier version of this test sliced the source text instead, and a
    mutation that appended `stop = NULL` to the second line of the
    concatenated SQL string sailed straight past it. Reading what ran beats
    reading what was written.
    """
    import desk.db as db_module

    executed: list[str] = []
    real_connect = db_module.connect

    def tracing_connect(path: Path | str) -> sqlite3.Connection:
        conn = real_connect(path)
        conn.set_trace_callback(executed.append)
        return conn

    monkeypatch.setattr(db_module, "connect", tracing_connect)

    db = workspace / "desk.db"
    ingest(FIXTURES / "positions_1.csv", db, BOOK, commit=True,
           imports_dir=workspace / "imports")
    ingest(FIXTURES / "positions_2_qty_changed.csv", db, BOOK, commit=True,
           imports_dir=workspace / "imports")

    assert executed, "the trace captured nothing; the test proves nothing"
    writes = [
        s for s in executed
        if s.lstrip().upper().startswith(("UPDATE", "INSERT INTO POSITIONS"))
    ]
    assert writes, "no position writes were traced"
    for statement in writes:
        if "positions" not in statement.lower():
            continue
        assignments = statement.lower().split("set", 1)[-1]
        for forbidden in ("stop", "target", "thesis_run_id", "opened_at"):
            assert f"{forbidden} =" not in assignments, (
                f"executed SQL assigns book-owned column {forbidden!r}:\n{statement}"
            )


# ======================================================================
# dry run is the default
# ======================================================================
def test_dry_run_is_the_default_and_writes_nothing(workspace: Path) -> None:
    db = _seed(workspace)
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    report = ingest(FIXTURES / "positions_2_qty_changed.csv", db, BOOK)  # no commit=
    assert report.committed is False
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before, "dry run mutated the db"


def test_dry_run_does_not_even_create_the_database(workspace: Path) -> None:
    db = workspace / "nothing-here.db"
    ingest(FIXTURES / "positions_1.csv", db, BOOK)
    assert not db.exists(), "a dry run created a database file"


def test_dry_run_still_reports_the_full_diff(workspace: Path) -> None:
    db = _seed(workspace)
    report = ingest(FIXTURES / "positions_2_qty_changed.csv", db, BOOK)
    assert {c.kind for c in report.changes} == {UPDATED, UNCHANGED, CLOSED}
    assert "DRY RUN" in report.render()


# ======================================================================
# the four reconciliation rules
# ======================================================================
def test_new_ticker_is_unmanaged_when_the_book_does_not_cover_it(workspace: Path) -> None:
    db = _seed(workspace)
    assert _row(db, "GOOG")["status"] == "UNMANAGED"
    assert _row(db, "NVDA")["status"] == "OPEN", "book.yaml covers NVDA, so it is evaluable"


def test_missing_ticker_is_closed_not_deleted_and_keeps_its_thesis(workspace: Path) -> None:
    """§4.5: 'Do not delete. Mark status=CLOSED, retain thesis and run history.'"""
    db = _seed(workspace)
    conn = init_db(db)
    with conn:
        _make_run(conn, 77)
        conn.execute("UPDATE positions SET thesis_run_id = 77, stop = 9.0 WHERE ticker = 'GIV'")
    conn.close()

    ingest(FIXTURES / "positions_2_qty_changed.csv", db, BOOK,
           commit=True, imports_dir=workspace / "imports")

    giv = _row(db, "GIV")           # raises if the row was deleted
    assert giv["status"] == "CLOSED"
    assert giv["thesis_run_id"] == 77, "thesis history lost on close"
    assert giv["stop"] == 9.0


def test_qty_change_writes_an_audit_row(workspace: Path) -> None:
    """§4.5: 'a size change you didn't make through a ticket is worth surfacing'."""
    db = _seed(workspace)
    ingest(FIXTURES / "positions_2_qty_changed.csv", db, BOOK,
           commit=True, imports_dir=workspace / "imports")
    conn = init_db(db)
    rows = conn.execute(
        "SELECT * FROM audit WHERE action = 'QTY_CHANGED' AND subject LIKE 'NVDA%'"
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    assert "100.0" in rows[0]["payload_json"] and "140.0" in rows[0]["payload_json"]


def test_unchanged_position_produces_no_audit_noise(workspace: Path) -> None:
    db = _seed(workspace)
    ingest(FIXTURES / "positions_1.csv", db, BOOK, commit=True,
           imports_dir=workspace / "imports")
    conn = init_db(db)
    n = conn.execute("SELECT count(*) c FROM audit WHERE action = 'QTY_CHANGED'").fetchone()["c"]
    conn.close()
    assert n == 0


def test_raw_csv_is_archived_byte_identical(workspace: Path) -> None:
    """§4.5: 'always write the raw CSV to imports/ unmodified; every
    reconciliation must be replayable'."""
    source = FIXTURES / "positions_1.csv"
    report = ingest(source, workspace / "desk.db", BOOK, commit=True,
                    imports_dir=workspace / "imports")
    assert report.archived_to is not None
    assert report.archived_to.read_bytes() == source.read_bytes()
    assert source.exists(), "the original export must not be consumed"


# ======================================================================
# the adapter seam
# ======================================================================
def test_unrecognised_column_raises_and_is_never_dropped() -> None:
    with pytest.raises(UnknownColumn, match="unrecognised"):
        normalise_headers(["ticker", "qty", "surprise_column"])


def test_missing_required_column_raises() -> None:
    with pytest.raises(MissingColumn):
        normalise_headers(["ticker", "market_value"])


def test_broker_formatting_is_parsed() -> None:
    """Real exports write '$1,234.56' and '(500.00)' for negatives."""
    rows = load_csv(FIXTURES / "positions_3_broker_headers.csv")
    by_ticker = {r.ticker: r for r in rows}
    assert by_ticker["NVDA"].qty == 1000.0
    assert by_ticker["NVDA"].cost_basis == 150000.0
    assert by_ticker["MU"].market_value == -500.0, "parenthesised negative"
    assert by_ticker["NVDA"].account == "IRA"


def test_same_ticker_in_two_accounts_does_not_collide(workspace: Path) -> None:
    """G1: §4.5 matches on (ticker, account) but §4's schema had no account
    column. Without it these two rows become one."""
    csv = workspace / "two_accounts.csv"
    csv.write_text(
        "ticker,qty,cost_basis,market_value,account\n"
        "NVDA,100,15000,19100,brokerage\n"
        "NVDA,40,6000,7640,IRA\n"
    )
    db = workspace / "desk.db"
    ingest(csv, db, BOOK, commit=True, imports_dir=workspace / "imports")
    conn = init_db(db)
    rows = conn.execute(
        "SELECT account, qty FROM positions WHERE ticker='NVDA' ORDER BY account"
    ).fetchall()
    conn.close()
    assert [(r["account"], r["qty"]) for r in rows] == [("IRA", 40.0), ("brokerage", 100.0)]


# ======================================================================
# schema
# ======================================================================
def test_check_constraints_reject_bad_enums(workspace: Path) -> None:
    conn = init_db(workspace / "desk.db")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO positions(ticker,qty,status) VALUES('X',1,'NONSENSE')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO tickets(ticker,side,state,created_at) VALUES('X','BUY','MAYBE','t')"
        )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO tickets(ticker,side,created_at,decided_by_kind) "
            "VALUES('X','BUY','t','ROBOT')"
        )
    conn.close()


def test_foreign_keys_are_enforced(workspace: Path) -> None:
    """SQLite disables FKs by DEFAULT, per connection. A schema full of
    REFERENCES clauses that are never enforced looks exactly like one that is."""
    conn = init_db(workspace / "desk.db")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO agent_outputs(run_id,agent,payload_json) VALUES(999,'x','{}')")
    conn.close()


def test_all_seven_design_tables_exist(workspace: Path) -> None:
    conn = init_db(workspace / "desk.db")
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert {"positions", "exit_rules", "runs", "agent_outputs", "verdicts",
            "tickets", "audit"} <= names, "a DESK_DESIGN §4 table is missing"


# ======================================================================
# staleness (G2)
# ======================================================================
def test_last_import_at_is_stamped_and_staleness_computed(workspace: Path) -> None:
    """§4.5: W1 must refuse to run — loudly — on a book more than 3 days old."""
    db = _seed(workspace)
    conn = init_db(db)
    assert get_meta(conn, "last_import_at") is not None
    assert days_stale(conn) == 0
    with conn:
        set_meta(conn, "last_import_at", (date.today() - timedelta(days=5)).isoformat())
    assert days_stale(conn) == 5
    conn.close()


def test_staleness_is_none_when_never_imported(workspace: Path) -> None:
    conn = init_db(workspace / "desk.db")
    assert days_stale(conn) is None, "never-imported must be distinguishable from fresh"
    conn.close()


# ======================================================================
# book.yaml
# ======================================================================
def test_example_book_parses() -> None:
    book = load_book(BOOK)
    assert ("NVDA", "brokerage") in book
    nvda = book[("NVDA", "brokerage")]
    assert nvda.stop == 150.0 and nvda.target == 220.0
    assert {r.kind for r in nvda.exit_rules} == {"fixed_stop", "trailing_stop", "take_profit"}


def test_absent_book_is_legitimate(tmp_path: Path) -> None:
    """A book with no overlay means every position is UNMANAGED — which is
    exactly what the health report should say, not a crash."""
    assert load_book(tmp_path / "nope.yaml") == {}


def test_duplicate_book_entry_raises(tmp_path: Path) -> None:
    p = tmp_path / "book.yaml"
    p.write_text("positions:\n  - ticker: NVDA\n    stop: 1\n  - ticker: NVDA\n    stop: 2\n")
    with pytest.raises(ValueError, match="duplicate"):
        load_book(p)
