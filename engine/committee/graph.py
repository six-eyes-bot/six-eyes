"""The 14-node committee graph — DESK_DESIGN §1 W2.

COMPOSED BESIDE THE ENGINE, NEVER INSIDE IT
-------------------------------------------
`tradingagents/graph/setup.py` holds a hardcoded four-analyst factory dict, and
T1 predicted this ticket would want to edit it. It cannot: invariant 6 hashes
every vendored file against upstream, and `make vendor-manifest` re-fetches
from upstream, so no local edit to a vendored file can ever be blessed.
Verified — appending one comment to `setup.py` fails the invariant.

That is the design working, not fighting us. See this package's __init__ for
why the module lives here and nowhere else.

WHERE THE DATA COMES FROM (this closes M10)
-------------------------------------------
`internal-docs/SUPERSEDED.md` recorded "repointing engine/dataflows/ at
desk/data.py" as UNASSIGNED, to be decided before T6. T7 decides it:

  * `desk/data.py` serves six of the seven analysts — technical, fundamentals,
    estimates, flow/ownership, options, macro.
  * News/sentiment uses the engine's own `yfinance_news` dataflow, because our
    MarketData Protocol has no news method and adding one is a T2 change.
    Measured: that dataflow needs NO API key.

Both paths are yfinance underneath. This is one provider reached two ways, not
two providers — which is why it is acceptable rather than merely tolerated.

EVERY LLM CALL GOES THROUGH desk/llm.py
---------------------------------------
Via `desk.llm_bridge`. Not the engine's `llm_clients`, which would bypass the
spend ledger and the daily ceiling entirely. See the T7 stage A decision log.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Annotated, Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from tradingagents.agents.analysts import (
    estimates_analyst,
    flow_analyst,
    macro_analyst,
    options_analyst,
)
from tradingagents.agents.analysts._desk_base import AnalystReport, Metric, unavailable

from desk.data import MarketData
from desk.llm import LLMGateway
from desk.llm_bridge import for_agent
from desk.providers.base import ProviderError
from desk.quality_gate import Grade, grade_all, rejected
from desk.verdict import Action, Verdict

log = logging.getLogger(__name__)


def _merge(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Reducer so analyst nodes can run concurrently without clobbering."""
    return {**left, **right}


class CommitteeState(TypedDict, total=False):
    ticker: str
    as_of: date
    run_id: str
    reports: Annotated[dict[str, str], _merge]
    grades: dict[str, Grade]
    bull: str
    bear: str
    synthesis: str
    trade_plan: str
    risk_review: str
    verdict: Verdict


#: DESK_DESIGN §1 W2's count, named so the graph can assert it.
ANALYSTS = (
    "technical", "fundamentals", "news_sentiment",
    "estimates", "flow_ownership", "options", "macro",
)
DEBATE = ("bull_researcher", "bear_researcher")
DOWNSTREAM = ("research_manager", "trader", "risk_manager", "fund_manager")
#: The orchestrator is the graph runner itself — DESK_DESIGN counts it as the
#: 14th node ("Manual Trigger / orchestrator").
ORCHESTRATOR = "orchestrator"
COMMITTEE = (*ANALYSTS, *DEBATE, *DOWNSTREAM, ORCHESTRATOR)


@dataclass(frozen=True)
class Deps:
    """Everything the graph needs from outside. Injected, so the whole thing
    is testable with a fake gateway and a fake feed."""

    data: MarketData
    gateway: LLMGateway
    workflow: str = "W2"
    news: Callable[[str, date], str] | None = None
    on_output: Callable[[str, dict[str, Any], int], None] | None = None


def _record(deps: Deps, agent: str, payload: dict[str, Any], started: float) -> None:
    if deps.on_output is not None:
        deps.on_output(agent, payload, int((time.monotonic() - started) * 1000))


def _prose(deps: Deps, state: CommitteeState, agent: str, instruction: str) -> str:
    """One LLM call, routed through the gateway so it lands in the ledger."""
    model = for_agent(deps.gateway, agent, deps.workflow, state.get("run_id", "unassigned"))
    result = model.invoke([
        SystemMessage(content=(
            "You are the {agent} on an education-only research desk. You never "
            "place orders. Be concise and cite the numbers you were given."
        ).format(agent=agent.replace("_", " "))),
        HumanMessage(content=instruction),
    ])
    return str(result.content)


