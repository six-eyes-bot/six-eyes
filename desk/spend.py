"""The spend ledger — one durable row per LLM call.

WHY THIS IS NOT `runs.token_cost`
---------------------------------
DESK_DESIGN §4 defines `runs(id, workflow, ticker, started_at, finished_at,
model, token_cost, status)` — ONE row per run, with ONE model column. T14 needs
per-agent AND per-model cost, and a committee run makes ~16 calls across two
tiers, so a single row per run cannot hold the answer.

This ledger is therefore the per-call record, and `runs.token_cost` becomes a
SUM over it. T3 owns the SQLite schema; T2 must not build it, so the handoff is
explicit rather than a shared table:

    runs.token_cost  ==  SpendLedger.total_for_run(run_id)

JSONL, append-only, one file. Not SQLite, deliberately: T3 owns the database
and a second writer to the same file from a different ticket is how you get a
locking bug at 16:15 on a weekday. Appending a line is atomic under POSIX for
writes below PIPE_BUF, and a torn final line is tolerated on read.
"""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMCall:
    """One call. `model_requested` and `model_served` are separate ON PURPOSE.

    T14: "Fable's safeguards route some queries to Opus 5, and you want that
    visible rather than assumed." If they were one field, a silent reroute
    would be indistinguishable from the model you asked for — and it would be
    billed at the other model's rate.
    """

    ts: str
    workflow: str
    run_id: str
    agent: str
    tier: str
    model_requested: str
    model_served: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    latency_ms: int
    rerouted: bool = False
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def day(self) -> date:
        return datetime.fromisoformat(self.ts).date()


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class SpendLedger:
    """Append-only. Reads tolerate a torn last line rather than crashing —
    a ledger that raises on read would take the cron down for a partial write.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, call: LLMCall) -> None:
        line = json.dumps(asdict(call), sort_keys=True)
        if len(line.encode()) > 4096:  # keep the append comfortably atomic
            log.warning("spend row is %d bytes; trimming extra", len(line))
            line = json.dumps(asdict(call) | {"extra": {}}, sort_keys=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def rows(self) -> list[LLMCall]:
        if not self.path.exists():
            return []
        out: list[LLMCall] = []
        for raw in self.path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                out.append(LLMCall(**json.loads(raw)))
            except (ValueError, TypeError) as exc:
                # A torn final line means the process died mid-append. Skipping
                # it under-reports one call; raising would refuse to run at all.
                log.warning("skipping unreadable spend row: %s", exc)
        return out

    # ------------------------------------------------------------ queries
    def total_for_day(self, day: date) -> float:
        return round(sum(c.cost_usd for c in self.rows() if c.day == day), 6)

    def total_for_run(self, run_id: str) -> float:
        """`runs.token_cost` for T3."""
        return round(sum(c.cost_usd for c in self.rows() if c.run_id == run_id), 6)

    def by_agent(self, day: date | None = None) -> dict[str, float]:
        return self._group(lambda c: c.agent, day)

    def by_model(self, day: date | None = None) -> dict[str, float]:
        """Grouped by the model that ACTUALLY served, not the one requested —
        that is the one you were billed for."""
        return self._group(lambda c: c.model_served, day)

    def _group(
        self, key: Callable[[LLMCall], str], day: date | None
    ) -> dict[str, float]:
        totals: dict[str, float] = defaultdict(float)
        for call in self.rows():
            if day is None or call.day == day:
                totals[key(call)] += call.cost_usd
        return {k: round(v, 6) for k, v in sorted(totals.items())}
