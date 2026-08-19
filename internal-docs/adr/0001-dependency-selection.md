# ADR 0001 — Dependency Selection for The Desk

- **Status:** **Proposed** — a human signs off. Nothing here is implemented.
- **Date:** 2026-08-18
- **Supersedes:** decisions D1–D3 in `internal-docs/DESK_DESIGN.md` §0, and the adopt lists in `internal-docs/TICKETS.md` T1/T2/T9/T11
- **Measurements:** [`0001-scoring.md`](0001-scoring.md) — every number below is traceable there

---

## Context

The Desk needs a dependency set chosen against three criteria, in priority order:

1. **Reliability** — maintained, tested, unlikely to break or be abandoned
2. **Dependency economy** — fewest distinct things relied on; candidates sharing transitive deps cost less together than apart
3. **Data subscription cost** — the budget being optimized (LLM token cost is out of scope; T14 handles it)

Weights applied: **reliability 40 · dependency economy 30 · subscription cost 30**.

**The vendor/depend distinction drives most of this.**

- **DEPEND** — installed by a package manager, upgraded over time, someone else's release cadence becomes our problem. Reliability metrics dominate: idle days, bus factor, release cadence, issue responsiveness.
- **VENDOR** — copied into our tree, becomes our code, upstream stops mattering at the moment of the copy. Popularity is nearly irrelevant. What matters is licence, test coverage, size, and how many packages that specific module drags in.

Classifying each candidate into the right mode turned out to be the highest-leverage judgement in this audit. The clearest case: `DanisHack/ai-hedge-fund` scores **59/100 as a DEPEND and 96/100 as a VENDOR**. Same repo, same measurements, same day. It is a bad dependency (185 days idle, bus factor 1, zero releases) and an excellent donor (MIT, **160** passing tests covering the modules taken, 1,853 relevant LOC, **zero net new packages**).

Star counts were used as one weak input and never as a tiebreak, per the brief. They earned their reputation here: the two most-starred candidates in the set — `TauricResearch/TradingAgents` (98.8k★) and `shiyu-coder/Kronos` (37.5k★) — are respectively the base we keep and the heaviest thing we refuse to install by default.

---

## Decision

Recommended set — **142 unique Python packages** total (134 core + `scipy` from the valuation vendoring + 7 from `financetoolkit`). Sum-of-parts would be 203 before those; shared transitive deps save 69.

> **Scores in this document were recomputed 2026-08-18 after an adversarial audit found four arithmetic errors.** [`score.py`](score.py) is now the source of truth; [`0001-scoring.md` §9](0001-scoring.md) records every remediation and **supersedes** earlier numbers where they differ.

| # | Item | Mode | Why, in one line |
|---|---|---|---|
| 1 | `TauricResearch/TradingAgents` @ pinned SHA (v0.3.1) | **VENDOR** (pinned fork) | Graph matches slide 3 1:1; all three claimed upstream features verified; **must install from git — the PyPI name is someone else's fork** |
| 2 | `DanisHack/ai-hedge-fund` — 11 modules, 1,853 LOC | **VENDOR** | **160** tests covering the taken modules verified passing on a clean checkout (342 repo-wide); MIT; adds **0 net new packages**. Survived active alternatives sweeps — see Decisions 2b and 2c |
| 2b | `financetoolkit` | **DEPEND** | Return-series stats, technicals, ratios, CAPM, implied vol. Supplies drawdown **duration** *and* **recovery time**, which T8 requires and DanisHack does not compute. **+7 packages — cheaper than `quantstats` and covers strictly more.** Superseded `quantstats` in Round 3 |
| 3 | `langgraph` | **DEPEND** | Already transitive via (1) — 0 net new packages |
| 4 | `litellm` | **DEPEND** | Gateway for all 14 agents; collapses most of T14 to config |
| 5 | `langfuse` | **DEPEND** | Per-step tracing in a 14-node graph; MIT core, self-hostable |
| 6 | `yfinance` | **DEPEND** | Measured: covers all but one required metric, free — **flagged for human decision, see below** |
| 7 | `finvizfinance` | **DEPEND — screener only** | Screener verified working; **its fundamentals scraper is broken today** |
| 8 | FRED (`fredgraph.csv` / API) | **DEPEND** (HTTP, no library) | Free, no key needed; the correct source for UST 10Y |
| 9 | SEC EDGAR (`data.sec.gov`) | **DEPEND** (HTTP, no library) | Free, 10 req/s, declared UA; XBRL fundamentals + 13F |
| 10 | `dafahentra/dcf-valuation-tool` — `dcf_engine.py`, 207 LOC | **VENDOR** | Canonical MIT; imports only numpy + scipy; **replaces the T9 pick, which is licence-blocked** |
| 11 | **FMP Starter — $19/mo** | subscription | Estimates VERIFIED at Starter (scoring §9.3). Premium's UK/CA and 30y history are redundant — yfinance gives 27y free. Scores 83.3 vs $0's 80.0 and $49's 80.6 |
| 12 | `NousResearch/hermes-agent` @ pinned SHA | **VENDOR** (pinned fork) | Per D2, unchanged — but see Consequences; its issue ratio is the worst measured |

**Dropped:** OpenBB and `openbb-mcp-server` (Phase 4 below) · QuantMind (fit gate below) · `virattt/ai-hedge-fund` · `bit-r/TradingAgents-AI-hedge-fund` · `td-02` as a code source · Alpha Vantage · Finnhub · Tiingo · EODHD · Polygon/Massive · Finviz Elite.

**Gated, not adopted:** Kronos — stays behind T8 exactly as T16 specifies, now with the number attached.

**Total monthly subscription cost: $19.**

---

## Options Considered

### Decision 1 — Committee engine

| Candidate | Days idle | Commits | Contributors | Releases/12mo | Licence | Score |
|---|---:|---:|---:|---:|---|---:|
| **TauricResearch/TradingAgents** | 31 | 257 | 19 | 8 | Apache-2.0 | **74** |
| virattt/ai-hedge-fund | 11 | 904 | 39 | 11 | MIT | 71 |
| DanisHack/ai-hedge-fund *as DEPEND* | 185 | 26 | **1** | 0 | MIT | 59 |
| DanisHack/ai-hedge-fund *as VENDOR* | — | — | — | — | MIT | **96** |
| td-02/ai-native-hedge-fund | 111 | 56 | 1 | 0 | **none** | disqualified |
| bit-r/TradingAgents-AI-hedge-fund | 115 | 149 (all inherited) | 19 (inherited) | 0 | Apache-2.0 | disqualified |