# ----------------------------------------------------------------- analysts
def _metric_node(
    agent: str, analyse: Callable[[MarketData, str, date], AnalystReport], deps: Deps
) -> Callable[[CommitteeState], dict[str, Any]]:
    """A T6 analyst: deterministic numbers, then LLM prose over them.

    The split is DESK_DESIGN §1 W1's rule applied to W2 — the model writes the
    words, never the numbers. A model that cannot see a metric cannot invent
    one, because the numbers are rendered before it is called.
    """
    def node(state: CommitteeState) -> dict[str, Any]:
        started = time.monotonic()
        report = analyse(deps.data, state["ticker"], state["as_of"])
        prose = _prose(deps, state, agent,
                       f"Interpret these measurements. Say plainly which are "
                       f"UNAVAILABLE and do not substitute for them.\n\n{report.render()}")
        text = f"{report.render()}\n\n{prose}"
        _record(deps, agent, {"metrics": report.render(), "prose": prose}, started)
        return {"reports": {agent: text}}

    return node


def _news_node(deps: Deps) -> Callable[[CommitteeState], dict[str, Any]]:
    def node(state: CommitteeState) -> dict[str, Any]:
        started = time.monotonic()
        if deps.news is None:
            text = "news: UNAVAILABLE (no news source configured)"
            _record(deps, "news_sentiment", {"metrics": text, "prose": ""}, started)
            return {"reports": {"news_sentiment": text}}
        raw = deps.news(state["ticker"], state["as_of"])
        prose = _prose(deps, state, "news_sentiment",
                       f"Summarise sentiment from these headlines, with counts.\n\n{raw}")
        _record(deps, "news_sentiment", {"metrics": raw, "prose": prose}, started)
        return {"reports": {"news_sentiment": f"{raw}\n\n{prose}"}}

    return node


def _price_metrics(data: MarketData, ticker: str, as_of: date, fields: tuple[str, ...],
                   label: str) -> AnalystReport:


    try:
        got = data.quote_scalars(ticker, list(fields), as_of)
    except ProviderError as exc:
        return AnalystReport(label, ticker, as_of,
                             tuple(unavailable(f, str(exc)) for f in fields))
    return AnalystReport(label, ticker, as_of, tuple(
        Metric(f, got.value[f], got.source, degraded=got.degraded) for f in fields
    ))


def _technical(data: MarketData, ticker: str, as_of: date) -> AnalystReport:
    return _price_metrics(data, ticker, as_of,
                          ("fiftyDayAverage", "twoHundredDayAverage", "regularMarketPrice"),
                          "Technical")


def _fundamentals(data: MarketData, ticker: str, as_of: date) -> AnalystReport:
    return _price_metrics(data, ticker, as_of,
                          ("forwardPE", "grossMargins", "returnOnEquity"),
                          "Fundamentals")


# ------------------------------------------------------------- quality gate
def _gate_node(deps: Deps) -> Callable[[CommitteeState], dict[str, Any]]:
    """Between the analysts and the debate, per SUPERSEDED.md.

    A 14-node graph fails in the middle, not at the end. Rejected reports are
    still persisted — they are exactly what you need to debug a bad verdict.
    """
    def node(state: CommitteeState) -> dict[str, Any]:
        grades = grade_all(dict(state.get("reports", {})))
        bad = rejected(grades)
        if bad:
            log.warning("quality gate rejected %d analyst report(s): %s",
                        len(bad), {a: g.reason for a, g in bad.items()})
        return {"grades": grades}

    return node


def _accepted(state: CommitteeState) -> str:
    grades = state.get("grades", {})
    kept = {a: t for a, t in state.get("reports", {}).items()
            if a not in grades or grades[a].passed}
    return "\n\n---\n\n".join(f"[{a}]\n{t}" for a, t in sorted(kept.items())) or "(none)"


# ----------------------------------------------------------------- the rest
def _debate_node(agent: str, stance: str, deps: Deps) -> Callable[[CommitteeState], dict[str, Any]]:
    def node(state: CommitteeState) -> dict[str, Any]:
        started = time.monotonic()
        text = _prose(deps, state, agent,
                      f"Argue the {stance} case for {state['ticker']} from these "
                      f"analyst reports.\n\n{_accepted(state)}")
        _record(deps, agent, {"argument": text}, started)
        if stance == "bull":
            return {"bull": text}
        return {"bear": text}

    return node


def _synthesis_node(deps: Deps) -> Callable[[CommitteeState], dict[str, Any]]:
    def node(state: CommitteeState) -> dict[str, Any]:
        started = time.monotonic()
        text = _prose(deps, state, "research_manager",
                      f"Weigh these two cases and state which is better supported.\n\n"
                      f"BULL:\n{state.get('bull','')}\n\nBEAR:\n{state.get('bear','')}")
        _record(deps, "research_manager", {"synthesis": text}, started)
        return {"synthesis": text}

    return node


