# THE DESK — Design Doc

**Target:** a self-hosted, cron-driven AI investment committee that health-checks a live book, screens for new setups, and produces written theses with conviction scores. Human approval gate before any order.

**How to use this doc:** this is *context*, not a plan. `ship-workflow` generates its own spec (step 1) and audits it (step 2); feeding it a finished plan would collide with both. Commit this to `internal-docs/DESK_DESIGN.md` so the brainstorm step reads it as background, and drive the build from `THE_DESK_TICKETS.md` — one `/ship` invocation per ticket.

**Status:** reverse-engineered from a public post (6-slide carousel; slides 2 and 6 unavailable). Architecture is inferred from screenshots, not the author's source. Inferences marked `[INFERRED]`.

---

## 0. Decisions already made (override before running)

| # | Decision | Default | Why |
|---|---|---|---|
| D1 | Committee engine | Fork `TauricResearch/TradingAgents` | Its LangGraph flow already matches the post's pipeline ~1:1 |
| D2 | Orchestrator / scheduler / memory | `NousResearch/hermes-agent` | Provides cron, persistent memory, skills, MCP client, delivery channels |
| D3 | Market data | `openbb` + `openbb-mcp-server`, `yfinance` fallback | Both visible in slide 3 |
| D4 | LLM | `claude-fable-5` deep / `claude-haiku-4-5` fast | Post's headline claim; Haiku for the cheap analyst passes |
| D5 | Broker | **None. Paper only.** | Custodian is Wells Fargo — no retail trading API exists (see §4.5) |
| D6 | Book storage | SQLite (`desk.db`), seeded from CSV | Hermes already persists SQLite; no new infra |
| D7 | Delivery | Telegram via Hermes gateway | Slide 5 implies push-to-phone; swap freely |

**D5 is a hard gate.** Every workflow in this spec terminates in a ticket marked `AWAITING_APPROVAL`. No code path places an order. Do not add one in this build.

---

## 1. What the source system actually is

Three separate scheduled workflows sharing one committee engine and one book. The post presents them as one product; they are not one code path.

```
                      ┌──────────────────────────────┐
                      │   HERMES (orchestrator)      │
                      │   cron · memory · skills     │
                      │   · MCP client · delivery    │
                      └──────────────┬───────────────┘
                 ┌───────────────────┼───────────────────┐
                 ▼                   ▼                   ▼
        W1 BOOK HEALTH        W2 DEEP DIVE         W3 MORNING SCREEN
        (daily 16:15 ET)      (on demand)          (daily 09:00 ET)
                 │                   │                   │
                 ▼                   ▼                   ▼
        positions →          ticker →            screener →
        exit-rule engine     14-agent committee  playbook filter →
        → health report      → verdict + DCF     committee → ticket
                 │                   │                   │
                 └───────────────────┴───────────────────┘
                                     ▼
                          SQLite: book · runs · tickets · audit
```

### W1 — Book Health Check (slide 4, FIG 02)
Input: open positions. Slide shows 5 (TIVO, NVDA, MU, GOOG, GIV) with entry, stop, cost basis, alert state. Each is evaluated against **pre-set exit rules**, then an Exit-Rule Engine emits `n/5 triggered` and an aggregate Health Report. Observed output: `5× HOLD · 0 EXITS TRIGGERED`.

This is deterministic rule evaluation, not an LLM committee. The LLM only writes the summary prose. Keep it that way — it's the cheapest and most reliable part of the system.

### W2 — Deep Dive (slide 3 + slide 4 FIG 03)
One ticker in, full committee out. This is the 14 agents.

Counted from the slide-3 node graph:

| Layer | Agents | Slide-3 evidence |
|---|---|---|
| Data | OpenBB MCP, yFinance (local) | shown as source nodes, not agents |
| Analysts (7) | Technical, Fundamentals, Estimates, News/Sentiment, Flow/Ownership, Options, Macro | each a card with concrete metrics |
| Debate (2) | Bull Researcher, Bear Researcher | multi-round |
| Synthesis (1) | Research Manager | |
| Execution (1) | Trader | action, price, size, targets, stops, catalysts |
| Control (1) | Risk Manager | liquidity / concentration / correlation / VaR — all `pass` |
| Verdict (1) | Fund Manager | `HOLD / ACCUMULATE $191–196 · conviction 7/10` |
| Trigger (1) | Manual Trigger / orchestrator | `horizon 2+ wks · book rules · 66 playbook` |

