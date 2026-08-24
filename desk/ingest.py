"""Canonical CSV -> book reconciliation.

    "An import that silently clobbers a stop loss is the single most damaging
     bug this system can have."  -- DESK_DESIGN §4.5

Everything here is arranged around that sentence. The UPDATE statement sets
exactly three columns, named literally, and a test asserts a stop survives a
re-import with changed quantities. `--dry-run` is the DEFAULT.

Reconciliation rules (§4.5), verbatim:

  in CSV, not in book -> new position, status=UNMANAGED, flagged as needing
                         stops before it can be evaluated
  in book, not in CSV -> closed at the custodian. Do NOT delete. status=CLOSED,
                         retain thesis and run history
  both                -> update qty and cost basis from CSV. NEVER touch
                         stops, targets, exit rules, or thesis_run_id
  qty changed         -> log to audit
  always              -> write the raw CSV to imports/ unmodified; every
                         reconciliation must be replayable
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sqlite3
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from adapters.canonical import Row, load_csv
from desk.book import BookEntry, load_book
from desk.db import init_db, set_meta, transaction

log = logging.getLogger(__name__)

NEW, CLOSED, UPDATED, UNCHANGED = "NEW", "CLOSED", "UPDATED", "UNCHANGED"

#: The ONLY columns a CSV import may write to an existing position. Named
#: literally rather than derived, so that widening this set is a visible,
#: reviewable diff and never an accident of refactoring.
CSV_OWNED_COLUMNS = ("qty", "cost_basis", "market_value")

#: Owned by config/book.yaml. An import must never write these.
BOOK_OWNED_COLUMNS = ("stop", "target", "thesis_run_id", "opened_at")


@dataclass(frozen=True)
class Change:
    kind: str
    ticker: str
    account: str
    fields: dict[str, tuple[object, object]] = field(default_factory=dict)

    def describe(self) -> str:
        where = f"{self.ticker}" + (f"@{self.account}" if self.account else "")
        if not self.fields:
            return f"  {self.kind:9s} {where}"
        bits = ", ".join(f"{k}: {b} -> {a}" for k, (b, a) in sorted(self.fields.items()))
        return f"  {self.kind:9s} {where}  ({bits})"


@dataclass
class IngestReport:
    changes: list[Change]
    committed: bool
    archived_to: Path | None = None

    def of_kind(self, kind: str) -> list[Change]:
        return [c for c in self.changes if c.kind == kind]

    def render(self) -> str:
        lines = [c.describe() for c in self.changes] or ["  (no differences)"]
        counts = {k: len(self.of_kind(k)) for k in (NEW, UPDATED, CLOSED, UNCHANGED)}
        summary = " · ".join(f"{v} {k.lower()}" for k, v in counts.items())
        mode = "COMMITTED" if self.committed else "DRY RUN — nothing written"
        return "\n".join([*lines, "", f"  {summary}", f"  {mode}"])


def _existing(conn: sqlite3.Connection) -> dict[tuple[str, str], sqlite3.Row]:
    return {
        (r["ticker"], r["account"]): r
        for r in conn.execute("SELECT * FROM positions")
    }


def _status_for(key: tuple[str, str], book: dict[tuple[str, str], BookEntry]) -> str:
    """OPEN means imported AND covered by book.yaml — i.e. it has the stops
    needed for the exit-rule engine to evaluate it. Without that overlay the
    position is UNMANAGED and the health report must say so."""
    return "OPEN" if key in book else "UNMANAGED"


def reconcile(
    conn: sqlite3.Connection,
    rows: list[Row],
    book: dict[tuple[str, str], BookEntry],
) -> list[Change]:
    existing = _existing(conn)
    seen: set[tuple[str, str]] = set()
    changes: list[Change] = []

    for row in rows:
        seen.add(row.key)
        current = existing.get(row.key)
        if current is None:
            changes.append(
                Change(NEW, row.ticker, row.account,
                       {"qty": (None, row.qty), "status": (None, _status_for(row.key, book))})
            )
            continue
        diff: dict[str, tuple[object, object]] = {}
        for column in CSV_OWNED_COLUMNS:
            before, after = current[column], getattr(row, column)
            if before != after:
                diff[column] = (before, after)
        want_status = _status_for(row.key, book)
        if current["status"] != want_status:
            diff["status"] = (current["status"], want_status)
        changes.append(
            Change(UPDATED if diff else UNCHANGED, row.ticker, row.account, diff)
        )

    for key, current in existing.items():
        if key in seen or current["status"] == CLOSED:
            continue
        # Closed at the custodian. NOT deleted -- the thesis and run history
        # are the reason the position is interesting after it is gone.
        changes.append(
            Change(CLOSED, key[0], key[1], {"status": (current["status"], CLOSED)})
        )
    return changes


def _audit(
    conn: sqlite3.Connection, action: str, subject: str, payload: dict[str, object], actor: str
) -> None:
    conn.execute(
        "INSERT INTO audit(ts, actor, actor_kind, action, subject, payload_json) "
        "VALUES(?, ?, 'HUMAN', ?, ?, ?)",
        (datetime.now(UTC).isoformat(), actor, action, subject, json.dumps(payload, default=str)),
    )


def apply_changes(
    conn: sqlite3.Connection,
    changes: list[Change],
    rows: list[Row],
    book: dict[tuple[str, str], BookEntry],
    actor: str = "ingest",
) -> None:
    by_key = {r.key: r for r in rows}
    for change in changes:
        key = (change.ticker, change.account)
        if change.kind == NEW:
            row = by_key[key]
            entry = book.get(key)
            conn.execute(
                "INSERT INTO positions"
                "(ticker, account, qty, cost_basis, market_value, stop, target,"
                " thesis_run_id, opened_at, status) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    row.ticker, row.account, row.qty, row.cost_basis, row.market_value,
                    entry.stop if entry else None,
                    entry.target if entry else None,
                    entry.thesis_run_id if entry else None,
                    date.today().isoformat(),
                    _status_for(key, book),
                ),
            )
            _audit(conn, "POSITION_OPENED", f"{change.ticker}@{change.account}",
                   {"qty": row.qty, "status": _status_for(key, book)}, actor)

        elif change.kind == UPDATED:
            row = by_key[key]
            # EXACTLY three columns, plus status. Written out literally: a
            # loop over "whatever changed" is how `stop` eventually joins the
            # SET clause during a refactor nobody reviews closely.
            conn.execute(
                "UPDATE positions SET qty = ?, cost_basis = ?, market_value = ?, "
                "status = ? WHERE ticker = ? AND account = ?",
                (row.qty, row.cost_basis, row.market_value,
                 _status_for(key, book), row.ticker, row.account),
            )
            if "qty" in change.fields:
                # §4.5: "a size change you didn't make through a ticket is
                # worth surfacing".
                before, after = change.fields["qty"]
                _audit(conn, "QTY_CHANGED", f"{change.ticker}@{change.account}",
                       {"before": before, "after": after}, actor)

        elif change.kind == CLOSED:
            conn.execute(
                "UPDATE positions SET status = 'CLOSED' WHERE ticker = ? AND account = ?",
                (change.ticker, change.account),
            )
            _audit(conn, "POSITION_CLOSED", f"{change.ticker}@{change.account}",
                   {"reason": "absent from custodian export"}, actor)


def archive_csv(source: Path, imports_dir: Path) -> Path:
    """§4.5: "always write the raw CSV to imports/ unmodified; every
    reconciliation must be replayable"."""
    imports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    target = imports_dir / f"positions_{stamp}_{source.name}"
    shutil.copy2(source, target)   # copy2, not move: never consume the original
    return target


