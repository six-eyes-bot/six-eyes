# THE DESK — `/ship` Ticket Queue (v2, adopt-first)

Revised so every ticket names what it **adopts** before what it **builds**. Net effect: from-scratch code drops from roughly 60% of the build to about 25%, and two tickets collapse to config.

---

## The base-repo decision comes first

The source post is TradingAgents-based — slide 3's node names (bull researcher, bear researcher, research manager, trader, risk manager, fund manager) are TradingAgents' exact graph, and the caption confirms it. But it isn't the only candidate, and one alternative has something the original lacks.

### Liveness verified — v2's recommendation was wrong

| Repo | Fork? | Signal | Verdict |
|---|---|---|---|
| `TauricResearch/TradingAgents` | no, upstream | Apache-2.0. Releases v0.2.0 (Feb 26) → v0.2.4 (Apr 26). Discord, arXiv paper, per-release contributor credits | **Base.** Actively maintained |
| `bit-r/TradingAgents-AI-hedge-fund` | **yes**, of the above | 0★, 0 forks, 149 commits all inherited, README byte-identical to upstream | **Reject.** Bare mirror, no divergence |
| `DanisHack/ai-hedge-fund` | **no** — own network root | 17★, 26 commits, MIT, 342 tests, CI on Py 3.11/3.12/3.13, 1 open issue | **Vendor and own.** Small but standalone and tested |
| `virattt/ai-hedge-fund` | no | ~51.7k★, ~9k forks | **Drop.** DanisHack covers the same ground under MIT with better test density |
| `td-02/ai-native-hedge-fund` | no | Audit-log pattern only | Reference, don't vendor |

**The reflection loop is upstream, not bit-r's.** TradingAgents v0.2.4 ships a persistent decision log at `~/.tradingagents/memory/trading_memory.md` that fetches realised return (raw and alpha vs SPY) on the next same-ticker run, writes a one-paragraph reflection, and injects recent same-ticker decisions plus cross-ticker lessons into the Portfolio Manager prompt. I attributed a native upstream feature to a mirror fork. **Base on upstream `TauricResearch/TradingAgents`.**

Upstream also already ships three things v2 had as work:

- **LangGraph checkpoint resume** (`--checkpoint`, per-ticker SQLite at `~/.tradingagents/cache/checkpoints/`) — a crashed cron run resumes from the last successful node instead of re-running fourteen agents. Resilience for T13, free.
- **Structured-output agents** for Research Manager, Trader, and Portfolio Manager — most of T7's verdict schema.
- **A five-tier rating scale** — maps onto the conviction score.

**T1 must include a license audit.** Upstream is Apache-2.0, DanisHack is MIT, Ghostfolio is AGPL-3.0. Mixed but compatible as long as nothing AGPL lands in the tree.

---

## Track A — Foundation

### T1 · Scaffold, pinned forks, license audit
`tier: standard`

> **Ticket:** Scaffold the-desk monorepo. Evaluate bit-r/TradingAgents-AI-hedge-fund against TauricResearch/TradingAgents upstream for divergence, pick a base, vendor it pinned to an explicit SHA. Install openbb, openbb-mcp-server, yfinance, finvizfinance, litellm. Run a license audit across all vendored dependencies and record it in internal-docs/LICENSES.md. Add pytest, ruff, mypy behind one make target.

**Done:** `make test` green; `versions.lock` records every SHA; no AGPL code in the tree without a recorded decision.

---

### T2 · Market data interface + LiteLLM gateway
`tier: standard`

> **Ticket:** Build desk/data.py exposing a MarketData protocol satisfied by OpenBB MCP (primary), yfinance (fallback), and finvizfinance (screener + fundamentals). Fallback must be explicit and logged, never silent. TTL cache keyed on (ticker, metric, date). Separately, stand up LiteLLM as the gateway for all agent LLM calls and point the committee's provider config at it.

**Adopt:** `openbb` · `yfinance` · `lit26/finvizfinance` · `LiteLLM`

**The LiteLLM decision is the point of this ticket.** Routing all 14 agents through one gateway gets per-call cost tracking, spend caps, provider fallback, and a single Langfuse integration point — instead of instrumenting fourteen agents individually. It collapses most of T14 into config and makes T7's observability nearly free.

**Done:** the same call returns the same shape from any backend; a forced OpenBB failure surfaces a visible fallback; every LLM call appears in LiteLLM's spend log.

---

### T3 · Book schema + canonical ingest
`tier: standard`

> **Ticket:** Implement the SQLite schema in internal-docs/DESK_DESIGN.md §4 and desk/ingest.py against the canonical CSV schema only. Reconciliation per §4.5. --dry-run default, --commit to persist. Fixtures at tests/fixtures/positions_*.csv.

