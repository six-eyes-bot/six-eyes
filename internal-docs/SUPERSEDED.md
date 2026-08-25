# Superseded instructions

`internal-docs/TICKETS.md` and `internal-docs/DESK_DESIGN.md` are **frozen** — the T0 brief forbids editing them. Several of their instructions have since been overridden by [`adr/0001-dependency-selection.md`](adr/0001-dependency-selection.md) (**Accepted 2026-08-18**, merged in `90f399b`).

This file exists so the drift is greppable. **Where the two disagree, the ADR wins.**

*Last reconciled: 2026-08-21 against `main` @ f10a839.*

---

## Overridden

| Frozen doc says | ADR says instead | Why |
|---|---|---|
| **DESK_DESIGN §0 D3** — market data is `openbb` + `openbb-mcp-server`, yfinance fallback | yfinance primary · FMP Starter fallback · FRED · SEC EDGAR · finvizfinance (screener only). **No OpenBB.** | AGPL-3.0-only; +86 packages; serves zero required metrics the direct providers don't |
| **DESK_DESIGN §2** — `pip install openbb openbb-mcp-server yfinance` and `openbb.build()` | Install the ADR set. OpenBB is not installed at all. | as above |
| **DESK_DESIGN §3** — `engine/tradingagents/dataflows/openbb_mcp.py` "NEW — replaces FinnHub as primary" | That module will not exist. Both OpenBB **and** Finnhub are dropped. | Finnhub's fundamentals ladder jumps free → $3,500/mo with nothing between |
| **DESK_DESIGN §3** — `desk/` tree lists no `data.py` | `desk/data.py` exists and ships in **T1** as a Protocol | It is the seam three vendored codebases repoint at |
| **DESK_DESIGN §5 Phase 1** — "OpenBB MCP server running, reachable, tools discoverable" | Not applicable. Phase 1's done-criterion is the yfinance/FMP path. | OpenBB dropped |
| **TICKETS T1** — "Install openbb, openbb-mcp-server, yfinance, finvizfinance, litellm" | yfinance · finvizfinance · litellm · langfuse · **financetoolkit**. No OpenBB. | ADR Decision table |
| **TICKETS T2** — "MarketData protocol satisfied by **OpenBB MCP (primary)**, yfinance (fallback)" | yfinance primary, **FMP Starter** fallback | ADR Decision 4 |
| **TICKETS T2 Done** — "a forced **OpenBB** failure surfaces a visible fallback" | Unsatisfiable as written. Substitute: a forced **yfinance** failure surfaces a visible FMP fallback. | OpenBB is not installed |
| **TICKETS T9** — "Vendor EmanueleSturzo/DCF-Valuation-Model (MIT)" | Vendor **`dafahentra/dcf-valuation-tool`** | EmanueleSturzo's licence omits the modify/merge grant; T9 is entirely a modification task |
| **TICKETS T9** — "add a fixed seed" / "replace its yfinance calls" | Neither applies to the substitute: `dafahentra`'s engine takes an injected `rng` and has no data-layer coupling | measured |
| **TICKETS T1** — implies `pip install tradingagents` | **Install from git at a pinned SHA.** The PyPI name resolves to `Mai0313/tradingagents` v0.7.0 MIT, not upstream v0.3.1 Apache-2.0 | supply chain |
| **TICKETS T13** — LangGraph checkpoint resume treated as automatic | It is **opt-in via `--checkpoint`**. The cron entrypoint must pass the flag. | verified in upstream README |

## Gaps WITHIN the frozen docs — §4 and §4.5 disagree with each other (T3)

These are not ADR overrides. They are places where DESK_DESIGN contradicts
itself, found while implementing T3. Resolved in `desk/db.py`, recorded here.

| # | Gap | Resolution |
|---|---|---|
| G1 | §4.5 reconciles on **`(ticker, account)`**, but §4's `positions(...)` has **no `account` column** | Added `account NOT NULL DEFAULT ''` with `UNIQUE (ticker, account)`. Without it the matching key cannot be expressed and the same ticker in two accounts collapses into one row — asserted by a test |
| G2 | §4.5 says stamp **`book.last_import_at`**; §4 defines no `book` table | Added `book_meta(key, value)`. `days_stale()` reads it for W1's staleness refusal (default 3 days) |
| G3 | `positions.status` values are never enumerated; §4.5 only uses `UNMANAGED` and `CLOSED` | `status ∈ {OPEN, UNMANAGED, CLOSED}` with a CHECK constraint. **OPEN** = imported *and* covered by `config/book.yaml`, i.e. it has the stops the exit-rule engine needs |

Also settled by T3: `runs.token_cost` (§4) is **one row per run with one model
column**, which cannot hold the per-agent, per-model cost of a ~16-call
committee. T2's per-call spend ledger lives outside this database and
`runs.token_cost == SpendLedger.total_for_run(run_id)`.

## Corrections to ADR 0001 itself, found in implementation (T6)