**Keep the current pick.** TradingAgents upstream stays the base. This is a null result and it is the cheapest outcome available.

All three of TICKETS.md's upstream claims verified in the checkout:

- decision log at `~/.tradingagents/memory/trading_memory.md` — `default_config.py:75`, exercised by `tests/test_memory_log.py`
- LangGraph checkpoint resume — `README:248`, `tests/test_checkpoint_resume.py`. **Correction: it is opt-in via `--checkpoint`, not on by default.** T13 must pass the flag.
- structured-output agents — `with_structured_output` in `agents/managers/portfolio_manager.py`, two dedicated test files

`bit-r` re-checked and re-rejected: 149 commits against upstream's 257, zero divergence, 0★, and a `pushed_at` of 2026-04-25 that *precedes* its own `created_at` of 2026-04-29 — the signature of a fork created after a push. The original diagnosis was right.

`DanisHack` re-checked against the fork-laundering pattern, since it shares a name with virattt's 62.9k★ repo and could plausibly be a re-uploaded copy rather than a GitHub-network fork. **It is not.** Layouts differ completely (`src/` vs `hedge_fund/`), and its history begins at its own `Initial commit`. TICKETS.md's "own network root" claim holds.

### Decision 2 — Which DanisHack modules, and what they cost

| Module | LOC | Ticket |
|---|---:|---|
| `backtest/{engine,metrics,portfolio_tracker,export,models,__init__}.py` | 868 | T4, T8 |
| `data/cache.py` | 49 | T2 |
| `paper_trading/state.py` | 129 | T3 |
| `agents/{risk_manager,portfolio_manager,macro_regime}.py` | 807 | T6, T12 |
| **Total** | **1,853** | |

Third-party packages those lines import: `numpy`, `pandas`, `pydantic`, `rich`, `langchain_core` — **all five already in the tree for other reasons. Net new: 0.** That is the T0 rule's ideal case.

The real cost is 22 intra-repo `src.*` imports needing rewiring to `desk.*`, plus the fact that DanisHack is built on Polygon.io while our data layer is not. TICKETS.md already names this as the hidden cost and it is correct to.

### Decision 2b — Is DanisHack actually the best donor? (Round 2 sweep)

The first pass verified the candidate list it was given but never ran the active discovery the brief asked for. Closed in Round 2. Full tables in [`0001-scoring.md` §7](0001-scoring.md).