**Build, don't adopt.** Ghostfolio is the obvious candidate and the wrong one: NestJS + Next.js + Postgres + Redis and a full wealth-management UI, to get cost-basis tracking that fits in a SQLite table. It's also AGPL-3.0. What *is* worth taking is the `ghostfolio-export-transactions` ecosystem — community CSV converters for Schwab, IBKR, DEGIRO, Trading212 and others. Read those as reference implementations for T15's parser; don't depend on them.

**Done:** re-import with changed quantities preserves every stop, target, and thesis link — asserted explicitly.

---

### T4 · Exit-rule engine
`tier: standard`

> **Ticket:** Port DanisHack/ai-hedge-fund's `src/backtest/portfolio_tracker.py` stop-loss logic into desk/exit_rules.py — fixed stop, trailing stop, take-profit, with its documented trigger priority (fixed > trailing > take-profit, one sell per position per cycle). Add the two rules it lacks: time stop and thesis-invalidation flag. Port its tests alongside. No LLM calls in this module.

**Adopt, mostly.** v2 said build this and I was wrong — DanisHack already has three of the five rules implemented, tested, and with the trigger-precedence question already answered. That precedence detail is exactly the kind of thing you get wrong on a first pass and only notice when two rules fire on the same bar.

Also worth taking from the same repo: `src/data/cache.py` (TTL cache, folds into T2) and `src/paper_trading/state.py` (persistent portfolio state, folds into T3).

**Done:** 100% branch coverage; seeded 5-position book yields `5× HOLD · 0 EXITS TRIGGERED`; two simultaneous triggers resolve per the documented precedence.

---

### T5 · Health report + staleness guard
`tier: micro`

Unchanged from v1. Build. Stale book produces a refusal, not a report.

---

## Track B — Committee

### T6 · Analyst nodes — audit before authoring
`tier: standard`

> **Ticket:** Add Estimates, Flow/Ownership, Options, and Macro analyst nodes consuming desk/data.py. Before writing any of them, audit which already exist in the base fork and in virattt/ai-hedge-fund, and port rather than write wherever one exists.

The analyst sets in TradingAgents and virattt both overlap this list. The genuinely new ones are likely Options and Flow/Ownership; Estimates and Macro probably exist in one of the two trees already.

---

### T7 · Committee graph + verdict schema + tracing
`tier: high-stakes`

> **Ticket:** Wire all 14 agents per internal-docs/DESK_DESIGN.md §1 W2. Persist every agent output to agent_outputs. Verdict carries action, price range, conviction 1-10, rationale. Instrument with Langfuse via its LangGraph integration.

**Adopt:** the base fork's graph (this is mostly wiring, not authoring) · `langfuse/langfuse` (MIT, self-hostable)

Langfuse gives typed observations, agent-graph visualisation, and per-step token and cost capture. In a 14-node graph where failures hide in intermediate steps rather than the final answer, that's the difference between debugging and guessing.

---

### T8 · Eval harness — now mostly assembly
`tier: high-stakes`

> **Ticket:** Port DanisHack/ai-hedge-fund's backtest module wholesale — `engine.py` (date stepping), `metrics.py` (Sharpe, max drawdown, Calmar, win rate, profit factor, SPY benchmark), `models.py`, `export.py`. Run its deterministic no-LLM rule-based mode as the control arm and the committee as the treatment arm over the same held-out dates. Layer Langfuse datasets and LLM-as-judge for conviction calibration.

**Almost entirely assembly now.** One repo supplies both arms of the experiment: a backtester with a SPY benchmark, and a deterministic zero-LLM scoring mode that is fast and reproducible by construction. That control arm is the piece that matters — without it you cannot show the committee beats simple scoring, and "beats simple scoring" is the only claim worth making.

Dropped virattt/ai-hedge-fund from v2's plan. It's the far more popular repo, but DanisHack covers the same ground under MIT with 342 tests, and one source beats two.

**Done:** two numbers, not one.

1. **Directional accuracy** — committee vs deterministic baseline on held-out dates. Answers "is the committee thinking."
2. **Expectancy net of costs** — per-trade expected value after spread, slippage, and commission, plus max drawdown and its duration. Answers "could this trade unattended."

These are different questions and the second is the one that gates autonomy. A model with real directional skill still loses money at high turnover, and that is the specific way retail algo systems die. Model costs explicitly; do not assume frictionless fills.

Report drawdown *duration* alongside magnitude. The number that decides whether a system keeps running is the one you can sit through without switching it off at the worst possible moment.

If the committee doesn't win on (1), stop and reconsider before building Tracks C and D. Nothing climbs the autonomy ladder without (2).

---

### T9 · Valuation engine — adopt wholesale
`tier: micro` *(was standard)*