def days_stale(conn: sqlite3.Connection, today: date | None = None) -> int | None:
    """For W1's staleness refusal (§4.5, default 3 days). None = never imported."""
    from desk.db import get_meta

    stamp = get_meta(conn, "last_import_at")
    if stamp is None:
        return None
    return ((today or datetime.now(UTC).date()) - date.fromisoformat(stamp[:10])).days


def ingest(
    csv_path: Path | str,
    db_path: Path | str,
    book_path: Path | str,
    commit: bool = False,
    imports_dir: Path | str = "imports",
    actor: str = "ingest",
) -> IngestReport:
    rows = load_csv(csv_path)
    book = load_book(book_path)

    if not commit:
        # "Writes nothing" is taken literally. Rolling back the transaction is
        # NOT enough: opening the real path would create the file when it does
        # not exist, and leave WAL sidecars when it does. A dry run operates on
        # a scratch COPY, so the real database is provably byte-identical
        # afterwards -- which is what the test hashes.
        with tempfile.TemporaryDirectory() as tmp:
            scratch = Path(tmp) / "scratch.db"
            if Path(db_path).exists():
                shutil.copy2(db_path, scratch)
            conn = init_db(scratch)
            try:
                changes = reconcile(conn, rows, book)
            finally:
                conn.close()
        return IngestReport(changes=changes, committed=False)

    conn = init_db(db_path)
    try:
        changes = reconcile(conn, rows, book)
        archived = archive_csv(Path(csv_path), Path(imports_dir))
        with transaction(conn):
            apply_changes(conn, changes, rows, book, actor)
            set_meta(conn, "last_import_at", datetime.now(UTC).isoformat())
        return IngestReport(changes=changes, committed=True, archived_to=archived)
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="desk.ingest",
        description="Reconcile a canonical positions CSV against the book. "
                    "DRY RUN by default -- pass --commit to persist.",
    )
    parser.add_argument("csv", type=Path)
    parser.add_argument("--db", type=Path, default=Path("desk.db"))
    parser.add_argument("--book", type=Path, default=Path("config/book.yaml"))
    parser.add_argument("--imports-dir", type=Path, default=Path("imports"))
    parser.add_argument(
        "--commit", action="store_true",
        help="actually write. Without this nothing is persisted.",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    report = ingest(args.csv, args.db, args.book, commit=args.commit,
                    imports_dir=args.imports_dir)
    print(report.render())
    if report.archived_to:
        print(f"  raw CSV archived to {report.archived_to}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
