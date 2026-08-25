"""T7 stage B — the 14-node committee graph.

No network, no API key: the gateway takes an injected `completion_fn` and the
market data is a fake driven by the recorded NVDA fixture.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, cast

import pandas as pd
import pytest

from desk.data import MarketData, Sourced
from desk.db import init_db
from desk.llm import LLMGateway
from desk.providers.base import ProviderUnavailable
from desk.runs import finish_run, record_agent_output, start_run
from desk.spend import SpendLedger
from desk.verdict import Action, Verdict

sys.path.insert(0, str(Path(__file__).parent.parent / "engine"))
from committee.graph import (  # noqa: E402
    ANALYSTS,
    COMMITTEE,
    Deps,
    build,
)

FIXTURES = Path(__file__).parent / "fixtures" / "recorded"
INFO = json.loads((FIXTURES / "nvda_info.json").read_text())
TODAY = date(2026, 8, 21)
GOOD = ("Reviewed: RSI 62.4, price 216.85, consensus target 240. Constructive "
        "setup with supportive breadth and a rising 200-day average.")


class FakeData:
    def __init__(self, fail: frozenset[str] = frozenset()) -> None:
        self.fail = fail

    def _guard(self, name: str) -> None:
        if name in self.fail:
            raise ProviderUnavailable(f"simulated {name} outage")

    def quote_scalars(self, t: str, fields: list[str], as_of: date) -> Sourced[Any]:
        self._guard("quote_scalars")
        return Sourced({f: float(INFO.get(f) or 1.0) for f in fields}, "yfinance", as_of)

    def estimates(self, t: str, as_of: date) -> Sourced[Any]:
        self._guard("estimates")
        return Sourced({"numberOfAnalystOpinions": 58.0, "recommendationMean": 1.6,
                        "targetMeanPrice": 240.0}, "yfinance", as_of)

    def option_chain(self, t: str, e: date | None, as_of: date) -> Sourced[Any]:
        self._guard("option_chain")
        return Sourced(pd.DataFrame({
            "strike": [215.0, 220.0], "impliedVolatility": [0.40, 0.42],
            "openInterest": [100.0, 50.0], "volume": [10.0, 5.0],
            "kind": ["call", "put"]}), "yfinance", as_of)

    def macro_series(self, sid: str, s: date, e: date) -> Sourced[Any]:
        self._guard("macro_series")
        return Sourced(pd.Series([20.0, 25.0], index=pd.to_datetime([s, e]), name=sid),
                       "fred", e)


class FakeResponse:
    def __init__(self, content: str = GOOD) -> None:
        self.model = "claude-haiku-4-5-20251001"
        self.usage = type("U", (), {"prompt_tokens": 50, "completion_tokens": 20})()
        message = type("M", (), {"content": content, "tool_calls": None})()
        self.choices = [type("C", (), {"message": message})()]


def make(
    tmp_path: Path, data: Any = None, content: str = GOOD, **kw: Any
) -> tuple[Any, Any, list[str]]:
    seen: list[str] = []
    ledger = SpendLedger(tmp_path / "spend.jsonl")
    gateway = LLMGateway(
        ledger=ledger, completion_fn=lambda **_k: FakeResponse(content),
        cost_fn=lambda _r: 0.001, validate_models=False, daily_ceiling_usd=5.0,
    )
    deps = Deps(
        # A deliberate partial double: the graph calls four of MarketData's
        # nine methods, and implementing the other five as `raise` would add
        # noise without adding a guarantee.
        data=cast(MarketData, data or FakeData()), gateway=gateway,
        news=kw.pop("news", lambda t, a: "3 headlines, net positive, 2 upgrades."),
        on_output=lambda agent, payload, ms: seen.append(agent),
    )
    return build(deps), ledger, seen


def run(graph: Any, **kw: Any) -> dict[str, Any]:
    return graph.invoke({"ticker": "NVDA", "as_of": TODAY, "run_id": "run-1",
                         "reports": {}, **kw})


# ================================================================ the shape
def test_committee_has_the_designs_fourteen_agents() -> None:
    """DESK_DESIGN §1 W2: 7 + 2 + 1 + 1 + 1 + 1 + 1 = 14."""
    assert len(COMMITTEE) == 14
    assert len(ANALYSTS) == 7
    assert len(set(COMMITTEE)) == 14, "a duplicate name would silently drop an agent"


def test_all_seven_analysts_produce_a_report(tmp_path: Path) -> None:
    graph, _, _ = make(tmp_path)
    final = run(graph)
    assert set(final["reports"]) == set(ANALYSTS)


def test_thirteen_agents_emit_output_the_fourteenth_is_the_graph(tmp_path: Path) -> None:
    """The orchestrator is the runner itself, so it has no node of its own."""
    graph, _, seen = make(tmp_path)
    run(graph)
    assert len(seen) == 13
    assert "orchestrator" not in seen


# ============================================================== the budget
def test_every_agent_call_lands_in_the_spend_ledger(tmp_path: Path) -> None:
    """The reason T7 bridges to desk/llm.py instead of adopting the engine's
    own LLM clients — those would bypass the ledger entirely."""
    graph, ledger, _ = make(tmp_path)
    run(graph)
    rows = ledger.rows()
    assert len(rows) == 13
    assert all(r.run_id == "run-1" for r in rows)
    assert ledger.total_for_run("run-1") == pytest.approx(0.013)


def test_analysts_are_cheap_and_the_verdict_is_expensive(tmp_path: Path) -> None:
    """DESK_DESIGN §5's tiering, observed through a whole committee run."""
    graph, ledger, _ = make(tmp_path)
    run(graph)
    by_agent = {r.agent: r.tier for r in ledger.rows()}
    for analyst in ANALYSTS:
        assert by_agent[analyst] == "cheap", f"{analyst} should be on the cheap tier"
    for pricey in ("bull_researcher", "bear_researcher", "research_manager", "fund_manager"):
        assert by_agent[pricey] == "expensive"