| ADR says | Measured | Resolution |
|---|---|---|
| **`langgraph` — "Already transitive via (1) — 0 net new packages"** (Decision table row 3) | **False as built.** That accounting assumed TradingAgents would be *installed*. T1 vendored it as source and deliberately omitted its `pyproject.toml` (VENDORING.md §4b), so the transitive dependencies never arrived. The engine was **inert**: all five of its analysts, its graph and its LLM clients failed to import | `langgraph`, `langchain-core` and `stockstats` added to `pyproject.toml` as **direct** dependencies. Measured 2026-08-21: **17 net-new packages**, 106 → 123 |
| the recommended set is **142 packages** | 123 after this change, so the ADR's own budget is **not exceeded** — it was never reached, because the vendoring dropped the transitive set | No re-scoring needed. Economy is better than the ADR assumed, not worse |

**Deliberately still absent: `langchain-anthropic`, `langchain-openai`, `langchain-google-genai`, `langchain-aws`.** The engine's full declaration would pull **38** net-new rather than 17; the extra 21 exist only for `engine/tradingagents/llm_clients/`, which is **redundant** — T2 routes every model call through litellm. Nothing on the analyst or graph path imports them. **T7 must route the committee through `desk/llm.py` rather than the engine's own clients**, or it will pull those 21 back in.

## T6 audit result — "port rather than write" had nothing to port

T6 says to audit the base fork and `virattt/ai-hedge-fund` before authoring.
Measured 2026-08-21:

| DESK_DESIGN §1 W2 analyst | Vendored engine | virattt | Verdict |
|---|---|---|---|
| Technical | `market_analyst.py` | — | exists |
| Fundamentals | `fundamentals_analyst.py` | — | exists |
| News/Sentiment | `news_` + `sentiment_` + `social_media_` | — | exists |
| Estimates | **absent** | **absent** | written |
| Flow/Ownership | **absent** | **absent** | written |
| Options | **absent** | **absent** | written |
| Macro | tools only (`macro_data_tools.py`), **no node** | **absent** | written |

**`virattt/ai-hedge-fund` no longer has analyst nodes at all.** At
`eff8a732` it has been restructured into a quant library: `hedge_fund/signals/`
holds investor personas (buffett, munger, graham, lynch, druckenmiller, pead),
plus `data/protocol.py`, `features/`, `backtesting/` and a TUI. The ADR
evaluated a differently-shaped repository. The ticket's guess that "Estimates
and Macro probably exist in one of the two trees already" was half right:
Macro has tools, neither has a node.

## Added, with no ticket that owns them

| Item | Status |
|---|---|
| ~~**Repointing `engine/dataflows/` at `desk/data.py`**~~ — **RESOLVED in T7.** `desk/data.py` serves six of the seven analysts (technical, fundamentals, estimates, flow/ownership, options, macro). News/sentiment uses the engine's own `yfinance_news` dataflow, because the MarketData Protocol has no news method and adding one is a T2 change. **Measured: that dataflow needs no API key.** Both paths are yfinance underneath — one provider reached two ways, not two providers, which is why this is acceptable rather than merely tolerated. The engine's five vendored analysts are **not used** by the committee graph at all. |
| ~~**A quality-gate node** between the analysts and the bull/bear debate~~ — **DONE in T7.** `desk/quality_gate.py`; pattern attributed, no code copied. |
| ~~**T8 must annualise Sharpe explicitly**~~ — **DONE.** `desk/eval_metrics.annualised_sharpe` states the convention in its name; `per_period_sharpe` exists only so a test can measure the gap. **Measured 2026-08-21: 15.87×**, matching the recorded 15.88×. DanisHack's own Sharpe is already annualised, so the concern did not apply to the port. | **T8 ✓** |
| **`rev Q/Q` is single-sourced on yfinance** at the $19 FMP tier (Starter is *annual* fundamentals). A licensed fallback for it costs $49. | Accepted caveat. Revisit at T18. |

## Corrections to an adopted upstream, found by the verification VENDORING.md required (T8)

`VENDORING.md` §6 says: "Where a ported module gates a real decision —
`_analyze_trades` feeding T8's expectancy number — verify it independently
against a hand-built fixture before trusting it." Done, at `6d7a3ab`:

    buy 1 @ 100, sell @ 110      ->    +$10
    buy 1000 @ 100, sell @ 95    ->  -$5,000
                                      net -$4,990

    DanisHack reports: win_rate 50.0%, profit_factor 2.00

**A profit factor of 2.00 for a strategy that lost $4,990.** Five defects:

| # | Defect | Consequence |
|---|---|---|
| 1 | a round trip is appended **once per FIFO match, unweighted by quantity** | a 1-share match counts as much as a 1000-share one |
| 2 | `profit_factor` sums **percentages**, not currency | meaningless across unequal position sizes |
| 3 | returns come from **raw trade prices** — gross, not net | contradicts T8's "after spread, slippage, and commission" |
| 4 | a **flat** round trip is counted as a loss | biases win rate down, inflates the loss side |
| 5 | a sell with **no matching buy is silently discarded** | short sales and data gaps vanish |

**Resolution: `_analyze_trades` is NOT ported.** `desk/eval_metrics.py`
computes expectancy in currency, quantity-weighted and net of costs.
DanisHack's Sharpe, drawdown and benchmark are sound and are used as written.
This does not reflect on the modules T4 took, which were verified separately.

## Not decided by the ADR

- **T18** — the FMP Starter subscription is recommended, not purchased.
- **T19** — the yfinance / finvizfinance terms-of-service question. No paid configuration measured removes yfinance from this system below $3,500/month.
