"""T7 stage A — the LLM bridge, the verdict contract, the quality gate, and
run persistence. Everything except the graph wiring itself.

No network, no API key. The bridge is driven by an injected completion_fn.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from pydantic import ValidationError

from desk.db import init_db
from desk.llm import BudgetExceeded, LLMGateway
from desk.llm_bridge import DeskChatModel, for_agent, to_payload
from desk.quality_gate import MIN_CHARS, grade, grade_all, rejected
from desk.runs import finish_run, record_agent_output, record_verdict, start_run
from desk.spend import SpendLedger
from desk.verdict import Action, Verdict

GOOD_REPORT = (
    "RSI 62.4, VWAP +0.8 sigma, SMA200 sloping up. Price is 191.20 against a "
    "3-month change of +14.2%. DMI confirms trend. YTD +31%."
)


# ============================================================== the bridge
class FakeResponse:
    def __init__(self, content: str = "ok", tool_calls: Any = None,
                 model: str = "claude-haiku-4-5-20251001") -> None:
        self.model = model
        self.usage = type("U", (), {"prompt_tokens": 10, "completion_tokens": 5})()
        message = type("M", (), {"content": content, "tool_calls": tool_calls})()
        self.choices = [type("C", (), {"message": message})()]


def make_model(tmp_path: Path, response: Any = None, **kw: Any) -> DeskChatModel:
    seen: list[dict[str, Any]] = kw.pop("seen", [])

    def completion_fn(**kwargs: Any) -> Any:
        seen.append(kwargs)
        return response or FakeResponse()

    gateway = LLMGateway(
        ledger=SpendLedger(tmp_path / "spend.jsonl"),
        completion_fn=completion_fn,
        cost_fn=lambda _r: 0.001,
        validate_models=False,
        **kw,
    )
    return for_agent(gateway, "technical", "W2", "run-1")


def test_every_bridged_call_lands_in_the_spend_ledger(tmp_path: Path) -> None:
    """The reason this adapter exists instead of the engine's own LLM clients:
    those would bypass the budget entirely."""
    model = make_model(tmp_path)
    model.invoke([HumanMessage(content="hi")])
    model.invoke([HumanMessage(content="again")])
    rows = SpendLedger(tmp_path / "spend.jsonl").rows()
    assert len(rows) == 2
    assert all(r.agent == "technical" and r.run_id == "run-1" for r in rows)


def test_bridge_respects_the_daily_ceiling(tmp_path: Path) -> None:
    """A committee that could not be stopped by the ceiling would make the
    ceiling decorative."""
    # $0.001 a call against a $0.0015 ceiling: the first two are each under
    # the limit at the moment they are checked; the third is not.
    model = make_model(tmp_path, daily_ceiling_usd=0.0015)
    model.invoke([HumanMessage(content="one")])
    model.invoke([HumanMessage(content="two")])
    with pytest.raises(BudgetExceeded):
        model.invoke([HumanMessage(content="three")])


def test_response_metadata_carries_provenance(tmp_path: Path) -> None:
    model = make_model(tmp_path, response=FakeResponse(model="claude-opus-5"))
    out = model.invoke([HumanMessage(content="hi")])
    assert out.response_metadata["model_served"] == "claude-opus-5"
    assert out.response_metadata["rerouted"] is True, "a reroute must surface"
    assert out.response_metadata["cost_usd"] == 0.001


def test_message_roles_are_translated(tmp_path: Path) -> None:
    payload = to_payload([
        SystemMessage(content="sys"),
        HumanMessage(content="user"),
        AIMessage(content="assistant"),
        ToolMessage(content="tool result", tool_call_id="abc"),
    ])
    assert [m["role"] for m in payload] == ["system", "user", "assistant", "tool"]
    assert payload[3]["tool_call_id"] == "abc"


def test_bind_tools_is_supported(tmp_path: Path) -> None:
    """BaseChatModel's default raises NotImplementedError, and EVERY analyst
    node in the engine calls bind_tools — so without this they all die on
    construction."""
    @tool
    def get_price(ticker: str) -> float:
        """Return the last price."""
        return 1.0

    seen: list[dict[str, Any]] = []
    model = make_model(tmp_path, seen=seen).bind_tools([get_price])
    model.invoke([HumanMessage(content="price?")])
    assert "tools" in seen[0]
    assert seen[0]["tools"][0]["function"]["name"] == "get_price"


def test_bind_tools_does_not_mutate_the_original(tmp_path: Path) -> None:
    @tool
    def noop(x: str) -> str:
        """Do nothing."""
        return x

    model = make_model(tmp_path)
    bound = model.bind_tools([noop])
    assert model.bound_tools == [], "bind_tools must not mutate the original"
    assert len(bound.bound_tools) == 1


def test_tool_calls_are_recovered_from_the_raw_response(tmp_path: Path) -> None:
    call = type("TC", (), {
        "id": "call_1",
        "function": type("F", (), {"name": "get_price", "arguments": '{"ticker": "NVDA"}'})(),
    })()
    model = make_model(tmp_path, response=FakeResponse(content="", tool_calls=[call]))
    out = model.invoke([HumanMessage(content="price?")])
    assert out.tool_calls[0]["name"] == "get_price"
    assert out.tool_calls[0]["args"] == {"ticker": "NVDA"}


def test_malformed_tool_arguments_do_not_raise(tmp_path: Path) -> None:
    """A model emitting bad JSON should fail in the node that inspects the
    call, where the agent name is known — not deep inside the adapter."""
    call = type("TC", (), {
        "id": "c", "function": type("F", (), {"name": "f", "arguments": "{not json"})(),
    })()
    model = make_model(tmp_path, response=FakeResponse(tool_calls=[call]))
    out = model.invoke([HumanMessage(content="x")])
    assert out.tool_calls[0]["args"] == {}


def test_no_tool_calls_is_an_empty_list(tmp_path: Path) -> None:
    out = make_model(tmp_path).invoke([HumanMessage(content="x")])
    assert out.tool_calls == []


# ============================================================== the verdict
def test_verdict_renders_like_the_design_example() -> None:
    """DESK_DESIGN §1 W2 observed: `HOLD / ACCUMULATE $191–196 · conviction 7/10`."""
    v = Verdict(ticker="nvda", action=Action.ACCUMULATE, price_low=191, price_high=196,
                conviction=7, rationale="thesis intact")
    assert v.ticker == "NVDA"
    assert v.render() == "ACCUMULATE $191–196 · conviction 7/10"


@pytest.mark.parametrize("conviction", [0, 11, -1])
def test_conviction_outside_one_to_ten_is_refused(conviction: int) -> None:
    """T7 says 1-10. The failure mode for an LLM field is a confident,
    well-formatted, out-of-range number."""
    with pytest.raises(ValidationError):
        Verdict(ticker="X", action=Action.HOLD, conviction=conviction, rationale="r")


def test_inverted_price_range_is_refused() -> None:
    with pytest.raises(ValidationError, match="inverted"):
        Verdict(ticker="X", action=Action.HOLD, price_low=200, price_high=190,
                conviction=5, rationale="r")


def test_half_a_price_range_is_refused() -> None:
    with pytest.raises(ValidationError, match="both bounds or neither"):
        Verdict(ticker="X", action=Action.HOLD, price_low=200, conviction=5, rationale="r")


def test_empty_rationale_is_refused() -> None:
    with pytest.raises(ValidationError):
        Verdict(ticker="X", action=Action.HOLD, conviction=5, rationale="")


def test_verdict_carries_no_order_fields() -> None:
    """D5 is structural. The verdict schema is where an order would first
    leak in, so assert it cannot."""
    for forbidden in ("quantity", "size", "venue", "order_type", "broker", "shares"):
        assert forbidden not in Verdict.model_fields


# =========================================================== quality gate
def test_good_report_passes() -> None:
    assert grade("technical", GOOD_REPORT).passed


@pytest.mark.parametrize("text", [
    "I cannot retrieve the data for this ticker at the moment, apologies.",
    "Unable to fetch fundamentals for NVDA right now, please try again later.",
    "As an AI language model, I do not have access to real-time market data.",
])
def test_llm_failure_markers_are_rejected(text: str) -> None:
    """An analyst that returns 'I'm unable to retrieve that' is not a bearish
    signal, but a debate node reading it as prose will argue from it."""
    result = grade("fundamentals", text)
    assert not result.passed
    assert "failure marker" in result.reason


def test_empty_and_whitespace_are_rejected() -> None:
    assert not grade("macro", None).passed
    assert not grade("macro", "   \n  ").passed


def test_short_report_is_rejected() -> None:
    result = grade("options", "Looks fine. 42")
    assert not result.passed and "too short" in result.reason


def test_report_with_no_numbers_is_rejected() -> None:
    text = "The technical picture appears constructive and the trend seems favourable " \
           "with supportive momentum and generally positive breadth across the sector."
    assert len(text) > MIN_CHARS
    result = grade("technical", text)
    assert not result.passed and "numeric" in result.reason


def test_grade_all_and_rejected() -> None:
    grades = grade_all({"technical": GOOD_REPORT, "macro": "", "options": None})
    assert grades["technical"].passed
    assert set(rejected(grades)) == {"macro", "options"}


def test_grade_is_falsey_when_rejected() -> None:
    assert not grade("x", "")
    assert grade("x", GOOD_REPORT)


# ============================================================ persistence
@pytest.fixture
def conn(tmp_path: Path) -> Any:
    return init_db(tmp_path / "desk.db")


def test_every_agent_output_is_persisted(conn: Any) -> None:
    """§4: "Without agent_outputs you cannot debug a bad verdict, and you will
    get bad verdicts.\""""
    run_id = start_run(conn, "W2", "NVDA")
    for agent in ("technical", "fundamentals", "macro"):
        record_agent_output(conn, run_id, agent, {"report": GOOD_REPORT}, latency_ms=120)
    rows = conn.execute("SELECT agent, payload_json FROM agent_outputs").fetchall()
    assert len(rows) == 3
    assert json.loads(rows[0]["payload_json"])["report"] == GOOD_REPORT


def test_rejected_reports_are_persisted_too(conn: Any) -> None:
    """The report the gate threw away is exactly the one you need when
    debugging why the verdict was wrong."""
    run_id = start_run(conn, "W2", "NVDA")
    bad = "I cannot retrieve the data."
    record_agent_output(conn, run_id, "news", {"report": bad, "grade": "rejected"})
    stored = conn.execute("SELECT payload_json FROM agent_outputs").fetchone()
    assert "cannot retrieve" in stored["payload_json"]


def test_verdict_is_persisted(conn: Any) -> None:
    run_id = start_run(conn, "W2", "NVDA")
    record_verdict(conn, run_id, Verdict(
        ticker="NVDA", action=Action.ACCUMULATE, price_low=191, price_high=196,
        conviction=7, rationale="thesis intact"))
    row = conn.execute("SELECT * FROM verdicts").fetchone()
    assert row["action"] == "ACCUMULATE" and row["conviction"] == 7


def test_finish_run_stamps_cost_from_the_t2_ledger(conn: Any, tmp_path: Path) -> None:
    """T3 defined the handoff; T7 executes it:
    runs.token_cost == SpendLedger.total_for_run(run_id)."""
    run_id = start_run(conn, "W2", "NVDA")
    model = make_model(tmp_path)
    bound = for_agent(model.gateway, "technical", "W2", run_id)
    bound.invoke([HumanMessage(content="a")])
    bound.invoke([HumanMessage(content="b")])

    ledger = SpendLedger(tmp_path / "spend.jsonl")
    cost = finish_run(conn, run_id, ledger, model="claude-haiku-4-5-20251001")
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (int(run_id),)).fetchone()
    assert cost == pytest.approx(0.002)
    assert row["token_cost"] == pytest.approx(ledger.total_for_run(run_id))
    assert row["status"] == "DONE" and row["finished_at"] is not None


def test_agent_output_requires_a_real_run(conn: Any) -> None:
    """The FK from T3 is load-bearing: an output with no run is undebuggable."""
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        record_agent_output(conn, "9999", "technical", {"r": "x"})