def _trader_node(deps: Deps) -> Callable[[CommitteeState], dict[str, Any]]:
    def node(state: CommitteeState) -> dict[str, Any]:
        started = time.monotonic()
        text = _prose(deps, state, "trader",
                      "Propose an entry band, a stop and a target. This is a "
                      "RESEARCH proposal; no order is placed.\n\n"
                      f"{state.get('synthesis','')}")
        _record(deps, "trader", {"plan": text}, started)
        return {"trade_plan": text}

    return node


def _risk_node(deps: Deps) -> Callable[[CommitteeState], dict[str, Any]]:
    def node(state: CommitteeState) -> dict[str, Any]:
        started = time.monotonic()
        text = _prose(deps, state, "risk_manager",
                      "Review liquidity, concentration, correlation and VaR. "
                      f"State pass or fail for each.\n\n{state.get('trade_plan','')}")
        _record(deps, "risk_manager", {"review": text}, started)
        return {"risk_review": text}

    return node


def _verdict_node(deps: Deps) -> Callable[[CommitteeState], dict[str, Any]]:
    def node(state: CommitteeState) -> dict[str, Any]:
        started = time.monotonic()
        model = for_agent(deps.gateway, "fund_manager", deps.workflow,
                          state.get("run_id", "unassigned")).with_structured_output(Verdict)
        raw = model.invoke([HumanMessage(content=(
            f"Ticker {state['ticker']}. Return the committee verdict.\n\n"
            f"SYNTHESIS:\n{state.get('synthesis','')}\n\n"
            f"PLAN:\n{state.get('trade_plan','')}\n\n"
            f"RISK:\n{state.get('risk_review','')}"
        ))])
        verdict = raw if isinstance(raw, Verdict) else Verdict(
            ticker=state["ticker"], action=Action.HOLD, conviction=1,
            rationale="verdict node returned an unparseable object",
        )
        _record(deps, "fund_manager", {"verdict": verdict.model_dump(mode="json")}, started)
        return {"verdict": verdict}

    return node


def _add(graph: Any, name: str, fn: Callable[[CommitteeState], dict[str, Any]]) -> None:
    """One typed seam for all nine nodes.

    langgraph's `add_node` overloads do not bind their node type variable from
    a plain `Callable[[CommitteeState], dict]`, even though `CommitteeState`
    is a TypedDict and the graph compiles and runs — nine identical mypy
    errors, none of them a defect. Funnelling the calls through one helper
    resolves it without a single suppression anywhere. (A `type: ignore` was
    tried first and `warn_unused_ignores` correctly reported it as
    unnecessary.)
    """
    graph.add_node(name, fn)


def build(deps: Deps) -> Any:
    """Compile the committee. Fan the seven analysts out in parallel, gate,
    debate, synthesise, plan, risk-check, then decide."""
    graph = StateGraph(CommitteeState)

    metric_nodes = {
        "technical": _technical,
        "fundamentals": _fundamentals,
        "estimates": estimates_analyst.analyse,
        "flow_ownership": flow_analyst.analyse,
        "options": options_analyst.analyse,
        "macro": lambda data, ticker, as_of: macro_analyst.analyse(data, as_of),
    }
    for name, fn in metric_nodes.items():
        _add(graph, name, _metric_node(name, fn, deps))
    _add(graph, "news_sentiment", _news_node(deps))

    _add(graph, "quality_gate", _gate_node(deps))
    _add(graph, "bull_researcher", _debate_node("bull_researcher", "bull", deps))
    _add(graph, "bear_researcher", _debate_node("bear_researcher", "bear", deps))
    _add(graph, "research_manager", _synthesis_node(deps))
    _add(graph, "trader", _trader_node(deps))
    _add(graph, "risk_manager", _risk_node(deps))
    _add(graph, "fund_manager", _verdict_node(deps))

    for analyst in ANALYSTS:
        graph.add_edge(START, analyst)
        graph.add_edge(analyst, "quality_gate")
    for side in DEBATE:
        graph.add_edge("quality_gate", side)
        graph.add_edge(side, "research_manager")
    graph.add_edge("research_manager", "trader")
    graph.add_edge("trader", "risk_manager")
    graph.add_edge("risk_manager", "fund_manager")
    graph.add_edge("fund_manager", END)
    return graph.compile()
