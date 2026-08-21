"""The LLM gateway and the spend ledger.

No network. The gateway takes an injected `completion_fn`, and the one test
that exercises litellm's real cost calculation does so on a synthetic
`ModelResponse` — measured: `completion_cost` works entirely offline.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from desk.llm import (
    AGENT_TIERS,
    CHEAP,
    EXPENSIVE,
    TIER_MODELS,
    BudgetExceeded,
    LLMGateway,
    UnknownAgent,
    enable_langfuse_if_configured,
)
from desk.spend import LLMCall, SpendLedger, utc_now_iso

TODAY = date(2026, 8, 20)
NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)


class FakeUsage:
    def __init__(self, p: int, c: int) -> None:
        self.prompt_tokens, self.completion_tokens = p, c


class FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = FakeMessage(content)


class FakeResponse:
    def __init__(self, model: str, content: str = "ok", p: int = 100, c: int = 50) -> None:
        self.model, self.choices, self.usage = model, [FakeChoice(content)], FakeUsage(p, c)


def make_gateway(tmp_path: Path, cost: float = 0.01, **kw: Any) -> LLMGateway:
    served = kw.pop("served_model", None)
    calls: list[dict[str, Any]] = kw.pop("record_calls", [])

    def fake_completion(**kwargs: Any) -> FakeResponse:
        calls.append(kwargs)
        return FakeResponse(served or kwargs["model"])

    kw.setdefault("completion_fn", fake_completion)
    kw.setdefault("cost_fn", lambda _r: cost)
    kw.setdefault("now", lambda: NOW)
    return LLMGateway(ledger=SpendLedger(tmp_path / "spend.jsonl"), **kw)


# ================================================================== tiering
def test_all_fourteen_agents_have_a_tier() -> None:
    assert len(AGENT_TIERS) == 14, "DESK_DESIGN §1 W2 counts 14 agents"
    assert set(AGENT_TIERS.values()) == {CHEAP, EXPENSIVE}


def test_analysts_are_cheap_and_the_verdict_is_expensive() -> None:
    """DESK_DESIGN §5: 'Use the cheap model for analysts, the expensive one
    only for debate, research manager, and verdict.'"""
    for analyst in ("technical", "fundamentals", "estimates", "news_sentiment",
                    "flow_ownership", "options", "macro"):
        assert AGENT_TIERS[analyst] == CHEAP, f"{analyst} should be on the cheap tier"
    for pricey in ("bull_researcher", "bear_researcher", "research_manager", "fund_manager"):
        assert AGENT_TIERS[pricey] == EXPENSIVE


def test_unknown_agent_is_refused_not_defaulted(tmp_path: Path) -> None:
    """Either default is silently wrong: cheap downgrades a verdict agent,
    expensive multiplies the bill."""
    gw = make_gateway(tmp_path)
    with pytest.raises(UnknownAgent):
        gw.complete(agent="typo_analyst", messages=[], workflow="W2", run_id="r1")


def test_cheap_tier_really_is_cheaper() -> None:
    import litellm

    cheap = sum(litellm.cost_per_token(model=TIER_MODELS[CHEAP], prompt_tokens=1000,
                                       completion_tokens=500))
    exp = sum(litellm.cost_per_token(model=TIER_MODELS[EXPENSIVE], prompt_tokens=1000,
                                     completion_tokens=500))
    assert cheap < exp, "the cheap tier is not actually cheaper"


def test_configured_models_are_priceable_by_litellm() -> None:
    """An unpriceable model raises from the COST path, not the call path — so
    without this the committee would make a real, billed request and only then
    fail while recording what it cost."""
    import litellm

    for tier, model in TIER_MODELS.items():
        litellm.cost_per_token(model=model, prompt_tokens=1, completion_tokens=1), tier


