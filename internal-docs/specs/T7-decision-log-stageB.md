# T7 decision log — stage B: the 14-node committee graph

Branch `desk-t7-wiring` off `main` @ `f10a839`. **Tier: high-stakes.**

## Where the graph could live — three constraints, one answer

| Constraint | Rules out |
|---|---|
| `tradingagents/graph/__init__.py` eagerly imports `trading_graph`, which imports `llm_clients` **and** `langgraph.checkpoint.sqlite` | anything inside `engine/tradingagents/graph/` — importing it drags back all 21 packages T6 excluded |
| `VENDORING.md` §4b: "engine/ may import desk; desk must never import engine" | `desk/committee.py` — this module imports the engine's analyst nodes |
| Invariant 6 hashes vendored files against upstream, and `make vendor-manifest` re-fetches from upstream, so **no local edit to a vendored file can ever be blessed** | editing `setup.py`'s hardcoded four-analyst dict. **Verified:** appending one comment to it fails the invariant |

So: `engine/committee/`, a new first-party package inside `engine/`, absent
from `.vendored-manifest`, linted and typed. T1 predicted T6/T7 would want to
edit `setup.py`; the vendoring machinery makes that impossible, which is the
design working rather than fighting us.

## M10 is resolved

`SUPERSEDED.md` carried "repointing `engine/dataflows/` at `desk/data.py`" as
UNASSIGNED since T1, to be decided before T6. T7 decides it:

- `desk/data.py` serves **six** of seven analysts;
- **news/sentiment** uses the engine's `yfinance_news` dataflow, because the
  MarketData Protocol has no news method and adding one is a T2 change.
  **Measured: it needs no API key.**

Both paths are yfinance underneath. One provider reached two ways is not two
providers — which is why this is acceptable rather than merely tolerated. The
engine's five vendored analysts are not used by the committee at all.

## Decisions

| # | Decision | Why |
|---|---|---|
| D1 | Analysts fan out from `START` in parallel, with a `_merge` reducer on `reports` | Seven sequential LLM calls would triple wall-clock for no benefit. The reducer is what makes concurrent writes safe |
| D2 | Numbers are rendered **before** the model is called | §1 W1's rule applied to W2. A model that cannot see a metric cannot invent one |
| D3 | The quality gate sits between the analysts and the debate | A 14-node graph fails in the middle. `_accepted()` is what the debate is fed, so a rejected report cannot be argued from |
| D4 | An unparseable verdict falls back to **HOLD at conviction 1** | The committee must not guess an action. Conviction 1 says "we did not decide", which is honest and legible downstream |
| D5 | The orchestrator has **no node** | It is the graph runner itself, which is what DESK_DESIGN's "Manual Trigger / orchestrator" describes. 13 nodes emit output; the 14th is the thing running them |

## Per-step review (ship-workflow §6) — NON-SKIPPABLE

| # | Finding | Sev | Triage |
|---|---|---|---|
| T7B-R1 | **`sqlite3.ProgrammingError`: "SQLite objects created in a thread can only be used in that same thread."** LangGraph fans the seven analysts across a thread pool and every one persists its output. **This would have killed the first real committee run** | **High** | **Fixed** — `check_same_thread=False` in `desk/db.py` plus a write lock in `desk/runs.py`. Mutation-tested: reverting the flag fails the persistence test |
| T7B-R2 | The `llm_clients` grep **false-positived on this module's own docstring**, which names it in order to explain why it is avoided | Med | **Fixed** — rewritten with `ast`. **Third time this project has hit this class** (T1 pandas-is-GPL, T5 `ticker_fundament`). Prose about a thing is not the thing |
| T7B-R3 | A gate test asserted the rejected text was absent from the bull node's output — but the fake makes *every* node emit the same marker, including the bull | Med | **Test fixed** to assert on `_accepted()`, which is what the debate is actually fed |
| T7B-R4 | Nine identical mypy errors on `add_node` | Low | **Fixed with zero suppressions** — funnelled through one `_add` helper. A `type: ignore` was tried first and `warn_unused_ignores` correctly reported it as unnecessary |
| T7B-R5 | A dynamic TypedDict key (`{"bull" if … else "bear": text}`) | Low | Branched explicitly |

**Rejected:** none.

## Mutation tests

| Mutation | Tests failed |
|---|---|
| revert `check_same_thread=False` | 1 |
| gate stops filtering what the debate sees | 1 |

## Verification

A full committee run against fakes: **13 agents produce output, 7 analyst
reports, 13 ledger rows, $0.013 for the run**, verdict reached.

```
ruff check .   -> All checks passed!
mypy           -> clean, 120 source files
make test      -> all green
```

Structural guarantees asserted, not assumed: the committee never imports the
engine's `llm_clients` (by AST), it does not live under the vendored graph
package, it is absent from the manifest, and no order-placing symbol appears
anywhere in it.

`TICKETS.md` and `DESK_DESIGN.md` unmodified.

## Carried forward

- **Langfuse tracing is wired but unexercised.** `enable_langfuse_if_configured()`
  registers the litellm callbacks; with the committee now routed through that
  gateway, traces will appear once keys exist. No key, so unverified — same
  standing as FMP.
- **`with_structured_output` is unverified against a real model.** The fallback
  path is tested; the success path needs a live call, which belongs with the
  first real run.
- **The engine's five vendored analysts are now dead code** for our purposes.
  Worth deciding at T8 whether they stay vendored at all.