7 + 2 + 1 + 1 + 1 + 1 + 1 = **14**. The count checks out, which is decent evidence the reverse-engineering is right.

Metrics visible per analyst (use these as the required output schema):
- **Technical** — RSI, VWAP σ, SMA200, 3-month change, price TTM, DMI, YTD
- **Fundamentals** — fwd P/E, rev Q/Q, gross margin, ROE, FCF
- **Estimates** — analyst count, consensus rating, consensus target + implied %
- **Flow/Ownership** — short % float, institutional net, days to cover
- **Options** — ATM IV, cycle open interest, call/put volume ratio
- **Macro** — VIX y/y, QQQ/SPY relative, UST 10Y, DXY

Deep Dive also emits a **written thesis** (slide 4, FIG 03): blended DCF + exit-multiple + Monte Carlo, 20,000 paths, producing a 5-year bear/base/bull range, plus CAPM inputs (β, discount rate r, σ) and a DCF stress floor. Strengths/Threats bullets. Footer: `Education only — not financial advice`. **Reproduce that footer verbatim on every generated artifact.**

### W3 — Morning Screen (slide 5)
`day-gainers screener → playbook filter → bull/bear debate → sized trade ticket`

The playbook filter is the interesting bit and the least documented. Slide 5 shows a named ruleset (`EDGE_BREAKOUT_V2`) rejecting candidates with one-line reasons (`crypto bear risk → reject`, `event risk, low range → reject`) and passing others by theme. Slide 3's trigger node references `66 playbook`. `[INFERRED]` This is a user-authored YAML ruleset, not learned behaviour — implement it as data, not code.

Ticket schema from slide 5: `side · entry · stop · target · size · max risk %` + state `AWAITING YOUR GO`.

### What Hermes contributes
Not the trading logic — the *operating* layer: cron scheduling with skill attachment, persistent cross-session memory, session history, MCP client, and multi-channel delivery. The post's "not a static bot — a fund that gets smarter" claim rests on Hermes memory + skills accumulating across runs. Treat that as an aspiration to be measured, not a feature that exists on install.

---

## 2. Repos

```bash
# Fork these two to your org, then:
git clone git@github.com:<YOU>/TradingAgents.git   engine/
git clone git@github.com:<YOU>/hermes-agent.git    hermes/

# Do NOT fork OpenBB. Install it.
pip install openbb openbb-mcp-server yfinance
python -c "import openbb; openbb.build()"
```

Upstreams: `TauricResearch/TradingAgents` · `NousResearch/hermes-agent` · `OpenBB-finance/OpenBB`

**Install Hermes from the git installer, not PyPI** — PyPI has lagged the source release. Pin both forks to a specific SHA in `versions.lock` and record it; do not track `main`.

---

## 3. Target layout

```
the-desk/
├── engine/                     # fork of TradingAgents
│   └── tradingagents/
│       ├── agents/analysts/
│       │   ├── estimates.py    # NEW
│       │   ├── flow.py         # NEW
│       │   ├── options.py      # NEW
│       │   └── macro.py        # NEW
│       └── dataflows/
│           └── openbb_mcp.py   # NEW — replaces FinnHub as primary
├── desk/                       # NET-NEW. The real work is here.
│   ├── book.py                 # position CRUD, SQLite
│   ├── exit_rules.py           # deterministic rule engine
│   ├── screener.py             # day-gainers + universe filters
│   ├── playbook.py             # YAML ruleset loader/evaluator
│   ├── valuation.py            # DCF + CAPM + Monte Carlo (20k paths)
│   ├── ticket.py               # sizing, risk %, approval state machine
│   └── report.py               # thesis card renderer
├── playbooks/
│   └── edge_breakout_v2.yaml
├── hermes-skills/
│   ├── book-health/SKILL.md
│   ├── deep-dive/SKILL.md
│   └── morning-screen/SKILL.md
├── config/
│   ├── book.yaml               # positions, entries, stops, exit rules
│   └── desk.yaml               # models, thresholds, risk limits
└── tests/
```

`desk/` is roughly 60% of the build effort and has no upstream to inherit from. Budget accordingly.

---

## 4. Data model