> **Ticket:** Vendor EmanueleSturzo/DCF-Valuation-Model (MIT). It ships 5-year DCF, WACC via CAPM, Gordon Growth and EV/EBITDA exit-multiple terminal values, and a 10,000-run Monte Carlo over growth, margins, WACC and TGR producing percentiles. Adapt: raise to 20,000 paths, add a fixed seed, replace its yfinance calls with desk/data.py.

A near-exact match for slide 4's thesis card — blended DCF, exit-multiple, Monte Carlo, CAPM inputs, bear/base/bull range. Tier drops to micro because the work is vendoring plus three edits.

**Done:** identical seed and inputs → byte-identical output. Its README flags that Yahoo consensus estimates go stale for small caps — routing through desk/data.py with OpenBB primary fixes that.

---

### T10 · Thesis card
`tier: micro`

Unchanged. Build. Education-only footer asserted in a test.

---

## Track C — Screen and execution

### T11 · Screener + playbook filter
`tier: standard`

> **Ticket:** Implement desk/screener.py on finvizfinance (day gainers, SMA crosses, universe filters — its Overview screener takes a filters dict directly). Build desk/playbook.py as a thin YAML evaluator emitting per-candidate pass/reject with a one-line reason. Author playbooks/edge_breakout_v2.yaml.

**Adopt the screener, build the filter.** finvizfinance covers slide 5's day-gainers screen out of the box. The playbook is your edge, is idiosyncratic, and is ~150 lines — a generic rules engine would be more configuration than code.

**Caveat:** finviz quotes are delayed 15–20 minutes and the library scrapes, so it breaks when finviz changes markup; its changelog shows exactly that pattern. Fine for a 09:00 screen, not for anything time-sensitive.

---

### T12 · Ticket sizing + approval gate
`tier: high-stakes`

> **Ticket:** Port sizing and risk controls from DanisHack/ai-hedge-fund's `risk_manager.py` and `portfolio_manager.py` — confidence-based sizing, position limits, and correlation-aware group caps (correlation > 0.7 over 60 days, each correlated group capped at 40% of portfolio). Build desk/ticket.py's state machine on top: AWAITING_APPROVAL → APPROVED | REJECTED | EXPIRED (24h). Adopt the hash-chained audit log pattern from td-02/ai-native-hedge-fund. No broker integration.

**Adopt the risk math, build the state machine.** The correlation-aware group cap is the non-obvious part and it's already written — it stops the committee putting 75% into tech because all six analysts independently like NVDA, MSFT and GOOGL. Slide 3 shows a correlation check passing; this is that check.

**Build the approver as an interface, not an `if` statement.** `Approver.decide(ticket) -> Decision` with exactly one implementation in this build: `HumanApprover`. Populate `decided_by_kind=HUMAN` and leave `approver_rule_id` null. A `RuleApprover` is a later ticket that must not exist yet.

This is the autonomy ladder's seam. The rung is a property of which approver is registered, never of the state machine, so climbing a rung is a config change plus a T8 number — not a refactor. Building it as a boolean flag now makes the second rung a rewrite later.

Hash-chaining makes the decision log tamper-evident, which is what you want on the one table recording who approved what.

**Done:** a test asserts no path reaches APPROVED without a human-attributed audit row. Grep the diff for order-placement calls yourself.

---

## Track D — Operate

### T13 · Hermes skills + cron
`tier: standard`

Unchanged, with one scope reduction: the learning requirement moved to the base fork's reflection loop in T1. Hermes is now scheduling, delivery, and session state only. Still verify cron can reach MCP servers and attached skills on your pinned SHA before building on it; fallback is no-agent-mode cron invoking a CLI entrypoint.

---

### T14 · Cost caps — mostly config now
`tier: micro` *(was standard)*

> **Ticket:** Configure LiteLLM budgets and spend caps to hard-stop the scheduler at a daily ceiling. Surface per-agent and per-model cost from LiteLLM and Langfuse. Log which model actually served each call.

Collapsed by the T2 gateway decision. LiteLLM ships spend tracking and budget enforcement; Langfuse ships the per-step cost view. What remains is configuration plus the cron kill-switch.

Still log the responding model — Fable's safeguards route some queries to Opus 5, and you want that visible rather than assumed.

---

### T15 · Wells Fargo CSV adapter
`tier: micro` — **LAST, blocked on a real export**

Unchanged. Mapping dict only; touching anything outside the adapter file means T3 drew the seam wrong. Reference the ghostfolio broker-converter implementations for parser patterns.

---

### T16 · Kronos forecast analyst — **optional, gated behind T8**
`tier: standard` · **do not start before T8 produces a baseline number**

> **Ticket:** Add a Forecast Analyst node backed by shiyu-coder/Kronos (MIT). Inference only — no finetuning, so no Qlib dependency. Load NeoQuasar/Kronos-small (24.7M) first; escalate to Kronos-base (102.3M) only if small underperforms. Feed OHLCV from desk/data.py. Use sample_count > 1 to generate a path distribution, and derive P(hit stop before target) as a sizing input for T12. Evaluate as a new arm in the T8 harness against the deterministic baseline.

