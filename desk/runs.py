"""Run, agent-output and verdict persistence — the T3 tables, finally written to.

T7: "Persist every agent output to agent_outputs." DESK_DESIGN §4 is blunt
about why: "Every agent output is persisted. Without agent_outputs you cannot
debug a bad verdict, and you will get bad verdicts."

`runs.token_cost` is filled from T2's per-call ledger. That handoff was
defined in T3 and is executed here:

    runs.token_cost == SpendLedger.total_for_run(run_id)
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from desk.spend import SpendLedger
from desk.verdict import Verdict


def start_run(
    conn: sqlite3.Connection, workflow: str, ticker: str | None = None
) -> str:
    cursor = conn.execute(
        "INSERT INTO runs(workflow, ticker, started_at, status) VALUES(?,?,?,'RUNNING')",
        (workflow, ticker, datetime.now(UTC).isoformat()),
    )
    conn.commit()
    return str(cursor.lastrowid)


def record_agent_output(
    conn: sqlite3.Connection,
    run_id: str,
    agent: str,
    payload: Any,
    latency_ms: int | None = None,
) -> None:
    """EVERY output, including rejected ones.

    A report the quality gate threw away is exactly the one you need when
    debugging why the verdict was wrong — so it is persisted with its grade,
    not dropped.
    """
    conn.execute(
        "INSERT INTO agent_outputs(run_id, agent, payload_json, latency_ms) VALUES(?,?,?,?)",
        (int(run_id), agent, json.dumps(payload, default=str), latency_ms),
    )
    conn.commit()


def record_verdict(conn: sqlite3.Connection, run_id: str, verdict: Verdict) -> None:
    conn.execute(
        "INSERT INTO verdicts(run_id, action, price_low, price_high, conviction, rationale) "
        "VALUES(?,?,?,?,?,?)",
        (int(run_id), verdict.action.value, verdict.price_low, verdict.price_high,
         verdict.conviction, verdict.rationale),
    )
    conn.commit()


def finish_run(
    conn: sqlite3.Connection,
    run_id: str,
    ledger: SpendLedger,
    status: str = "DONE",
    model: str | None = None,
) -> float:
    """Close the run and stamp its cost from the T2 ledger."""
    cost = ledger.total_for_run(run_id)
    conn.execute(
        "UPDATE runs SET finished_at = ?, status = ?, token_cost = ?, model = ? WHERE id = ?",
        (datetime.now(UTC).isoformat(), status, cost, model, int(run_id)),
    )
    conn.commit()
    return cost