def test_unpriceable_model_is_rejected_at_construction(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cannot price"):
        LLMGateway(
            ledger=SpendLedger(tmp_path / "s.jsonl"),
            tier_models={CHEAP: "not-a-real-model-xyz", EXPENSIVE: "claude-opus-5"},
        )


# ================================================================ spend log
def test_every_call_lands_in_the_spend_log(tmp_path: Path) -> None:
    """T2 Done: 'every LLM call appears in LiteLLM's spend log.'"""
    gw = make_gateway(tmp_path, cost=0.02)
    for agent in ("technical", "fundamentals", "fund_manager"):
        gw.complete(agent=agent, messages=[{"role": "user", "content": "x"}],
                    workflow="W2", run_id="run-1")
    rows = SpendLedger(tmp_path / "spend.jsonl").rows()
    assert len(rows) == 3
    assert {r.agent for r in rows} == {"technical", "fundamentals", "fund_manager"}
    assert all(r.run_id == "run-1" and r.workflow == "W2" for r in rows)
    assert all(r.prompt_tokens == 100 and r.completion_tokens == 50 for r in rows)


def test_total_for_run_is_the_runs_token_cost_handoff(tmp_path: Path) -> None:
    """DESK_DESIGN §4's `runs.token_cost` is a SUM over this ledger — one row
    per run cannot hold per-agent, per-model cost for a 16-call committee."""
    gw = make_gateway(tmp_path, cost=0.05)
    for agent in ("technical", "macro", "trader"):
        gw.complete(agent=agent, messages=[], workflow="W2", run_id="run-A")
    gw.complete(agent="technical", messages=[], workflow="W1", run_id="run-B")
    ledger = SpendLedger(tmp_path / "spend.jsonl")
    assert ledger.total_for_run("run-A") == pytest.approx(0.15)
    assert ledger.total_for_run("run-B") == pytest.approx(0.05)


def test_cost_is_grouped_by_the_model_that_actually_served(tmp_path: Path) -> None:
    gw = make_gateway(tmp_path, cost=0.03, served_model="claude-opus-5")
    gw.complete(agent="technical", messages=[], workflow="W2", run_id="r")
    by_model = SpendLedger(tmp_path / "spend.jsonl").by_model()
    assert by_model == {"claude-opus-5": 0.03}, "billed against the served model"


def test_by_agent_breakdown(tmp_path: Path) -> None:
    gw = make_gateway(tmp_path, cost=0.01)
    gw.complete(agent="technical", messages=[], workflow="W2", run_id="r")
    gw.complete(agent="technical", messages=[], workflow="W2", run_id="r")
    gw.complete(agent="macro", messages=[], workflow="W2", run_id="r")
    assert SpendLedger(tmp_path / "spend.jsonl").by_agent() == {
        "macro": 0.01, "technical": 0.02,
    }


# =================================================================== budget
def test_ceiling_hard_stops(tmp_path: Path) -> None:
    """DESK_DESIGN §5: 'set a daily ceiling that hard-stops the cron.'"""
    gw = make_gateway(tmp_path, cost=0.30, daily_ceiling_usd=1.00)
    for _ in range(4):
        gw.complete(agent="technical", messages=[], workflow="W2", run_id="r")
    assert gw.spent_today() == pytest.approx(1.20)
    with pytest.raises(BudgetExceeded, match="daily ceiling"):
        gw.complete(agent="technical", messages=[], workflow="W2", run_id="r")


def test_budget_does_not_degrade_to_a_cheaper_model(tmp_path: Path) -> None:
    """Degrading would keep spending money the operator said not to spend, and
    would silently change which model produced a verdict."""
    gw = make_gateway(tmp_path, cost=2.00, daily_ceiling_usd=1.00)
    gw.complete(agent="fund_manager", messages=[], workflow="W2", run_id="r")
    with pytest.raises(BudgetExceeded):
        gw.complete(agent="fund_manager", messages=[], workflow="W2", run_id="r")
    rows = SpendLedger(tmp_path / "spend.jsonl").rows()
    assert len(rows) == 1, "a refused call must not be billed"


def test_yesterdays_spend_does_not_count_against_today(tmp_path: Path) -> None:
    ledger = SpendLedger(tmp_path / "spend.jsonl")
    yesterday = (TODAY - timedelta(days=1)).isoformat() + "T12:00:00+00:00"
    ledger.record(LLMCall(yesterday, "W2", "old", "technical", CHEAP,
                          "m", "m", 1, 1, 99.0, 10))
    gw = make_gateway(tmp_path, cost=0.01, daily_ceiling_usd=1.00)
    assert gw.spent_today() == 0.0
    gw.complete(agent="technical", messages=[], workflow="W2", run_id="r")


def test_remaining_budget_is_reported(tmp_path: Path) -> None:
    gw = make_gateway(tmp_path, cost=0.25, daily_ceiling_usd=1.00)
    gw.complete(agent="technical", messages=[], workflow="W2", run_id="r")
    assert gw.remaining_today() == pytest.approx(0.75)


# ================================================================= reroute
def test_model_reroute_is_recorded_and_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """T14: 'Fable's safeguards route some queries to Opus 5, and you want that
    visible rather than assumed.'"""
    gw = make_gateway(tmp_path, served_model="claude-opus-5")
    with caplog.at_level(logging.WARNING):
        got = gw.complete(agent="technical", messages=[], workflow="W2", run_id="r")
    assert got.call.model_requested == TIER_MODELS[CHEAP]
    assert got.call.model_served == "claude-opus-5"
    assert got.call.rerouted is True
    assert "MODEL REROUTE" in caplog.text


def test_provider_prefix_is_not_a_reroute(tmp_path: Path) -> None:
    """`anthropic/claude-opus-5` and `claude-opus-5` are the same model —
    flagging that as a reroute would cry wolf on every call."""
    gw = make_gateway(tmp_path, served_model=f"anthropic/{TIER_MODELS[CHEAP]}")
    got = gw.complete(agent="technical", messages=[], workflow="W2", run_id="r")
    assert got.call.rerouted is False


# =============================================================== cost path
def test_real_litellm_cost_calculation_offline(tmp_path: Path) -> None:
    """Uses litellm's ACTUAL cost function on a synthetic response, so the
    integration is exercised without a network call or an API key."""
    import litellm
    from litellm.types.utils import Choices, Message, ModelResponse, Usage

    response = ModelResponse(
        id="x",
        choices=[Choices(index=0, message=Message(role="assistant", content="hi"),
                         finish_reason="stop")],
        created=0, model=TIER_MODELS[EXPENSIVE], object="chat.completion",
        usage=Usage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500),
    )
    gw = LLMGateway(
        ledger=SpendLedger(tmp_path / "spend.jsonl"),
        completion_fn=lambda **_kw: response,
        now=lambda: NOW,
        daily_ceiling_usd=10.0,
    )
    got = gw.complete(agent="fund_manager", messages=[], workflow="W2", run_id="r")
    expected = sum(litellm.cost_per_token(model=TIER_MODELS[EXPENSIVE],
                                          prompt_tokens=1000, completion_tokens=500))
    assert got.call.cost_usd == pytest.approx(expected, rel=1e-6)
    assert got.call.cost_usd > 0


