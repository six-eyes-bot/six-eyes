# T7 decision log — stage A: bridge, verdict, quality gate, persistence

Branch `desk-t7-graph` off `main` @ `921dff4`. **Tier: high-stakes** (the
ticket's own classification).

T7 is large, so it splits like T1 and T2. **Stage A is everything except the
graph wiring** — all of it testable without an API key. Stage B is the wiring.

## The decisive finding

`engine/tradingagents/graph/trading_graph.py` calls `create_llm_client` from
`tradingagents.llm_clients`. Using it would have two consequences, and the
second is the one that matters:

1. it needs the 21 packages T6 measured and excluded; and
2. **every committee call would bypass `desk/llm.py` entirely** — no spend
   ledger, no daily ceiling, no reroute logging.

T2's whole purpose is that all 14 agents route through one gateway. Adopting
the engine's clients would have defeated it silently, and the failure would
have shown up as a surprising invoice rather than as an error.

So: `desk/llm_bridge.py`, a `BaseChatModel` over the T2 gateway. `BaseChatModel`
has exactly two abstract methods, and the real work is `bind_tools` —
**every** analyst node in the engine calls it, and the base class's default
raises `NotImplementedError`, so without it they all die on construction.

## Decisions

| # | Decision | Why |
|---|---|---|
| D1 | Bridge to the gateway rather than adopt the engine's LLM clients | The budget argument above. The package count is secondary |
| D2 | `Completion` gains `raw` | Tool calls cannot survive a `str` content field. Added last and defaulted, so existing callers are untouched |
| D3 | Malformed tool `arguments` yield `{}`, not an exception | A model emitting bad JSON should fail in the node that inspects the call, where the agent name is known — not deep inside the adapter |
| D4 | The verdict is a **pydantic** model, not a dict | This is an LLM's output, and the failure mode is a confident, well-formatted, out-of-range number. Conviction is bounded 1–10 at the type level |
| D5 | A price range needs **both** bounds or neither | Half a range renders as a real one |
| D6 | **Rejected reports are persisted too** | The report the quality gate threw away is exactly the one you need when debugging why the verdict was wrong |
| D7 | The quality gate rejects reports with **no numeric content** | A restatement of the ticker with no numbers is a non-answer dressed as one. The pattern is read from `simonlin1212/TradingAgents-astock` (Apache-2.0); no code copied, attributed in the module and in `LICENSES.md` |
| D8 | A test asserts `Verdict` has **no** order fields | D5 (no code path places an order) is structural. The verdict schema is where an order would first leak in |

## Per-step review (ship-workflow §6) — NON-SKIPPABLE

| # | Finding | Sev | Triage |
|---|---|---|---|
| T7-R1 | `bind_tools` default raises `NotImplementedError`; every engine analyst calls it | **High** | Implemented, and a test asserts it does not mutate the receiver — a bound copy that shared state would leak one analyst's tools into another's |
| T7-R2 | Tool calls were lost: `Completion` carried only `content` | **High** | `raw` added |
| T7-R3 | My ceiling test asserted the wrong arithmetic — at $0.001 a call against a $0.0015 ceiling, the **second** call is still under | Med | **Test fixed, code correct.** The ceiling is checked before a call, so two calls pass and the third is refused |
| T7-R4 | A test used `tool(lambda …, name=…)`, which is not the API | Low | Fixed |

**Rejected:** none.

## Mutation tests

| Mutation | Tests failed |
|---|---|
| quality gate stops rejecting LLM failure markers | 3 |
| conviction bounds removed from the verdict | 3 |
| bridge drops `run_id` (breaks the cost handoff) | 2 |

## Verification

```
ruff check .   -> All checks passed!
mypy           -> clean
make cover     -> desk/exit_rules.py 100% branch
make test      -> all green (31 stage-A tests)
```

No network, no API key: the bridge is driven by an injected `completion_fn`.

`runs.token_cost == SpendLedger.total_for_run(run_id)` — the handoff T3
defined and T2 fed is now executed and asserted.

## Carried forward to stage B

- **The graph wiring itself**, including mapping the engine's node set onto
  DESK_DESIGN §1 W2's 14. They are not 1:1: the engine has three risk debators
  where the design has one Risk Manager, and a `portfolio_manager` where the
  design has a Fund Manager.
- **The engine's `setup_graph` defaults to four analysts**
  (`market, social, news, fundamentals`); the design needs seven, and T6's
  four new nodes are not in its factory dict.
- **M10 remains open** — the engine's five vendored analysts use upstream
  dataflows while T6's four use `desk/data.py`. Two data paths. Stage B should
  decide deliberately rather than inherit.
