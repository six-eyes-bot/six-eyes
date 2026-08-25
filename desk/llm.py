"""The LLM gateway — every agent call goes through here.

THE POINT OF THIS TICKET (T2): routing all 14 agents through one gateway buys
per-call cost tracking, a spend cap, provider fallback and a single Langfuse
integration point, instead of instrumenting fourteen agents individually. It
collapses most of T14 into configuration.

SDK, NOT PROXY
--------------
LiteLLM ships both a Python SDK and a proxy server. This uses the SDK.
DESK_DESIGN's target is "a self-hosted, cron-driven AI investment committee";
Hermes already owns orchestration, and nothing else in the design runs a
long-lived daemon. A proxy would add one more service to operate, monitor and
restart for benefits we would then have to re-implement anyway — the ceiling
must "hard-stop the cron", which is a process-level decision the calling
process has to make, not something a remote proxy can do for it.

MEASURED, 2026-08-20 (litellm 1.97.0)
-------------------------------------
  import litellm                      2.71 s   -> imported lazily, see below
  cost of a 6000/1200 cheap call      $0.0120
  cost of a 6000/1200 expensive call  $0.0600
  one 16-call committee run           ~$0.62
  three workflows a day               ~$1.87
  thirty days                         ~$56

Worth stating plainly: at ~$56/month the token bill is roughly **three times**
the $19/month FMP data subscription that ADR 0001 spent a whole audit round on.
The default ceiling of $5/day is ~2.7x expected daily spend.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from desk.spend import LLMCall, SpendLedger

log = logging.getLogger(__name__)

CHEAP = "cheap"
EXPENSIVE = "expensive"

#: DESK_DESIGN §5: "Use the cheap model for analysts, the expensive one only
#: for debate, research manager, and verdict."
TIER_MODELS: dict[str, str] = {
    CHEAP: "claude-haiku-4-5-20251001",
    EXPENSIVE: "claude-opus-5",
}

#: The 14 agents of DESK_DESIGN §1 W2, each pinned to a tier.
AGENT_TIERS: dict[str, str] = {
    # 7 analysts -- cheap
    "technical": CHEAP,
    "fundamentals": CHEAP,
    "estimates": CHEAP,
    "news_sentiment": CHEAP,
    "flow_ownership": CHEAP,
    "options": CHEAP,
    "macro": CHEAP,
    # debate, synthesis, execution, control, verdict -- expensive
    "bull_researcher": EXPENSIVE,
    "bear_researcher": EXPENSIVE,
    "research_manager": EXPENSIVE,
    "trader": EXPENSIVE,
    "risk_manager": EXPENSIVE,
    "fund_manager": EXPENSIVE,
    # the orchestrator's own summarisation
    "orchestrator": CHEAP,
}

DEFAULT_DAILY_CEILING_USD = 5.00


class BudgetExceeded(RuntimeError):
    """The daily ceiling is spent. Raised so the cron HARD-STOPS.

    DESK_DESIGN §5: "set a daily ceiling that hard-stops the cron". Degrading
    to a cheaper model instead would keep spending money the operator said not
    to spend, and would silently change which model produced a verdict.
    """


class UnknownAgent(KeyError):
    """An agent with no tier. Refused rather than defaulted.

    Defaulting an unknown agent to the cheap tier would silently downgrade a
    verdict-producing agent someone forgot to register; defaulting it to the
    expensive tier would silently multiply the bill.
    """


@dataclass(frozen=True)
class Completion:
    """What a caller gets back. Carries the ledger row so the caller can see
    what it cost without going back to disk."""

    content: str
    call: LLMCall
    #: The provider's raw response. Needed by desk/llm_bridge.py to recover
    #: tool calls, which `content` alone cannot carry. Deliberately last and
    #: defaulted so existing callers are untouched.
    raw: Any = None


class LLMGateway:
    def __init__(
        self,
        ledger: SpendLedger,
        daily_ceiling_usd: float = DEFAULT_DAILY_CEILING_USD,
        completion_fn: Callable[..., Any] | None = None,
        cost_fn: Callable[..., float] | None = None,
        tier_models: Mapping[str, str] | None = None,
        agent_tiers: Mapping[str, str] | None = None,
        fallbacks: Sequence[str] | None = None,
        now: Callable[[], datetime] | None = None,
        validate_models: bool = True,
    ) -> None:
        self._ledger = ledger
        self._ceiling = float(daily_ceiling_usd)
        self._completion_fn = completion_fn
        self._cost_fn = cost_fn
        self._tier_models = dict(tier_models or TIER_MODELS)
        self._agent_tiers = dict(agent_tiers or AGENT_TIERS)
        self._fallbacks = list(fallbacks or ())
        # ONE clock. An earlier version stamped ledger rows with real UTC now
        # while asking an injected `today` for the budget window, so the two
        # could disagree -- and a budget that reads a different day than the
        # ledger writes is a ceiling that does not hold.
        self._now = now or (lambda: datetime.now(UTC))
        if validate_models and completion_fn is None:
            self._validate_models()

    # ------------------------------------------------------------- lazy load
    @staticmethod
    def _litellm() -> Any:
        """Imported lazily: `import litellm` measured 2.71s, and neither the
        test suite nor a data-only run should pay that.

        LITELLM_LOCAL_MODEL_COST_MAP is set first, deliberately. By default
        litellm FETCHES its model-price map over the network at import,
        falling back to a bundled copy. For a component whose whole job is
        enforcing a spend ceiling, prices that can change between runs without
        a code change are an integrity problem, not a convenience — the same
        reason every dependency here is hash-pinned and the engine is vendored
        at a SHA. Refreshing prices should be a deliberate act: upgrade
        litellm, and the bundled map moves with it under the lockfile.
        """
        os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
        import litellm

        return litellm

    def _validate_models(self) -> None:
        """Fail at construction, not at the first call.

        Measured: an unpriceable model name (e.g. `claude-3-5-haiku-20241022`
        with no provider prefix) raises from the COST path, not the call path
        — so without this the committee would make a real, billed request and
        only then blow up while trying to record what it cost.
        """
        litellm = self._litellm()
        bad = []
        for tier, model in self._tier_models.items():
            try:
                litellm.cost_per_token(model=model, prompt_tokens=1, completion_tokens=1)
            except Exception as exc:  # noqa: BLE001 - litellm raises broadly
                bad.append(f"{tier}={model!r} ({type(exc).__name__})")
        if bad:
            raise ValueError(
                "litellm cannot price these models, so spend could not be "
                f"tracked for them: {bad}. Use a name litellm knows, or prefix "
                "the provider (e.g. 'anthropic/<model>')."
            )

    # --------------------------------------------------------------- budget
    def today(self) -> date:
        return self._now().date()

    def spent_today(self) -> float:
        return self._ledger.total_for_day(self.today())

    def remaining_today(self) -> float:
        return round(max(0.0, self._ceiling - self.spent_today()), 6)

    def _check_budget(self, agent: str) -> None:
        spent = self.spent_today()
        if spent >= self._ceiling:
            raise BudgetExceeded(
                f"daily ceiling ${self._ceiling:.2f} reached (spent "
                f"${spent:.4f}) — refusing to call {agent}. The ceiling is "
                "enforced per call, so the last call may overshoot it by one "
                "call's cost; it cannot overshoot repeatedly."
            )

    # ----------------------------------------------------------------- call
    def model_for(self, agent: str) -> str:
        try:
            tier = self._agent_tiers[agent]
        except KeyError as exc:
            raise UnknownAgent(
                f"{agent!r} has no tier. Register it in AGENT_TIERS — an "
                "unknown agent is refused rather than defaulted, because "
                "either default is silently wrong."
            ) from exc
        return self._tier_models[tier]

    def complete(
        self,
        *,
        agent: str,
        messages: Sequence[Mapping[str, str]],
        workflow: str,
        run_id: str,
        **kwargs: Any,
    ) -> Completion:
        model = self.model_for(agent)
        tier = self._agent_tiers[agent]
        self._check_budget(agent)

        started = time.monotonic()
        response = self._invoke(model=model, messages=list(messages), **kwargs)
        latency_ms = int((time.monotonic() - started) * 1000)

        served = str(getattr(response, "model", model) or model)
        usage = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        cost = self._cost_of(response)

        rerouted = _base_model(served) != _base_model(model)
        if rerouted:
            # T14: safeguards can route a query to a different model. Visible,
            # not assumed -- and it is billed at the OTHER model's rate.
            log.warning(
                "MODEL REROUTE: agent %s requested %r but %r served the call. "
                "Cost recorded against the served model.",
                agent, model, served,
            )

        call = LLMCall(
            ts=self._now().isoformat(),
            workflow=workflow,
            run_id=run_id,
            agent=agent,
            tier=tier,
            model_requested=model,
            model_served=served,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=round(float(cost), 6),
            latency_ms=latency_ms,
            rerouted=rerouted,
        )
        # Recorded BEFORE the content is handed back: a caller that raises
        # while processing the answer must not lose the fact that it was paid
        # for. Un-billed spend is the failure mode a ceiling cannot survive.
        self._ledger.record(call)
        return Completion(content=_content_of(response), call=call, raw=response)

    def _invoke(self, **kwargs: Any) -> Any:
        if self._completion_fn is not None:
            return self._completion_fn(**kwargs)
        litellm = self._litellm()
        if self._fallbacks:
            kwargs["fallbacks"] = self._fallbacks
        return litellm.completion(**kwargs)

    def _cost_of(self, response: Any) -> float:
        try:
            if self._cost_fn is not None:
                return float(self._cost_fn(response))
            return float(self._litellm().completion_cost(completion_response=response))
        except Exception as exc:  # noqa: BLE001
            # A cost we cannot compute is recorded as 0.0 and LOUDLY logged.
            # Silently dropping it would let the ceiling be bypassed by any
            # model litellm cannot price.
            log.error(
                "COST UNKNOWN for %s: %s. Recorded as $0.00 — the daily "
                "ceiling cannot see this spend.",
                getattr(response, "model", "?"), exc,
            )
            return 0.0


def _base_model(name: str) -> str:
    """`anthropic/claude-opus-5` and `claude-opus-5` are the same model."""
    return name.split("/")[-1].strip()


def _content_of(response: Any) -> str:
    try:
        return str(response.choices[0].message.content or "")
    except (AttributeError, IndexError, TypeError):
        return ""


def enable_langfuse_if_configured() -> bool:
    """Single integration point for tracing, per the ticket.

    Returns False and does nothing when the keys are absent — tracing must
    never be a hard dependency of a committee run.
    """
    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        log.info("Langfuse keys absent; tracing disabled")
        return False
    litellm = LLMGateway._litellm()
    for hook in ("success_callback", "failure_callback"):
        current = list(getattr(litellm, hook, []) or [])
        if "langfuse" not in current:
            setattr(litellm, hook, [*current, "langfuse"])
    log.info("Langfuse tracing enabled on litellm callbacks")
    return True