**Axis 1 — better AI-desk repos. Null result.** Five GitHub searches sorted by `updated` as well as `stars` (so the sweep was not star-ranked) surfaced ~35 candidates not previously audited. Every one was rejected: wrong market (`TradingAgents-astock` 3,017★ A-share — **re-examined in depth, see below**; `RakshaQuant` NSE; `skopaqtrader` India; `cryptotrader-ai` crypto; `midas-agent` XAUUSD), forbidden scope (`AlpacaTradingAgent` 252★ — its differentiator is live order execution, which D5 forbids), or no licence at all (`AgentQuant` 172★, and the majority of the ~20 remaining 0★ `ai-hedge-fund` results, which are re-uploads of virattt's repo). **No US-equity donor beats DanisHack.**

**`TradingAgents-astock` — rejected on measurement, not on its description.** The first pass rejected it from its one-line summary, which was not good enough. Re-measured ([`0001-scoring.md` §7.10](0001-scoring.md)): it is Apache-2.0 with proper LICENSE + NOTICE + README attribution to upstream, and on cadence it **beats** upstream (9 days idle vs 31; 21 releases vs 8). It is rejected anyway because `dataflows/a_stock.py` is 2,463 LOC containing `_reject_non_a_share()`, which raises `ValueError` on any non-6-digit ticker — every US ticker — and because its three added analyst nodes (85–108 LOC each) are prompt templates whose entire substance is a tool list naming A-share-exclusive data: limit-up boards (needs a ±10% daily price limit), Stock Connect northbound flow (needs the HK Connect channel), and the 龙虎榜 dragon-tiger list (exchange-published named-brokerage-branch detail that US exchanges do not publish). `hot_money_tracker` looks like it might answer T6's missing **Flow/Ownership** node; it does not — it would need rewriting, not repointing.

**What the re-examination did surface: `quality_gate.py`.** 168 LOC, Apache-2.0, market-agnostic, wired as a graph node between the analysts and the debate. It grades every analyst report A–F before downstream nodes consume it, with a length floor (200 chars) and a `FAILURE_MARKERS` list catching `"I cannot retrieve"` / `"unable to fetch"` / `"无法获取"` — i.e. an LLM politely narrating that it *couldn't* get the data, which the pipeline would otherwise treat as a valid report. That is the third independent instance in this audit of the same silent-wrong-number class (`^TNX`, `qs.stats.win_rate`), and it speaks directly to DESK_DESIGN §6.6 and T7's rationale. **Read the pattern, don't vendor the code** — it has no tests, its strings are Chinese, and its field map is keyed to astock's seven analysts. Folded into T7 as ~40 lines against our own schema.

**Axis 2 — the reframe, and the actual error.** I scored DanisHack as one bundle. It is five unrelated donations, and one of them is a solved problem:

| Kind | LOC | Category-best library exists? |
|---|---:|---|
| Return-series stats (Sharpe, max DD, Calmar, benchmark) | ~120 | **Yes** |
| Trade-level stats (win rate, profit factor, expectancy) | ~92 | **No — structurally impossible from a returns series** |
| Discrete-position stepping + **deterministic no-LLM control arm** | 401 | No |
| Exit-rule precedence | 255 | No |
| Correlation-aware sizing | 390 | Wrong tool (see below) |
| Macro regime | 417 | No |

**The decisive measurement.** Running `empyrical-reloaded 0.5.12` and `quantstats 0.0.81` against 500 seeded synthetic returns:

| Capability | empyrical | quantstats | DanisHack |
|---|---|---|---|
| Sharpe / max DD / Calmar | ✅ | ✅ | ✅ hand-rolled |
| Alpha / beta vs benchmark | ✅ | ✅ | ⚠️ buy-and-hold only |
| **Drawdown duration** | ❌ | ✅ `days: 364` | ❌ |
| **Win rate / profit factor per round-trip trade** | ❌ | ⚠️ **per-PERIOD** | ✅ |
| **Expectancy net of costs** | ❌ | ❌ | ✅ |

**They are complementary, not competing.** Return statistics should be a library — 120 lines of hand-rolled Sharpe and Calmar is not where our edge is, and DanisHack does not compute the drawdown *duration* T8 explicitly demands. But `qs.stats.win_rate()` returned **0.5140** — the fraction of positive *days*, not of profitable *trades*. Right name, plausible number, wrong question. Swapping it in would produce a silently wrong autonomy gate, the same failure class as `^TNX`. The round-trip analysis stays.

**Why `quantstats` (83) over `empyrical-reloaded` (74.5),** despite empyrical costing 2 net-new packages against quantstats' 10: empyrical-reloaded is 248 days idle with **zero releases in 12 months**, and its upstream `quantopian/empyrical` has been dead **753 days**. quantstats is 29 days idle, 5 releases, 30 contributors, Apache-2.0 — and it is the one that has drawdown duration. Eight of its ten net-new packages are matplotlib/seaborn plotting we do not need; that is the real cost of this choice and reliability outweighs it at 40/30/30.

**Rejected with numbers:** `backtesting.py` (**AGPL-3.0**) · `backtrader` (**GPL-3.0**, 729 days idle — see Trade-offs) · `vectorbt` (**Apache-2.0 + Commons Clause**, non-OSI; **40 net-new packages, 652 MB**) · `nautilus_trader` (scores 84, rejected on fit — an event-driven live-execution platform, structurally opposed to D5) · `ffn`/`bt` (14/16 net-new incl. scikit-learn; weight-rebalancing model, not discrete tickets) · `PyPortfolioOpt`/`Riskfolio-Lib`/`skfolio` (solve mean-variance *allocation*; we need a correlation *cap*, which is 30 lines DanisHack already has) · `qlib` (478 open issues, 0 releases/12mo) · `zipline-reloaded` (223 days idle).

### Decision 2c — Round 3: the sweep redone properly

Rounds 1–2 concluded "no better donor exists" from a search too weak to support it. Full methodology post-mortem in [`0001-scoring.md` §8](0001-scoring.md). Four specific failures: I searched the **marketing category** (`"ai hedge fund"`) when what we take from DanisHack contains **zero LLM code**; `search/repositories` never matches code; no star bucketing, so the 0★ flood drowned the 50–5,000★ band; and several multi-word queries returned **zero results** without my noticing — a silent empty read as "nothing exists."

Redone with star-bucketed `topic:` queries across the *functional* categories (stop-loss engines · backtesting with costs · trade accounting · position sizing · paper-trading state · regime classification). Eight substantial repos surfaced that **none** of Round 2's queries could see.

**The find: `JerBouma/FinanceToolkit`** — 5,237★, MIT, **0 days idle**, 1,356 commits, 8 releases/12mo, **5 open issues (0.10 per 100★)**, created 2019, **94 test files**. The strongest reliability profile of anything in this audit.

| | Net-new packages | Drawdown duration | CAPM | Technicals | Implied vol |
|---|---:|---|---|---|---|
| `quantstats` | 10 | `days` only | ❌ | ❌ | ❌ |
| **`financetoolkit`** | **7** | **duration + recovery time** | ✅ | RSI, VWAP, SMA, DMI, MACD | ✅ |

It ships `fmp_model.py` **and** `yfinance_model.py` — natively supporting both our chosen providers — plus its own MCP server. Co-installation with the full recommended set: `pip check` → *"No broken requirements found"*, `tradingagents 0.3.1` and `financetoolkit 2.2.0` both import under the resolved `pandas 3.0.5`.

**`financetoolkit` replaces `quantstats`** (90.0 vs 83.0): cheaper, and it covers the T9 valuation CAPM plus enough of T6's indicator maths to cut hand-written code there.

**DanisHack survives unchanged.** And the `win_rate` trap is now three-way — DanisHack counts profitable **round-trip trades**, quantstats counts **positive periods** (0.5140), and FinanceToolkit counts *"periods in which the asset's return exceeds the benchmark's"*. One name, three incompatible meanings, all plausible-looking. Nothing measured replaces round-trip trade accounting, so T8's expectancy gate stays on DanisHack.

**Pandas 3.0 gate: cleared.** DanisHack's suite re-run under the `pandas 3.0.5` that `financetoolkit` forces — **342 passed, 3 warnings in 29.50s**, the same pre-existing `websockets`/`polygon` deprecations as the pandas 2.x run. Adopting `financetoolkit` does not break the DanisHack vendoring.

**Operator decision, 2026-08-18:** vendoring DanisHack is **confirmed** by the project owner. This resolves the donor question only — the remaining ADR items (OpenBB drop, T9 licence blocker, the $49 subscription, and the T19 yfinance/ToS call) are still **Proposed** and unsigned.

### Decision 3 — Valuation

| | EmanueleSturzo *(T9's pick)* | **dafahentra** *(recommended)* |
|---|---|---|
| Engine LOC | 749 | **207** |
| Engine imports | numpy, pandas, **yfinance**, warnings, json, os, argparse | **numpy, scipy** |
| Data coupling | yfinance called inside the model class; `risk_free_ticker="^TNX"` hardcoded | **none** — `calculate_value(p: dict)` |
| Monte Carlo | `monte_carlo(n_simulations=10000, seed=42)` | vectorized, caller-injected `rng` |
| Tests | **0** | **0** |
| Licence | **defective** | **canonical MIT** |
| Net new packages | 0 | +1 (`scipy`) |

**TICKETS.md T9 is not executable as written.** It says "Vendor EmanueleSturzo/DCF-Valuation-Model (MIT)". The LICENSE file is *titled* "MIT License" but its grant clause reads:

> `to use, copy, publish, distribute, sublicense, and/or sell`

Canonical MIT reads `to use, copy, **modify, merge**, publish, distribute, sublicense, and/or sell`. Both words are deleted, and the `WITHOUT WARRANTY` paragraph is absent entirely. This is why GitHub's classifier returns `NOASSERTION` rather than `MIT` — the metadata was telling us, and the README claim was believed instead.

T9 is *entirely* a modification task ("raise to 20,000 paths, add a fixed seed, replace its yfinance calls"). We do not have the right to do that.

Two smaller corrections while we are here: the seed already exists (`seed=42`), so "add a fixed seed" is done; and raising to 20,000 paths is a call-site argument, not a code edit. T9 was over-scoped and mis-licensed at the same time.

`dafahentra` is the better target on every axis that survives: a properly licensed 207-line engine with no data coupling at all, which is precisely the seam T9 wanted to create by hand. It costs one new package (`scipy`).

Both ship **zero tests**, so DESK_DESIGN Phase 4's reproducibility test is ours to write either way.

### Decision 4 — Data providers

Full coverage-by-cost matrix in [`0001-scoring.md` §3.2](0001-scoring.md). The decisive measurement is §3.3: a live `yfinance 1.6.0` call against NVDA returning **183 info fields**, including every fundamentals, estimates, flow and options metric DESK_DESIGN §1 W2 requires — options chains with `impliedVolatility`, `openInterest` and `volume`; `shortPercentOfFloat` and `shortRatio`; `numberOfAnalystOpinions`, `recommendationKey`, `targetMeanPrice`; and **6,934 daily bars (~27 years)** for the T8 backtest.

| Option | Monthly | Verdict |
|---|---:|---|
| **A** — yfinance + FRED + SEC + finviz(screener) | **$0** | Covers everything. Zero contractual guarantees. |
| **B** — A + FMP Premium | **$49** | **Recommended.** |
| C — A + FMP Ultimate | $99 | +13F holdings, +3,000 rpm. Not needed yet. |
| E — A + EODHD ALL-IN-ONE | $99.99 | Pays $100 and removes no dependency. |
| D — Finnhub All-In-One | **$3,500** | See below. |

**The cheapest set covering every required metric is $0/month.** That is the honest answer and it should be stated plainly rather than dressed up.

**The recommendation is $49/month anyway**, because coverage is not the thing being bought. Two measurements explain why:

- `^TNX` (UST 10Y) via yfinance returns **17 rows for `period="2y"`** and 16 rows for an explicit two-year `start`/`end` — but 1,254 rows for `period="5y"`. No exception. No warning. A macro analyst would compute "UST 10Y y/y" from three weeks of data and report it with full confidence. Mitigated here by routing UST 10Y to FRED (`DGS10`, **16,859 observations**, keyless) — but the class of failure is not mitigated, only this instance of it.
- `finvizfinance('NVDA').ticker_fundament()` raises `AttributeError: 'NoneType' object has no attribute 'find_all'` — reproducible on AAPL too. The library last shipped 226 days ago and its median first response on recent closed issues is **4,107 hours (171 days)**. TICKETS.md T2 assigns it "screener **+ fundamentals**"; the fundamentals half is broken today.

$49 buys a licensed second source for fundamentals, estimates and technicals, 30 years of history, and 750 rpm of documented headroom. It does **not** remove yfinance, because no provider measured sells options-chain IV *and* short interest below $99.99, and none sells both together under $3,500.

**Finnhub deserves a specific note** because DESK_DESIGN §3 still treats it as a primary. Its pricing has bifurcated: a market-data ladder at $49.99/$129.99/$199.99 that is **price and OHLC only**, and a fundamentals ladder that goes **free → $3,500/month with nothing in between**. The free tier has no financials, no estimates, no ownership and no OHLC history. Finnhub is unusable for The Desk at any price we would pay.

**Rate-limit headroom as cost, per the brief:** Alpha Vantage free allows **25 requests/day** and EODHD free allows **20/day**. Fourteen agents across three daily workflows exhaust either before the first Deep Dive completes. Both are disqualified on arithmetic.

### ⚠️ Flagged for human decision — not decided here

**yfinance and finvizfinance are free because they scrape.** Per the brief, this is stated and left to you:

- Neither has a commercial agreement with its data source. yfinance is an unofficial client for Yahoo Finance; finvizfinance parses finviz HTML.
- Both break silently on upstream markup changes. Both failure modes above are live instances, measured today, not hypotheticals.
- Terms-of-service for automated use are ambiguous for both. The Desk is self-hosted, single-user, education-only, places no orders, and redistributes nothing — which is the least exposed posture available — but "ambiguous" is not "permitted."
- Neither offers an SLA, a support channel with a useful response time (finvizfinance's median is 171 days), or any notice before breaking.

The paid alternative that removes the *most* exposure is Option C at **$99/month**, and even that leaves options chains and short interest on yfinance. **There is no configuration of paid providers measured here that removes yfinance from this system for less than $3,500/month.** If that is unacceptable, the required metric list in DESK_DESIGN §1 W2 has to shrink — specifically the Options and Flow/Ownership analysts — and that is a product decision, not a dependency one.

---

## Phase 4 — The OpenBB verdict

**Recommendation: DROP. `openbb` + `openbb-mcp-server` add 86 packages (+64% on a 134-package base) and 300 MB, are licensed AGPL-3.0-only, and serve zero required metrics that the chosen direct providers do not.**

### 1. Which required metrics does OpenBB serve that the direct providers don't?

**None.**

OpenBB is a normalization layer, not a data source. Its default install bundles 30 provider extensions — `benzinga, bls, cftc, commodity, congress_gov, crypto, currency, derivatives, econdb, economy, equity, etf, federal_reserve, fixedincome, fmp, fred, government_us, imf, imf_utils, index, intrinio, news, oecd, regulators, sec, tiingo, tradingeconomics, us_eia, uscongress, yfinance`.

Every one of those that serves a required metric for free is a provider we are already calling directly: **`yfinance`, `fred`, `sec`**. Every one that would add coverage is paid and would be billed separately on top of OpenBB — `fmp`, `intrinio`, `tiingo`, `benzinga`, `tradingeconomics`. OpenBB does not resell data; it wraps your keys. Installing it does not buy a single field.

The overlap matrix makes the redundancy exact: **`yfinance ∩ openbb = 23`** — *all 23* of yfinance's packages are already inside OpenBB's tree, because OpenBB ships `openbb-yfinance` and calls the same library we would.

### 2. Transitive dependency count and install size vs. calling providers directly

| | Packages | Install size |
|---|---:|---:|
| Core ops set alone | 96 | 400 MB |
| Core ops set + `openbb` + `openbb-mcp-server` | 190 | 519 MB |
| **Marginal cost of OpenBB** | **+94** | **+119 MB** |
| Against the full recommended set (134 pkgs) | **+86** | — |

It also tightens the Python ceiling from `<3.15` to `<3.14` (binding constraint: `openbb-polygon`).

### 3. Is the MCP server its only unique value? Quantify it.

The MCP server is OpenBB's only value here, and the saving it represents is small and one-time.

The argument for it is that it hands the agents a pre-built tool surface instead of us hand-writing tool definitions. But we are already writing `desk/data.py` as a provider-agnostic `MarketData` protocol (T2). The tools the committee needs are not "every OpenBB endpoint" — they are **one fetch function per analyst data need**, seven analyst nodes over the 26 metrics in DESK_DESIGN §1 W2. That is roughly **7–9 tool definitions**, written once, against an interface we control and must build regardless because T2 exists.

Against that saving: OpenBB's tool surface is generated from *its* schema, not ours, so every agent prompt couples to OpenBB's naming rather than to `desk/data.py`. That is the "abstraction beneath an abstraction" the brief suspected, and adopting it would partially defeat T2's purpose.

*(The exact OpenBB endpoint count is **not measured** — `obb.coverage` introspection failed with `module 'openbb' has no attribute '__version__'`. The 30 bundled extensions above came from the install log. The argument does not turn on the endpoint count, because the relevant number is how many tools *we* need, not how many OpenBB has.)*

### 4. The licence — the finding that settles it

**`openbb` 4.7.2 on PyPI is `AGPL-3.0-only`.** So is `openbb-mcp-server` 1.4.1, and so is every `openbb-*` provider extension checked (`openbb-yfinance`, `openbb-fmp`, `openbb-polygon`, `openbb-intrinio`, `openbb-tiingo`).

TICKETS.md T1 sets the rule: *"no AGPL code in the tree without a recorded decision."* It then names **Ghostfolio** as the AGPL risk — and Ghostfolio was already rejected for other reasons. The AGPL dependency that is actually in the plan, in DESK_DESIGN D3 and T1's install line, is OpenBB. That is a gap in the licence audit T1 was written to perform.

Whether AGPL §13's network-use clause binds a self-hosted single-user tool that serves nobody over a network is genuinely arguable, and I am not a lawyer. What is not arguable is that this repo is **public**, which puts the combined work squarely in the conveying case. This needs a recorded decision either way, and dropping OpenBB makes the decision unnecessary.

### 5. If dropped, what breaks — and the cost of adding it back

**Nothing breaks**, because nothing is built yet and OpenBB serves no unique metric.

Migration cost to add it back later: **one class.** T2's `MarketData` protocol exists exactly so that a backend can be added without touching callers — that is the same seam DESK_DESIGN §4.5 draws for the Wells Fargo adapter, applied to data. Adding OpenBB later means writing one more implementation of a protocol we will already have, and if adding it requires touching anything outside that class, the seam was drawn wrong and we would want to know.

**The number to attach: 86 packages and 119 MB to buy 0 metrics, 0 net capability, and 1 AGPL licence question, against a re-entry cost of 1 class.**

OpenBB is in the source post, which is a reason to examine it. Having examined it: drop.

---

## Phase 5 — QuantMind: the fit gate

**Recommendation: DROP on fit. Do not measure further, do not fold into the recommended set.** A null result here, as the brief allows.

The scoping question comes first: **does this system need a knowledge-extraction layer at all, and if so, which nodes consume it?**

Walking the 14 agents against DESK_DESIGN §1 W2:

| Node | Inputs | Structured? | Needs typed/cited/timestamped knowledge retrieval? |
|---|---|---|---|
| Technical | RSI, VWAP σ, SMA200, DMI, 3-mo, YTD | yes | no |
| Fundamentals | fwd P/E, rev Q/Q, gross margin, ROE, FCF | yes | no |
| Estimates | analyst count, consensus rating, target | yes | no |
| Flow/Ownership | short % float, institutional net, days to cover | yes | no |
| Options | ATM IV, cycle OI, call/put vol ratio | yes | no |
| Macro | VIX y/y, QQQ/SPY, UST 10Y, DXY | yes | no |
| **News/Sentiment** | headlines, social | **no** | **the only candidate** |
| Bull / Bear / Research Mgr / Trader / Risk / Fund Mgr / Trigger | outputs of the above | — | no |

**Twelve of fourteen nodes consume structured numeric data.** One consumes unstructured text. That single node — News/Sentiment — is the entire addressable surface, and upstream TradingAgents already ships a working path for it: `agents/analysts/news_analyst.py`, `sentiment_analyst.py`, `social_media_analyst.py`, fed by `dataflows/alpha_vantage_news.py`, `yfinance_news.py`, `reddit.py`, `stocktwits.py`.

QuantMind's stated purpose is refining **papers, news, and filings** into typed, cited, timestamped knowledge. Of those three: The Desk consumes no research papers; its news path already exists and works; and no node in the §1 W2 schema consumes filings *text* — the filings requirement is XBRL numbers, which SEC EDGAR serves structured for free (**1,009 filings** returned for NVDA in the live test).

So the honest answer is **no**. Adopting a knowledge-extraction framework to improve one of fourteen nodes, where that node already has a working data path, is not a fit.

The cost side confirms it without being the reason: QuantMind installed from its git checkout is **140 packages / 613 MB**, of which **69 are new** to our tree — `llama-index-core`, `llama-index-retrievers-bm25`, `bm25s`, `pymupdf`, `trafilatura`, `arxiv`, `openai-agents`, `ipykernel`/`ipython`, and a `full` extra pulling `sentence-transformers`. That is a **+51% package increase to serve 1/14 of the graph.**

Two things worth recording for whoever revisits this:

- The repo itself measures well — 3 days idle, 203 commits, 7 contributors, canonical MIT, 24,998 LOC, 54 test files. **This is a fit rejection, not a quality rejection.** If The Desk ever grows a research-synthesis workflow (W4), reopen it.
- **`pip install quantmind` does not install QuantMind.** PyPI `quantmind` 0.1.0 is an empty placeholder: **1 package, 48 KB, zero dependencies**, while the repo's own `pyproject.toml` declares version 0.2.0 with 16 direct dependencies. Anyone acting on a "pip install quantmind" instruction gets a shell and would not immediately notice.

---

## Kronos — standalone line item, still gated

Reported separately per T16. **Not folded into the recommended set. T16's gating is correct and should stand.**

| Measurement | Value |
|---|---|
| Stars / forks | 37,500 / 6,235 (TICKETS said 36.5k — drifted up) |
| Days idle | **127** |
| Total commits | 76 |
| Contributors | 18 (top contributor 36 of 73 = 49%) |
| Releases | **0, ever** |
| Open issues | **264** (TICKETS said 204) |
| Licence | MIT |
| **Dependency footprint** | **44 packages, 987 MB** |
| **Net new packages vs recommended set** | **+14** |

The install-size number is the one T16 asked for and it makes the argument concrete: **987 MB** for `torch`, `transformers`, `matplotlib`, `sympy`, `networkx`, `safetensors` and friends — roughly **2.4× the entire core ops set (400 MB)** for a single optional analyst node. On macOS arm64 that is a CPU-only torch wheel; a Linux CUDA build is larger.

Interestingly the *package count* cost is mild (+14, because litellm already pulls 19 of the 44), so this is a disk-and-class-of-dependency argument rather than a package-count one. Zero releases in 13 months and 264 open issues against 76 commits is the reliability picture.

Nothing changes about T16: gated behind T8, adopted only if it beats the deterministic baseline, deleted if it doesn't.

---

## Trade-off Analysis

**Where reliability and dependency economy conflicted, and what was chosen.**

**1. TradingAgents: economy lost to reliability, deliberately.** At 107 packages it is the single largest DEPEND in the set, and two of those packages — `backtrader` and `redis` — are **declared in `pyproject.toml` and never imported anywhere in the codebase**. A leaner engine would score better on criterion 2. Reliability won: the graph matches slide 3 one-to-one, all three claimed features verified in the checkout, Apache-2.0, 8 releases in 12 months. Rebuilding that graph to save packages would cost weeks to save megabytes.

**Correction to this ADR's earlier drafts — and a correction to that correction.**

Draft 1 called removing `backtrader`/`redis` "zero functional cost" housekeeping. Draft 2 escalated it to "a licence requirement … the same class of exposure as the OpenBB AGPL finding." **Both were wrong, and the second was wrong in a way that flattered this ADR's own headline finding.** The adversarial audit caught it; the corrected position:

- **Installing a copyleft package into a local virtualenv is not conveying it.** `backtrader` 1.9.78.123 is GPLv3+ and does land in the tree from an upstream `pyproject.toml` line — but nothing imports it, and publishing *our* source does not distribute *it*. The honest case for removal is **dead weight**: a 22.9k★ package, 729 days idle, zero imports. That is reason enough. It is not a copyleft exposure.
- **The same reasoning must apply to OpenBB, and I withheld it.** At T1 nothing imports OpenBB either, so the venv argument would equally deflate the AGPL finding. Applying an argument only where it favours my own recommendation is exactly the failure this audit is supposed to catch.

**OpenBB's exclusion survives, on the grounds that actually hold:** +86 packages (+64% on a 134-package base), +119 MB, **zero required metrics served that the direct providers don't**, and a tightened Python ceiling. Those are measured and decisive on their own.

The licence point survives too, but only in its correct and *stronger* form: the objection is not a package sitting in a venv — it is that `desk/data.py` would **import** OpenBB, and this repo is **public**, so we would be publishing source that forms a combined work with an AGPL-3.0 library. That is a real conveying argument. The venv framing was the weak one, and it was the one I used.

Consequently the Consequences/Action-Item criterion *"No AGPL package in the environment"* is **withdrawn** — it is unbounded across 142 packages and unverifiable by the `grep -Ei 'openbb|backtrader'` check offered alongside it. Replaced by the enforceable invariant in T1: **no distribution in the resolved environment carries a GPL/AGPL classifier, asserted by a test.**

**2. DanisHack: reliability lost to economy — but only because the mode changed.** As a DEPEND it is close to indefensible: 185 days idle, bus factor 1, no releases. Under the T0 rule, VENDOR mode makes upstream's cadence irrelevant, and what remains is a clean MIT licence, **160** verified-passing tests over the modules taken, and **0 net new packages** for 1,853 LOC. This is the trade the vendor/depend distinction exists to make. **The risk we accept: the day we copy those modules, we own them, and nobody upstream will fix a bug in them.** With 160 relevant tests coming along, that is an acceptable trade — and it is a genuine trade, not a free lunch.

**3. Data providers: economy and cost both lost to reliability, for $49/month.** Option A covers every required metric for **$0**. We are recommending $49 anyway. Strictly on criteria 2 and 3, that is the wrong call. Criterion 1 outranks both, and two measured live failures — `^TNX` returning 17 bars without an error, finvizfinance's fundamentals scraper throwing on every ticker — are what $49 is insuring against. **The uncomfortable part, stated plainly: $49 does not remove the fragile dependency. It only gives us somewhere to fail over to.** yfinance stays on the critical path for options and short interest at every price point below $3,500/month.

**4. OpenBB: the two criteria agreed, which is rare enough to note.** +86 packages is the worst economy score in the audit, and it serves no unique metric. Even re-weighted to reliability 60 / economy 10 / cost 30 it only reaches 79/100 — and the AGPL question is a licence matter that no weighting touches.

**5. The brief predicted this and was right.** "The most popular options in this space are also the heaviest." OpenBB: 72.0k★, +86 packages, dropped. Kronos: 37.5k★, 987 MB, gated. TradingAgents: 98.8k★, 107 packages, kept — because it is the one case where the weight buys something we cannot cheaply rebuild. And the highest-scoring single item in the whole audit is a **19-star repo with 0 forks** that nobody has touched in six months.

---

## Consequences

**Easier**

- One subscription, one invoice, $49/month. No API-key sprawl across five vendors.
- 134 packages instead of 220. Faster CI, smaller images, fewer CVE surfaces to track.
- No AGPL anywhere in the tree — T1's licence audit becomes a short document with a clean result.
- T9 drops further than TICKETS.md hoped: `dcf_engine.py` is 207 LOC with no data coupling, so "repoint at `desk/data.py`" is not a code change at all, just a caller that passes a dict.
- Vendoring DanisHack brings 160 passing tests (over the modules taken) into a repo that currently has none.

**Harder**

- **yfinance is on the critical path and it is fragile.** Two live failures measured today. Every `desk/data.py` call needs a sanity assertion — *specifically* a row-count floor on every historical series, which is the exact check that would have caught `^TNX`.
- **finvizfinance's fundamentals are broken now**, so T2 and T11 must be re-scoped to screener-only. Its 171-day median issue response means waiting for a fix is not a plan.
- Three vendored codebases means three sets of someone else's assumptions. TICKETS.md already flags this and is right; dropping OpenBB does not reduce it.
- We own the vendored code. No upstream will patch it.

**Needs revisiting**

- **When T8 produces expectancy numbers**, re-run this cost analysis. If the committee shows real edge, FMP Ultimate at $99 (13F holdings, 3,000 rpm) becomes cheap. If it doesn't, drop to $0 and stay on Option A.
- **If yfinance breaks in a way FRED and FMP can't cover** — options or short interest — the choice is $3,500/month or removing the Options and Flow analysts. Decide which *before* it happens, not during.
- **Hermes-agent's 33,018 open issues (14.21 per 100 stars) is the worst ratio measured in this audit**, and its footprint is unmeasured because it installs from a git installer rather than PyPI. D2 is out of scope for this ADR and stands unchanged. It should get its own look before Phase 6 — DESK_DESIGN §6.1 already asks for a cron × MCP verification on the pinned SHA, and that is the natural place to do it.
- **The Python floor is 3.10 and the ceiling is 3.15** (binding: `litellm >=3.10,<3.15`). The measurement host runs 3.14 by default; pin CI to **3.11** to match DanisHack's verified matrix.

---

## Action Items

Diff-style against `internal-docs/TICKETS.md`. **That file is not modified by this ADR** — these are proposals for a human to apply.

**T1 — Scaffold, pinned forks, license audit**
```diff
- Evaluate bit-r/TradingAgents-AI-hedge-fund against TauricResearch/TradingAgents upstream
+ bit-r re-verified as a bare mirror (149 inherited commits, zero divergence,
+   pushed_at predates created_at). Base on upstream. No further evaluation needed.
- Install openbb, openbb-mcp-server, yfinance, finvizfinance, litellm
+ Install yfinance, finvizfinance, litellm, langfuse. DROP openbb + openbb-mcp-server
+   (+86 packages, +119 MB, 0 unique metrics, AGPL-3.0-only).
+ Install TradingAgents FROM GIT at a pinned SHA. Do NOT `pip install tradingagents` —
+   that PyPI name resolves to Mai0313/tradingagents (v0.7.0, MIT), not upstream
+   (v0.3.1, Apache-2.0).
+ LICENCE-CRITICAL: in our fork, delete the unused `backtrader` and `redis`
+   declarations from pyproject.toml. `backtrader` is GPLv3+ and IS currently
+   installed in the tree by `pip install git+TradingAgents`, from a declaration
+   no code imports. Public repo + GPL copyleft = the same exposure class as the
+   OpenBB AGPL finding. Verify after removal:
+     pip list | grep -Ei 'backtrader|redis'   # must return nothing
  Run a license audit ... record it in internal-docs/LICENSES.md
+ The audit must cover: OpenBB = AGPL-3.0-only (now moot if dropped);
+   EmanueleSturzo = defective MIT, no modify grant (see T9);
+   td-02 = NO LICENSE, all rights reserved, pattern-only.
+ Pin CI to Python 3.11 (floor 3.10 / ceiling 3.15, binding: litellm).
```

**T2 — Market data interface + LiteLLM gateway**
```diff
- MarketData protocol satisfied by OpenBB MCP (primary), yfinance (fallback),
-   and finvizfinance (screener + fundamentals)
+ MarketData protocol satisfied by yfinance (primary), FMP Premium (fallback),
+   FRED (macro/rates), SEC EDGAR (XBRL fundamentals + 13F),
+   and finvizfinance (SCREENER ONLY).
+ finvizfinance.ticker_fundament() raises AttributeError on every ticker tested
+   (NVDA, AAPL) as of 2026-08-18. Do not build fundamentals on it.
+ Route UST 10Y to FRED DGS10, never to yfinance ^TNX:
+   ^TNX history(period="2y") returns 17 rows instead of ~500, silently.
+ MANDATORY: every historical series gets a minimum-row-count assertion.
+   A short series must raise, not return. This is the check that catches ^TNX.
```

**T4 — Exit-rule engine** · **T8 — Eval harness** · **T12 — Ticket sizing**
```diff
+ DanisHack vendoring CONFIRMED by measurement: 160 of the repo's 342 tests
+   cover the 11 taken modules; all 160 pass in isolation in 3.55s (342 passed
+   on a clean py3.11 checkout; canonical MIT; 1,853 LOC across the target
+   modules; 0 net new packages (numpy/pandas/pydantic/rich/langchain_core
+   are all already in the tree).
+ Port the tests alongside the code — they are the reason this vendoring is safe.
+ Survived an active alternatives sweep (~35 repos + 14 category libraries).
+
+ T8 SPLIT — metrics.py is two jobs, not one:
+   (a) RETURN-SERIES stats -> adopt `financetoolkit` (MIT), do NOT hand-roll.
+       get_max_drawdown_duration + get_max_drawdown_recovery_time — T8 requires
+       duration and DanisHack's metrics.py does not compute it.
+       Also: get_jensens_alpha / get_beta vs SPY (DanisHack's benchmark is
+       buy-and-hold only), get_capital_asset_pricing_model (feeds T9's WACC),
+       and RSI / VWAP / SMA / ADX(DMI) / MACD (cuts T6 hand-written indicators).
+       Chosen over `quantstats`: 7 net-new packages vs 10, covers strictly more,
+       0 days idle vs 29, 5 open issues, 94 test files, native fmp + yfinance models.
+       PANDAS 3.0 GATE: CLEARED. financetoolkit resolves pandas to 3.0.5.
+       Co-install clean (`pip check` passes; tradingagents 0.3.1 +
+       financetoolkit 2.2.0 both import), AND DanisHack's suite re-run under
+       pandas 3.0.5: "342 passed, 3 warnings in 29.50s". Same 3 pre-existing
+       websockets/polygon deprecations as the pandas 2.x run. No blocker.
+   (b) TRADE-LEVEL stats (win rate, profit factor, expectancy net of costs)
+       -> KEEP DanisHack's _analyze_trades. No library measured can do this:
+       these need round-trip trade records, not a returns series.
+
+ ⚠️ "win_rate" means THREE different things across the libraries measured.
+   DanisHack._analyze_trades  = fraction of profitable ROUND-TRIP TRADES  <- what T8 needs
+   quantstats.stats.win_rate  = fraction of POSITIVE PERIODS (measured: 0.5140)
+   financetoolkit.get_win_rate= fraction of periods BEATING THE BENCHMARK
+   All three return a plausible number under the same name. Substituting either
+   library version would silently corrupt the T8 autonomy gate.
+
+ Rejected alternatives (numbers in 0001-scoring.md §7):
+   backtesting.py = AGPL-3.0 | backtrader = GPL-3.0 + 729d idle
+   vectorbt = Commons Clause (non-OSI), 40 net-new pkgs, 652 MB
+   nautilus_trader = LGPL + live-execution platform, contradicts D5
+   ffn/bt = 14/16 net-new incl. scikit-learn; wrong position model
+   PyPortfolioOpt/Riskfolio/skfolio = solve allocation, we need a correlation cap
  T12: Adopt the hash-chained audit log pattern from td-02/ai-native-hedge-fund
+ td-02 has NO LICENSE FILE (all rights reserved). Pattern only — read for the
+   idea, write our own. Do not copy code. Record this in LICENSES.md.
```

**T6 — Analyst nodes**
```diff
+ Audit resolved for upstream: TradingAgents ships ONLY
+   fundamentals / market / news / sentiment / social_media analysts.
+   Estimates, Flow/Ownership, Options and Macro are all absent — the ticket's
+   guess that "Estimates and Macro probably exist" is wrong for upstream.
+ Macro: port DanisHack's agents/macro_regime.py (417 LOC).
+ Estimates, Flow/Ownership, Options: author. virattt not yet enumerated for these.
```

**T7 / T13 — Committee graph / Hermes cron**
```diff
+ Upstream checkpoint resume is OPT-IN via `--checkpoint`, not default.
+   The cron entrypoint must pass the flag or crash recovery silently won't happen.
+
+ ADD a quality gate node between the analysts and the bull/bear debate.
+   Pattern (read, don't vendor) from simonlin1212/TradingAgents-astock
+   tradingagents/agents/quality_gate.py — Apache-2.0, 168 LOC, no tests,
+   Chinese strings, field map keyed to its own 7 analysts. Portable core is
+   ~40 lines against our schema:
+     - grade each analyst report A-F before downstream nodes consume it
+     - reject empty; reject under a length floor (theirs: 200 chars)
+     - scan for LLM-failure markers ("I cannot retrieve", "I don't have
+       access", "unable to fetch") — an LLM narrating that it couldn't fetch
+       the data must NOT pass as a valid report
+   Rationale: DESK_DESIGN §6.6 (distinguish a working committee from a fluent
+   one) and T7 (failures hide in intermediate steps). A fluent
+   "I don't have access to that" is exactly a fluent non-answer.
+   Attribute in LICENSES.md as Apache-2.0-derived if any code is lifted.
```

**T9 — Valuation engine — REWRITE REQUIRED**
```diff
- Vendor EmanueleSturzo/DCF-Valuation-Model (MIT).
+ BLOCKED. Its LICENSE is titled "MIT License" but the grant clause omits
+   "modify" and "merge", and the warranty disclaimer is absent entirely.
+   GitHub classifies it NOASSERTION. T9 is entirely a modification task,
+   so we do not have the rights it requires.
+ Vendor dafahentra/dcf-valuation-tool instead (canonical MIT):
+   dcf_engine.py, 207 LOC, imports numpy + scipy only, zero data coupling
+   (calculate_value takes a params dict). Adds 1 package (scipy).
- Adapt: raise to 20,000 paths, add a fixed seed, replace its yfinance calls
+ Adapt: pass n=20,000 and an explicit np.random.default_rng(seed) at the call
+   site. No seed to add (EmanueleSturzo already had seed=42; dafahentra takes
+   an injected rng). No yfinance calls to replace — the engine has none.
+ Both candidates ship ZERO tests. Write the Phase-4 reproducibility test
+   ourselves; it is not inherited.
```

**T11 — Screener + playbook filter**
```diff
  Implement desk/screener.py on finvizfinance (day gainers, SMA crosses)
+ Screener VERIFIED working: Overview(signal="Top Gainers") returns 86 rows.
+ Scope to the screener only — ticker_fundament() is broken (see T2).
+ Library last released 2026-01-03 (226 days); median first issue response
+   4,107 hours (171 days). Assume no upstream fix. Own the fallback.
```

**T16 — Kronos**
```diff
+ Footprint measured: 44 packages, 987 MB (macOS arm64, CPU-only torch),
+   +14 net new packages vs the recommended set. ~2.4x the entire core ops set.
+ Stars now 37,500 (was 36.5k); open issues 264 (was 204); 127 days idle;
+   zero releases ever. Gating decision unchanged and correct.
```

**New — T18 · Data provider subscription**
```diff
+ Subscribe to FMP Premium, $49/mo billed annually.
+ BEFORE PURCHASE, verify one thing the pricing page did not resolve: that
+   analyst estimates / price-target consensus are included at Premium and not
+   held back to Ultimate. The plan card names "Full Fundamentals and Ratios"
+   but does not name Estimates, and the comparison table's per-tier legend
+   could not be extracted.
+ Do NOT subscribe to: Alpha Vantage (free tier 25 req/day), EODHD (20/day),
+   Finnhub (fundamentals ladder jumps free -> $3,500/mo with nothing between),
+   Tiingo (no fundamentals below a further add-on), Finviz Elite ($39.50/mo
+   for a screener the free library already serves).
```

**New — T19 · yfinance/finvizfinance ToS decision (human)**
```diff
+ Both are free because they scrape. Neither has a commercial agreement,
+   an SLA, or unambiguous terms for automated use. Two live breakages measured
+   on 2026-08-18 (see ADR "Flagged for human decision").
+ No paid configuration measured removes yfinance from this system for under
+   $3,500/mo — options-chain IV and short interest are the binding metrics.
+ Decision required: accept the risk, or cut the Options and Flow/Ownership
+   analysts from DESK_DESIGN §1 W2. This is a product call, not a dependency one.
```