```sql
positions(id, ticker, qty, entry_price, cost_basis, stop, target,
          opened_at, thesis_run_id, status)
exit_rules(id, position_id, kind, threshold, armed, note)
runs(id, workflow, ticker, started_at, finished_at, model, token_cost, status)
agent_outputs(id, run_id, agent, payload_json, latency_ms)
verdicts(id, run_id, action, price_low, price_high, conviction, rationale)
tickets(id, run_id, ticker, side, entry, stop, target, size, max_risk_pct,
        state, created_at, decided_at,
        decided_by, decided_by_kind, approver_rule_id)
audit(id, ts, actor, actor_kind, action, subject, payload_json)
```

`decided_by_kind ∈ {HUMAN, RULE}` and `approver_rule_id` is null for human decisions. Both are unused in the initial build — every ticket is human-approved — and both exist so that autonomy is a property of *the approver*, not of the code path.

This is the autonomy ladder's only structural requirement, and it costs nothing now and a migration later. Rungs: human approves everything → rule auto-approves inside hard limits with human override → rule approves unsupervised. The state machine is identical at every rung; only the row in `decided_by_kind` changes. Nothing climbs a rung without a T8 number justifying it.

`tickets.state ∈ {AWAITING_APPROVAL, APPROVED, REJECTED, EXPIRED}`. Nothing transitions to APPROVED without a decision recorded in `audit`. Tickets expire after 24h by default — a stale sized ticket is a hazard.

Every agent output is persisted. Without `agent_outputs` you cannot debug a bad verdict, and you will get bad verdicts.

---

## 4.5 Book ingest — CSV, not API

Custodian is Wells Fargo. Their developer portal is commercial banking and open-banking payments; the retail brokerage side is reachable read-only through aggregators (Plaid, Akoya/SnapTrade) and those integrations explicitly **do not support placing trades**. Positions in, orders never out.

This is not a limitation to work around. It makes D5 structural rather than a policy choice, and it means the post's closing line — "wire in brokerage APIs and the desk trades 24/7" — is not available to you without moving custodians. Worth knowing before you build toward it.

### Two sources of truth, never merged blindly

| Source | Owns | Refresh |
|---|---|---|
| `imports/positions_YYYYMMDD.csv` (WF export) | ticker, quantity, cost basis, market value | each import |
| `config/book.yaml` (you) | stops, targets, exit rules, thesis link, horizon | manual |

A broker export contains what you hold. It does **not** contain why you hold it or when you'd leave — no stops, no targets, no thesis. Those are yours and they must survive re-import.

### `desk/ingest.py` contract

**Build order:** the canonical layer ships early (T3/T4 depend on having positions to reason about). Only the Wells Fargo *header adapter* is deferred to the end, because it needs a real export to be written against.

```
adapters/wells_fargo.py   ← LAST. ~20 lines. Maps WF headers → canonical.
        ↓
load(csv_path)
  → adapter normalizes headers (fail loudly on unrecognized columns;
    never silently drop one)
  → canonical schema: ticker, qty, cost_basis, market_value, account
  → reconcile against existing positions, matched on (ticker, account)
```

Everything below the adapter line is built and fully tested against synthetic fixtures in `tests/fixtures/positions_*.csv` written to the canonical schema. When the real export arrives, you write the mapping dict and nothing else changes. If adding the adapter requires touching reconciliation logic, the seam was drawn in the wrong place.

Reconciliation rules — these are the whole ballgame:

- **ticker in CSV, not in book** → new position, `status=UNMANAGED`, flagged in the next health report as needing stops before it can be evaluated
- **ticker in book, not in CSV** → position closed at the custodian. Do **not** delete. Mark `status=CLOSED`, retain thesis and run history.
- **both** → update qty and cost basis from CSV. **Never touch stops, targets, exit rules, or thesis_run_id.**
- **qty changed** → log to `audit`; a size change you didn't make through a ticket is worth surfacing
- always write the raw CSV to `imports/` unmodified; every reconciliation must be replayable

Add a `--dry-run` that prints the reconciliation diff and writes nothing. Make it the default and require `--commit` to persist. An import that silently clobbers a stop loss is the single most damaging bug this system can have.

### Staleness

Positions are as fresh as the last export. Stamp `book.last_import_at` and have W1 refuse to run — loudly, not silently — if the book is more than N days stale (default 3). A health report computed against a week-old book is worse than no health report, because it reads as current.

---

## 5. Build phases

Ship phases in order. Each phase must be green before the next starts.

### Phase 1 — Data layer
- OpenBB MCP server running, reachable, tools discoverable
- yfinance fallback with a shared interface so either source satisfies the same contract
- Cache with TTL; do not hit providers once per agent per run