# ========================================================= the quality gate
def test_gate_rejects_a_failure_marker_and_the_debate_does_not_see_it(
    tmp_path: Path,
) -> None:
    """An analyst returning 'I cannot retrieve' is not a bearish signal, but a
    debate node reading it as prose would argue from it."""
    graph, _, _ = make(tmp_path, content="I cannot retrieve that data right now.")
    final = run(graph)
    bad = [a for a, g in final["grades"].items() if not g.passed]
    assert set(bad) == set(ANALYSTS), "every report was a failure marker"

    # The debate must not be FED the rejected reports. (It cannot be asserted
    # on the bull node's own output here: this fake makes every node emit the
    # same marker string, including the bull.)
    from committee.graph import CommitteeState, _accepted

    assert _accepted(cast(CommitteeState, final)) == "(none)"


def test_a_dead_provider_does_not_kill_the_run(tmp_path: Path) -> None:
    """One dead data source must degrade the report, not the committee."""
    graph, _, _ = make(tmp_path, data=FakeData(fail=frozenset({"option_chain"})))
    final = run(graph)
    assert "UNAVAILABLE" in final["reports"]["options"]
    assert final.get("verdict") is not None, "the run should still reach a verdict"


def test_missing_news_source_is_declared_not_invented(tmp_path: Path) -> None:
    graph, _, _ = make(tmp_path, news=None)
    final = run(graph)
    assert "UNAVAILABLE" in final["reports"]["news_sentiment"]


# ================================================================== verdict
def test_unparseable_verdict_falls_back_to_hold(tmp_path: Path) -> None:
    """The fake never returns a structured Verdict. The committee must not
    guess an action — HOLD at conviction 1 says 'we did not decide'."""
    graph, _, _ = make(tmp_path)
    verdict = run(graph)["verdict"]
    assert isinstance(verdict, Verdict)
    assert verdict.action is Action.HOLD
    assert verdict.conviction == 1
    assert "unparseable" in verdict.rationale


def test_graph_reaches_the_verdict_node(tmp_path: Path) -> None:
    graph, _, seen = make(tmp_path)
    run(graph)
    assert "fund_manager" == seen[-1], "the verdict must be the last word"


# ============================================================== persistence
def test_a_whole_run_persists_and_costs_out(tmp_path: Path) -> None:
    """The T3 -> T2 -> T7 handoff, end to end:
    runs.token_cost == SpendLedger.total_for_run(run_id)."""
    conn = init_db(tmp_path / "desk.db")
    run_id = start_run(conn, "W2", "NVDA")

    ledger = SpendLedger(tmp_path / "spend.jsonl")
    gateway = LLMGateway(ledger=ledger, completion_fn=lambda **_k: FakeResponse(),
                         cost_fn=lambda _r: 0.001, validate_models=False,
                         daily_ceiling_usd=5.0)
    graph = build(Deps(
        data=cast(MarketData, FakeData()), gateway=gateway,
        news=lambda t, a: "3 headlines, net positive, 2 upgrades.",
        on_output=lambda agent, payload, ms: record_agent_output(
            conn, run_id, agent, payload, ms),
    ))
    graph.invoke({"ticker": "NVDA", "as_of": TODAY, "run_id": run_id, "reports": {}})

    stored = conn.execute("SELECT agent FROM agent_outputs").fetchall()
    assert len(stored) == 13, "every agent output must be persisted"

    cost = finish_run(conn, run_id, ledger)
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (int(run_id),)).fetchone()
    assert row["token_cost"] == pytest.approx(cost)
    assert cost == pytest.approx(0.013)
    conn.close()


# =================================================== structural guarantees
def test_committee_never_imports_the_engines_llm_clients() -> None:
    """Those bypass the spend ledger AND pull back the 21 packages T6
    excluded.

    Parsed with `ast`, not grepped: the first version false-positived on this
    module's own docstring, which names `llm_clients` in order to explain why
    it is avoided. Third time this project has hit that — see T5's
    ticker_fundament check and T1's pandas-is-GPL bug. Prose about a thing is
    not the thing.
    """
    import ast

    tree = ast.parse(Path("engine/committee/graph.py").read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    for banned in ("llm_clients", "langchain_anthropic", "langchain_openai",
                   "langchain_google_genai"):
        assert not any(banned in m for m in imported), (
            f"committee graph imports {banned!r}: {sorted(imported)}"
        )


def test_committee_does_not_live_under_the_vendored_graph_package() -> None:
    """tradingagents/graph/__init__.py eagerly imports trading_graph, which
    needs both llm_clients and langgraph.checkpoint.sqlite."""
    assert not Path("engine/tradingagents/graph/desk_committee.py").exists()
    assert Path("engine/committee/graph.py").exists()


def test_the_committee_is_not_vendored() -> None:
    """First-party code inside engine/: absent from the manifest, so it is
    linted and typed. This is what invariant 8 protects."""
    manifest = Path("engine/.vendored-manifest").read_text()
    assert "engine/committee/graph.py" not in manifest
    assert "engine/committee/__init__.py" not in manifest


def test_no_order_is_ever_placed(tmp_path: Path) -> None:
    """D5 is structural. The trader node proposes; nothing executes."""
    source = Path("engine/committee/graph.py").read_text()
    for banned in ("place_order", "submit_order", "broker", "execute_trade"):
        assert banned not in source
    verdict = run(make(tmp_path)[0])["verdict"]
    assert not hasattr(verdict, "quantity")