**What it is:** a foundation model for candlestick sequences — tokenizes OHLCV into discrete tokens, autoregressively predicts forward bars. 36.5k★, 6.1k forks, MIT, AAAI 2026, arXiv 2508.02739.

**What it is not:** a replacement for T9. Kronos caps at 512-bar context on small and base, so it cannot produce a five-year view. T9's Monte Carlo simulates DCF assumptions over five years; Kronos simulates price paths over days to weeks. Complements, not substitutes — don't let them collapse into each other.

**Best fit:** T11's morning screen and T4's exit rules, where the horizon matches. The `sample_count` path distribution yields P(hit stop before target), which nothing else in the stack provides and which is a genuine sizing input.

**Why it's gated:**

- It brings PyTorch and HuggingFace transformers — multi-gigabyte, and a dependency class nothing else here needs. Largest single addition available, directly against the dependency-economy criterion.
- Its live demo is BTC/USDT and its finetune example is A-shares. **US equity daily-bar performance is unverified.**
- 204 open issues against 54 open PRs and 76 total commits. High interest, unclear maintainer bandwidth.
- Inference is free at the margin, which suits the subscription budget — but only if it works.

T8 exists to answer exactly this kind of question with a number. Adopt after it does, not before.

**Done when:** Kronos scores as a measured arm in T8 against the deterministic baseline. **If it doesn't beat baseline, close the ticket and delete the dependency** — that is a successful outcome, not a failure.

---

### T17 · Execution venue — **research only, no implementation**
`tier: standard` · **blocked until T8 reports expectancy**

> **Ticket:** Produce an ADR comparing execution venues with real trading APIs — Alpaca, Interactive Brokers, Tradier, Schwab — on API quality, commission and spread, paper-trading fidelity, and the operational cost of running a second account alongside Wells Fargo. No integration code. No credentials. Output internal-docs/adr/0002-execution-venue.md at status Proposed.

Wells Fargo forecloses this structurally: aggregators can read positions and explicitly cannot trade. So active execution is not a config flag — it requires a second account somewhere else, which is a real decision with tax, custody, and operational consequences.

**Two things to price that people forget:** paper-trading fidelity (a venue whose paper fills are optimistic will flatter every backtest you run through it), and pattern-day-trader rules, which bind below $25k equity in a US margin account and constrain cadence directly.

**Done when:** an ADR exists and you've read it. Implementation is a separate ticket that doesn't exist yet and shouldn't until T8 justifies it.

---

## What's actually left from scratch

| Component | v2 estimate | v3 after liveness checks | Why |
|---|---|---|---|
| Exit rules | build | **port + 2 rules** | DanisHack has fixed/trailing/take-profit with trigger precedence, tested |
| Sizing + risk caps | build | **port** | Correlation-aware group caps already written |
| Backtest + metrics | port from virattt | **port from DanisHack** | MIT, 342 tests, SPY benchmark included |
| Eval control arm | build | **port** | Deterministic no-LLM mode exists |
| Macro analyst | build | **port** | `macro_regime.py` |
| Valuation | build | **vendor + 3 edits** | EmanueleSturzo, MIT |
| Learning loop | build on Hermes | **already upstream** | v0.2.4 decision log |
| Crash recovery | build | **already upstream** | LangGraph checkpoint resume |
| Verdict schema | build | **mostly upstream** | Structured-output agents |
| Cost caps | build | **config** | LiteLLM budgets |
| TTL cache | build | **port** | `src/data/cache.py` |

**Genuinely yours, ~10% of the build:**

1. **CSV ingest + reconciliation** (T3) — no OSS equivalent, because no one else's book is defined by a Wells Fargo export layered with your stops
2. **Playbook filter** (T11) — `EDGE_BREAKOUT_V2` is your edge; the whole point is that it isn't commodity
3. **Approval state machine** (T12) — every OSS option either auto-executes or paper-trades; none has a human gate
4. **Health report + thesis renderers** (T5, T10) — presentation, and yours
5. **Wiring** — desk/data.py behind OpenBB, and gluing ported modules to it

That last one is the hidden cost and the thing to watch. DanisHack is built on Polygon.io, upstream TradingAgents on its own dataflows, EmanueleSturzo on yfinance. Every ported module needs repointing at desk/data.py. Porting four modules from three repos with three different data assumptions is real integration work — it's smaller than writing them, but it isn't free, and it's where a plan like this usually slips.

**Where I'd stop reducing.** Items 1–3 above are the system. If you find OSS for the approval gate, read it carefully rather than adopting it — a human-in-the-loop gate is exactly the component where someone else's assumptions about what "approved" means will quietly not be yours.