def test_uncomputable_cost_is_zero_and_loudly_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Recorded as 0.0 so the run survives, but ERROR-logged because the
    ceiling cannot see spend it could not price."""
    def boom(_r: Any) -> float:
        raise RuntimeError("no pricing")

    gw = LLMGateway(
        ledger=SpendLedger(tmp_path / "spend.jsonl"),
        completion_fn=lambda **kw: FakeResponse(kw["model"]),
        cost_fn=boom, now=lambda: NOW, validate_models=False,
    )
    with caplog.at_level(logging.ERROR):
        got = gw.complete(agent="technical", messages=[], workflow="W2", run_id="r")

    assert got.call.cost_usd == 0.0
    assert "COST UNKNOWN" in caplog.text
    # The call still lands in the ledger. A call that happened and was not
    # recorded is worse than one recorded at an unknown price.
    assert len(SpendLedger(tmp_path / "spend.jsonl").rows()) == 1


# =================================================================== ledger
def test_torn_final_line_is_tolerated(tmp_path: Path) -> None:
    """A process killed mid-append must not take the next run down with it."""
    path = tmp_path / "spend.jsonl"
    ledger = SpendLedger(path)
    ledger.record(LLMCall(utc_now_iso(), "W2", "r", "technical", CHEAP, "m", "m", 1, 1, 0.5, 1))
    with path.open("a") as fh:
        fh.write('{"ts": "2026-08-20T00:00:00+00:00", "workflow": "W2"')  # truncated
    rows = ledger.rows()
    assert len(rows) == 1
    assert rows[0].cost_usd == 0.5


def test_ledger_rows_are_plain_json(tmp_path: Path) -> None:
    ledger = SpendLedger(tmp_path / "spend.jsonl")
    ledger.record(LLMCall(utc_now_iso(), "W2", "r", "technical", CHEAP, "m", "m", 1, 1, 0.5, 1))
    for line in (tmp_path / "spend.jsonl").read_text().splitlines():
        json.loads(line)


# ================================================================= langfuse
def test_langfuse_is_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tracing must never be a hard dependency of a committee run."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert enable_langfuse_if_configured() is False


def test_langfuse_registers_callbacks_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import litellm

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setattr(litellm, "success_callback", [], raising=False)
    monkeypatch.setattr(litellm, "failure_callback", [], raising=False)
    assert enable_langfuse_if_configured() is True
    assert "langfuse" in litellm.success_callback
    assert "langfuse" in litellm.failure_callback


# ================================================================ hermetic
def test_litellm_price_map_is_pinned_local_not_fetched() -> None:
    """litellm FETCHES its model-price map over the network at import unless
    this is set. Measured: first suite run 59.6s, subsequent 5.8s — the shape
    of a one-time remote fetch.

    Beyond test hermeticity, this is a correctness property: a spend ceiling
    computed from prices pulled off the internet can move between runs with no
    code change. Prices travel with the litellm pin in requirements.lock.
    """
    import os

    assert os.environ.get("LITELLM_LOCAL_MODEL_COST_MAP") == "True", (
        "tests/conftest.py should have pinned litellm to its bundled price map"
    )


def test_both_tier_models_are_priced_by_the_local_map() -> None:
    """The bundled map is smaller than the remote one (2,982 vs 3,110 entries
    when measured). Pinning is only safe if OUR models are in the bundled copy."""
    import litellm

    for tier, model in TIER_MODELS.items():
        prompt, completion = litellm.cost_per_token(
            model=model, prompt_tokens=1000, completion_tokens=500
        )
        assert prompt > 0 and completion > 0, f"{tier}={model} not priced locally"
