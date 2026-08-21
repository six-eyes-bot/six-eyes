# Superseded instructions

`internal-docs/TICKETS.md` and `internal-docs/DESK_DESIGN.md` are **frozen** — the T0 brief forbids editing them. Several of their instructions have since been overridden by [`adr/0001-dependency-selection.md`](adr/0001-dependency-selection.md) (**Accepted 2026-08-18**, merged in `90f399b`).

This file exists so the drift is greppable. **Where the two disagree, the ADR wins.**

*Last reconciled: 2026-08-21 against `main` @ ef220f5.*

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

## Added, with no ticket that owns them

| Item | Status |
|---|---|
| **Repointing `engine/dataflows/` at `desk/data.py`.** The ADR drops both OpenBB and Finnhub; frozen §3 assigned the engine's primary source to `openbb_mcp.py`, which will not exist. Upstream does ship `alpha_vantage`, `y_finance` and `fred` dataflows, so the engine is **not** dataless — but nothing assigns the repointing work. | **UNASSIGNED.** Not T1. Decide before T6. |
| **A quality-gate node** between the analysts and the bull/bear debate — grade each analyst report, reject empty/short ones and LLM-failure markers ("I cannot retrieve", "unable to fetch"). Pattern read from `simonlin1212/TradingAgents-astock` (Apache-2.0); ~40 lines against our schema. | Folded into **T7**. Attribute if code is lifted. |
| **T8 must annualise Sharpe explicitly** and assert the convention in a test. `financetoolkit.get_sharpe_ratio` is per-period; `empyrical`/`quantstats` annualise. 15.88× apart under an identical name. | **T8** |
| **`rev Q/Q` is single-sourced on yfinance** at the $19 FMP tier (Starter is *annual* fundamentals). A licensed fallback for it costs $49. | Accepted caveat. Revisit at T18. |

## Not decided by the ADR

- **T18** — the FMP Starter subscription is recommended, not purchased.
- **T19** — the yfinance / finvizfinance terms-of-service question. No paid configuration measured removes yfinance from this system below $3,500/month.