**Done when:** one command pulls the full slide-3 metric set for NVDA from OpenBB, and the same command with `--fallback` returns the same shape from yfinance.

### Phase 2 — Book + exit rules (W1)
- `desk/ingest.py` — CSV import, header mapping, reconciliation, `--dry-run` default
- `config/book.yaml` → stops/targets/rules layered over imported positions
- Exit-rule engine covering at minimum: stop breach, trailing stop, time stop, thesis-invalidation flag, earnings-proximity alert
- Staleness guard
- Health report renderer

**Done when:** a seeded 5-position book produces `5× HOLD · 0 EXITS TRIGGERED`; flipping one stop above spot flips exactly one position to triggered; and re-importing a CSV with changed quantities preserves every stop and target. Write that last one as an explicit test — it's the regression that will actually bite you. Pure functions, no LLM, fully unit-tested.

### Phase 3 — Committee (W2)
- Four new analyst nodes wired into the LangGraph flow
- Bull/bear debate rounds configurable (default 2)
- Verdict schema with conviction 1–10

**Done when:** `python -m desk deep-dive NVDA` returns a structured verdict with all 14 agents reporting, and `agent_outputs` has 13 rows.

### Phase 4 — Valuation + thesis
- DCF, CAPM discount rate, exit-multiple, Monte Carlo (20k paths, seeded for reproducibility)
- Blended bear/base/bull range
- Thesis card with the not-financial-advice footer

**Done when:** two runs with the same seed and same input data produce identical numbers. If they don't, the Monte Carlo is wrong.

### Phase 5 — Screen + tickets (W3)
- Screener, playbook YAML evaluator with per-candidate reject reasons
- Position sizing from `max_risk_pct` and stop distance
- Approval state machine

**Done when:** the screener produces a ticket in `AWAITING_APPROVAL` and there is no code path — none — that moves it to APPROVED without a recorded human decision. Write a test that asserts this.

### Phase 6 — Hermes wiring
- Three skills, three cron jobs, Telegram delivery
- Memory: prior verdicts on a ticker load into context on the next run

**Done when:** cron fires W1 unattended and the report lands on your phone.

---

## 6. Known landmines

1. **Hermes cron × MCP.** There is a filed issue about cron jobs running in a separate environment that doesn't share MCP/plugin config. It appears resolved and the docs now document `--skill` attachment, but **verify on your pinned SHA before building Phase 6 on top of it.** If it bites, fall back to no-agent-mode cron invoking a CLI entrypoint.
2. **Cost.** 14 agents × 2 debate rounds × 3 workflows/day is not free. The "$0 software cost" claim covers licences, not tokens. Instrument `runs.token_cost` from day one and set a daily ceiling that hard-stops the cron. Use the cheap model for analysts, the expensive one only for debate, research manager, and verdict.
3. **Fable safeguards routing.** Some queries to `claude-fable-5` get served by Opus 5 instead. Log which model actually answered per agent call; don't assume the pin held.
4. **yfinance fragility.** It breaks on upstream HTML changes with no warning. This is why OpenBB is primary and yfinance is fallback, not the reverse.
5. **Lookahead in any backtest.** If you add backtesting later, news and estimates data are the usual leak vectors. Not in scope for this build.
6. **The screenshots are marketing.** The numbers in the post are one good run. A verdict of `HOLD/ACCUMULATE, conviction 7/10` is the system agreeing with a position the author already held. Build the eval harness in Phase 3 or you will have no way to distinguish a working committee from a fluent one.

---

## 7. Acceptance criteria

- [ ] `make setup` from clean clone → all three workflows runnable
- [ ] `make test` green; exit rules and sizing at 100% branch coverage
- [ ] Deep Dive on NVDA reproduces the slide-3 output *shape* (not values)
- [ ] Monte Carlo reproducible under a fixed seed
- [ ] No code path places a broker order
- [ ] No ticket reaches APPROVED without an `audit` row naming a human
- [ ] CSV re-import never mutates a stop, target, or exit rule
- [ ] Ingest defaults to `--dry-run`; unrecognized CSV headers fail loudly
- [ ] W1 refuses to run against a stale book
- [ ] Every generated artifact carries the education-only footer
- [ ] Daily token spend visible and capped
- [ ] Secrets in `.env`, `.env.example` committed, real `.env` gitignored

---

## 8. Explicitly out of scope

Broker integration · live order routing · backtesting · multi-user · web UI · anything touching real money.
