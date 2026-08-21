"""The SQLite schema from DESK_DESIGN §4, plus the three things §4 leaves out.

WHY THE GAPS ARE ADDITIONS AND NOT SILENT PATCHES
-------------------------------------------------
§4 and §4.5 disagree with each other in three places. Both documents are
frozen, so the disagreements are recorded in internal-docs/SUPERSEDED.md and
resolved here:

  G1  §4.5 reconciles on (ticker, account). §4's `positions` has no `account`
      column at all. Without it the matching key cannot be expressed, and the
      same ticker held in two accounts collides into one row.
  G2  §4.5 says stamp `book.last_import_at`. §4 defines no `book` table.
  G3  `positions.status` is never enumerated; §4.5 uses UNMANAGED and CLOSED.

Everything else is §4 verbatim, including the two columns §4 explicitly calls
unused-on-purpose: `decided_by_kind` and `approver_rule_id` exist so that
autonomy is a property of *the approver*, not of the code path.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 1

#: §4.5 uses UNMANAGED and CLOSED; OPEN is the third state — imported AND
#: covered by config/book.yaml, i.e. it has the stops needed to be evaluated.
POSITION_STATES = ("OPEN", "UNMANAGED", "CLOSED")
#: §4: "tickets.state ∈ {AWAITING_APPROVAL, APPROVED, REJECTED, EXPIRED}"
TICKET_STATES = ("AWAITING_APPROVAL", "APPROVED", "REJECTED", "EXPIRED")
#: §4: "decided_by_kind ∈ {HUMAN, RULE}"
DECIDER_KINDS = ("HUMAN", "RULE")

def _enum(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"CHECK ({column} IN ({joined}))"


SCHEMA = f"""
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS positions (
    id            INTEGER PRIMARY KEY,
    ticker        TEXT    NOT NULL,
    -- G1: the reconciliation key in §4.5 is (ticker, account).
    account       TEXT    NOT NULL DEFAULT '',
    qty           REAL    NOT NULL,
    entry_price   REAL,
    cost_basis    REAL,
    market_value  REAL,
    -- The four fields below are owned by config/book.yaml and are NEVER
    -- written by a CSV import. That is the single most important invariant
    -- in this file; see desk/ingest.py.
    stop          REAL,
    target        REAL,
    thesis_run_id INTEGER REFERENCES runs(id),
    opened_at     TEXT,
    status        TEXT    NOT NULL DEFAULT 'UNMANAGED' {_enum('status', POSITION_STATES)},
    UNIQUE (ticker, account)
);

CREATE TABLE IF NOT EXISTS exit_rules (
    id          INTEGER PRIMARY KEY,
    position_id INTEGER NOT NULL REFERENCES positions(id) ON DELETE CASCADE,
    kind        TEXT    NOT NULL,
    threshold   REAL,
    armed       INTEGER NOT NULL DEFAULT 1,
    note        TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY,
    workflow    TEXT NOT NULL,
    ticker      TEXT,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    model       TEXT,
    -- Populated from the T2 spend ledger: this equals
    -- SpendLedger.total_for_run(run_id). One row per run cannot hold
    -- per-agent, per-model cost for a 16-call committee, which is why the
    -- per-call ledger lives outside this database.
    token_cost  REAL,
    status      TEXT
);

CREATE TABLE IF NOT EXISTS agent_outputs (
    id           INTEGER PRIMARY KEY,
    run_id       INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    agent        TEXT    NOT NULL,
    payload_json TEXT    NOT NULL,
    latency_ms   INTEGER
);

CREATE TABLE IF NOT EXISTS verdicts (
    id         INTEGER PRIMARY KEY,
    run_id     INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    action     TEXT    NOT NULL,
    price_low  REAL,
    price_high REAL,
    conviction INTEGER,
    rationale  TEXT
);

CREATE TABLE IF NOT EXISTS tickets (
    id               INTEGER PRIMARY KEY,
    run_id           INTEGER REFERENCES runs(id),
    ticker           TEXT NOT NULL,
    side             TEXT NOT NULL,
    entry            REAL,
    stop             REAL,
    target           REAL,
    size             REAL,
    max_risk_pct     REAL,
    state            TEXT NOT NULL DEFAULT 'AWAITING_APPROVAL'
                     {_enum('state', TICKET_STATES)},
    created_at       TEXT NOT NULL,
    decided_at       TEXT,
    decided_by       TEXT,
    -- §4: both unused in the initial build -- every ticket is human-approved.
    -- They exist so climbing the autonomy ladder is a data change, not a
    -- code-path change. Costs nothing now, a migration later.
    decided_by_kind  TEXT {_enum('decided_by_kind', DECIDER_KINDS)},
    approver_rule_id INTEGER,
    CHECK (decided_by_kind IS NULL OR approver_rule_id IS NULL
           OR decided_by_kind = 'RULE')
);

CREATE TABLE IF NOT EXISTS audit (
    id           INTEGER PRIMARY KEY,
    ts           TEXT NOT NULL,
    actor        TEXT NOT NULL,
    actor_kind   TEXT NOT NULL,
    action       TEXT NOT NULL,
    subject      TEXT,
    payload_json TEXT
);

-- G2: §4.5 stamps `book.last_import_at`; §4 defines no such table.
CREATE TABLE IF NOT EXISTS book_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
CREATE INDEX IF NOT EXISTS idx_audit_ts        ON audit(ts);
CREATE INDEX IF NOT EXISTS idx_outputs_run     ON agent_outputs(run_id);
"""


def connect(path: Path | str) -> sqlite3.Connection:
    """Open with foreign keys ON.

    SQLite disables foreign keys by DEFAULT, per connection. A schema full of
    REFERENCES clauses that are never enforced looks exactly like one that is.
    """
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path: Path | str) -> sqlite3.Connection:
    conn = connect(path)
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO book_meta(key, value) VALUES('schema_version', ?) "
        "ON CONFLICT(key) DO NOTHING",
        (str(SCHEMA_VERSION),),
    )
    conn.commit()
    return conn


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM book_meta WHERE key = ?", (key,)).fetchone()
    return None if row is None else str(row["value"])


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO book_meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """All-or-nothing. A half-applied reconciliation is worse than none:
    it would leave the book describing a state the custodian never had."""
    try:
        yield conn
    except BaseException:
        conn.rollback()
        raise
    else:
        conn.commit()
