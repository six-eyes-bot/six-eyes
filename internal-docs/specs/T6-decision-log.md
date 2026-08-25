# T6 decision log — analyst nodes

Branch `desk-t6-analysts` off `main` @ `ebf79bc`. **Tier: standard.**

## The audit came first, because the ticket says so

T6 is titled "audit before authoring" and instructs: "audit which already
exist in the base fork and in virattt/ai-hedge-fund, and port rather than write
wherever one exists."

**There was nothing to port.** Full table in `SUPERSEDED.md`. The headline:
`virattt/ai-hedge-fund` no longer has analyst nodes — at `eff8a732` it is a
quant library whose `signals/` are investor personas (buffett, munger, graham,
lynch, druckenmiller, pead), not per-analyst agents. The ADR evaluated a
differently-shaped repo. The engine has five analysts, none of them the four
DESK_DESIGN still needs.

## The finding that mattered more than the ticket

**ADR 0001 justified `langgraph` as "already transitive via TradingAgents — 0
net new packages". That was false as built.** The accounting assumed
TradingAgents would be *installed*; T1 vendored it as source and deliberately
omitted its `pyproject.toml`, so the transitive dependencies never arrived.

The vendored engine was **inert** — every one of its analysts, its graph and
its LLM clients failed to import. This had been true since T1 and nothing
caught it, because nothing had tried to import the engine.

| Option | Net-new | Verdict |
|---|---|---|
| full engine declaration | **38** | rejected — 21 of them exist only for `llm_clients/` |
| `langgraph` + `langchain-core` + `stockstats` | **17** | **chosen** |

The 21 rejected packages are `langchain-anthropic`, `langchain-openai`,
`langchain-google-genai`, `langchain-aws` and their trees. They are redundant:
**T2 routes every model call through litellm**, and nothing on the analyst or
graph path imports them. Recorded as a constraint on T7 — routing the committee
through the engine's own LLM clients would pull all 21 back in.

Package count is now **123 against the ADR's budget of 142**, so this does not
exceed the ADR; it partially realises a budget that was never reached.

## Decisions

| # | Decision | Why |
|---|---|---|
| D1 | The four nodes live **inside `engine/`**, not in `desk/` | T1's spec anticipated exactly this ("T6 adds first-party analyst nodes *inside* engine/"), and it is the scenario invariant 8 exists for. Verified live: they are absent from `.vendored-manifest`, ruff catches an injected error in them, and mypy types them |
| D2 | **No LLM calls.** T6 produces numbers; T7 produces prose | DESK_DESIGN §1 W1's rule applied to W2. A test greps all five files for `litellm`, `completion(`, `LLMGateway`, `openai`, `anthropic` |
| D3 | `Metric.unavailable` is a first-class state | DESK_DESIGN asks for metrics this desk cannot source at its tier. Reporting a plausible substitute is the failure the whole data layer exists to prevent |
| D4 | **"Institutional net" is reported UNAVAILABLE** | The metric asked for is a net *flow*; 13F is FMP **Ultimate** ($99) and we are at Starter ($19) with T18 open. What is sourceable is `heldPercentInstitutions` — a **level** — reported under its own name. Presenting a level where a delta was asked for would be exactly the silent failure this project keeps finding |
| D5 | Options failure says *why* it cannot degrade | Nothing under $3,500/mo sells options IV, so the report names that rather than just failing |
| D6 | Macro takes **no ticker** | It describes the world, not a holding, so it is evaluated once per run |
| D7 | UST 10Y from FRED `DGS10`, never `^TNX` | `^TNX` is the series guard (a) was written for. A test greps the module body to keep it that way |

## Per-step review (ship-workflow §6) — NON-SKIPPABLE

| # | Finding | Sev | Triage |
|---|---|---|---|
| T6-R1 | **`(target - price)` with `target` possibly `None`** — a `TypeError` the moment a ticker has no published consensus target. Small caps routinely have none | **High** | **Fixed** + regression test. Caught by **mypy**, not by any test I wrote |
| T6-R2 | **The engine was not importable at all** | **High** | **Fixed** — see above. Latent since T1 |
| T6-R3 | `make setup` does not uninstall, so a 143-package venv passed an import test against a 119-package lock — **a false green** | **High** | **Caught by rebuilding clean.** The minimal set then failed on `stockstats`, which the leftovers had been hiding. Every dependency claim here is from a clean venv |
| T6-R4 | Two tests hardcoded a spot of 191; the recorded fixture says **216.85** | Med | **Tests fixed, code vindicated.** Expectations now derived from the fixture so they cannot drift |
| T6-R5 | Zero put volume would have produced a division by zero | Med | **Fixed** — reported unavailable. A zero denominator is not a ratio of infinity, it is no data |

**Rejected:** none.

## Verification

```
ruff check .   -> All checks passed!
mypy           -> clean, 112 source files
pytest -q      -> all green (17 analyst tests)
make cover     -> desk/exit_rules.py 100% branch
```

Dependency claims measured in a **clean** venv: 123 installed, provider SDKs
absent, engine imports. Invariants 3 and 4 pass — none of the 17 new packages
is copyleft, none is banned.

`TICKETS.md` and `DESK_DESIGN.md` unmodified.

## Carried forward

- **T7 must route the committee through `desk/llm.py`**, not
  `engine/tradingagents/llm_clients/`, or it pulls back the 21 packages this
  ticket deliberately excluded.
- **M10 is still unassigned** — repointing `engine/dataflows/` at
  `desk/data.py`. T6 did not need it resolved: the four new nodes consume
  `desk/data.py` directly per the ticket, and the five vendored analysts keep
  their own dataflows. That leaves the engine with **two data paths**, which
  T7 should decide about deliberately rather than inherit.
- **Institutional net flow** needs FMP Ultimate ($99) — T18.
