# 0001 — Dependency Selection: Raw Measurement Tables

**Companion to** [`0001-dependency-selection.md`](0001-dependency-selection.md).
**Measured:** 2026-08-18 (all `gh api` and web fetches on this date).
**Measurement host:** macOS 26.5 (darwin arm64), Python 3.11.14 (`/opt/homebrew/bin/python3.11`), pip 26.1.2.
**Weights:** reliability **40** · dependency economy **30** · subscription cost **30**.

Every number below is traceable to the command in its section header. Anything not obtained is written **not measured** — no estimates.

> **Platform caveat that affects one number only:** all install sizes are macOS arm64 wheels. The Kronos figure (§2.2) is a CPU-only `torch` wheel; a Linux CUDA build of the same set is larger. Every other package in this audit is pure-Python or ships comparable wheels across platforms.

---

## 1. Phase 1 — Repo reliability

### 1.1 Raw metadata

```
gh api repos/{owner}/{repo} --jq '{stars:.stargazers_count, forks:.forks_count, pushed:.pushed_at,
  open_issues:.open_issues_count, archived:.archived, license:.license.spdx_id, is_fork:.fork,
  parent:(.parent.full_name // "none")}'
```

| Repo | Stars | Forks | Open issues | Archived | License (API) | Fork? | Parent |
|---|---:|---:|---:|---|---|---|---|
| TauricResearch/TradingAgents | 98,782 | 19,041 | 365 | no | Apache-2.0 | no | — |
| virattt/ai-hedge-fund | 62,938 | 11,069 | 162 | no | MIT | no | — |
| DanisHack/ai-hedge-fund | 19 | 0 | 1 | no | MIT | no | — |
| td-02/ai-native-hedge-fund | 9 | 0 | 0 | no | **null** | no | — |
| bit-r/TradingAgents-AI-hedge-fund | 0 | 0 | 0 | no | Apache-2.0 | **yes** | TauricResearch/TradingAgents |
| EmanueleSturzo/DCF-Valuation-Model | 2 | 0 | 0 | no | **NOASSERTION** | no | — |
| dafahentra/dcf-valuation-tool | 5 | 2 | 0 | no | MIT | no | — |
| OpenBB-finance/OpenBB | 71,997 | 7,415 | 108 | no | NOASSERTION | no | — |
| ranaroussi/yfinance | 25,017 | 3,400 | 150 | no | Apache-2.0 | no | — |
| lit26/finvizfinance | 1,610 | 271 | 19 | no | MIT | no | — |
| BerriAI/litellm | 56,650 | 10,683 | 4,960 | no | NOASSERTION | no | — |
| langfuse/langfuse | 33,327 | 3,586 | 781 | no | NOASSERTION | no | — |
| NousResearch/hermes-agent | 232,383 | 46,329 | 33,018 | no | MIT | no | — |
| langchain-ai/langgraph | 39,937 | 6,724 | 699 | no | MIT | no | — |
| LLMQuant/quant-mind | 2,583 | 441 | 33 | no | MIT | no | — |
| shiyu-coder/Kronos | 37,500 | 6,235 | 264 | no | MIT | no | — |

### 1.2 Activity, bus factor, cadence, responsiveness

```
gh api repos/{r}/contributors?per_page=100 --jq 'length'
gh api -i repos/{r}/commits?per_page=1     # total via Link rel="last"
gh api repos/{r}/releases?per_page=100 --jq '[.[].published_at | select(. >= "2025-08-18")] | length'
# median hours to first comment, 12 most recent closed non-PR issues that received a comment
```

| Repo | Days idle | Total commits | Contributors | Top contributor share | Releases (12mo) | Open issues / 100★ | Median 1st response (h) |
|---|---:|---:|---:|---:|---:|---:|---:|
| TauricResearch/TradingAgents | 31 | 257 | 19 | 201/256 = 79% | 8 | 0.36 | n/a¹ |
| virattt/ai-hedge-fund | 11 | 904 | 39 | 815/884 = 92% | 11 | 0.25 | 0 |
| DanisHack/ai-hedge-fund | **185** | 26 | **1** | 26/26 = **100%** | **0** | 5.00 | n/a¹ |
| td-02/ai-native-hedge-fund | 111 | 56 | **1** | 100% | 0 | 0 | n/a¹ |
| EmanueleSturzo/DCF-Valuation-Model | 132 | 9 | **1** | 100% | 0 | 0 | n/a¹ |
| dafahentra/dcf-valuation-tool | 72 | 30 | **1** | 100% | 0 | 0 | n/a¹ |
| OpenBB-finance/OpenBB | 29 | 6,863 | 100+² | 1035/5320 = 19% | 10 | 0.15 | 3 |
| ranaroussi/yfinance | **5** | 1,935 | 100+² | 1076/1832 = 59% | 12 | 0.59 | 13 |
| lit26/finvizfinance | **226** | 424 | 18 | 378/416 = 91% | 2 | 1.17 | **4,107** (171 days) |
| BerriAI/litellm | 0 | 43,488 | 100+² | 15232/30848 = 49% | 100+³ | 8.75 | 0 |
| langfuse/langfuse | 0 | 8,616 | 100+² | 1623/8517 = 19% | 100+³ | 2.34 | n/a¹ |
| NousResearch/hermes-agent | 0 | 23,624 | 100+² | 8459/18414 = 46% | 28 | 14.21 | n/a¹ |
| langchain-ai/langgraph | 7 | 7,041 | 100+² | 2262/6849 = 33% | 100+³ | 1.75 | n/a¹ |
| LLMQuant/quant-mind | 3 | 203 | 7 | 134/198 = 68% | 0 (no releases) | 1.27 | 0 |
| shiyu-coder/Kronos | 127 | 76 | 18 | 36/73 = 49% | 0 (no releases) | 0.70 | n/a¹ |

¹ `n/a` = the 12 sampled recent closed issues had no comment, or the repo has no closed issues. Not a good score and not a bad one — no signal.
² `contributors?per_page=100` caps at 100; true count is ≥100. Percentages are of the first page only.
³ `releases?per_page=100` caps at 100; all 100 fell inside the 12-month window.

### 1.3 Fork / divergence check (the `bit-r` lesson, re-applied)

The T0 brief requires checking `parent` and comparing divergence for anything that might be a bare mirror.

| Repo | API `fork` | Verdict | Evidence |
|---|---|---|---|
| `bit-r/TradingAgents-AI-hedge-fund` | **true**, parent `TauricResearch/TradingAgents` | **Confirmed bare mirror. Reject.** | 149 commits vs upstream 257; 0★/0 forks; last push 2026-04-25 predates its own creation date of 2026-04-29 (a push-then-fork artifact). Contributor list (19, top 101) is upstream's, inherited. |
| `DanisHack/ai-hedge-fund` | false | **Not a fork of virattt. Genuinely original.** | Layout differs completely: DanisHack uses `src/…`, virattt uses `hedge_fund/…`. Full git history is 26 commits, all authored by one person 2026-02-11 → 2026-02-13, starting from `52ad4ee "Initial commit: AI hedge fund project structure"`. TICKETS.md's "own network root" claim **holds.** |

`git -C DanisHack_ai-hedge-fund log --oneline --format='%h %ad %an %s' --date=short` — 26 commits, 3 calendar days, single author `DanisHack <danishmohd3610@gmail.com>`, then silence for 185 days.

### 1.4 README claims put to the test

| Claim | Source | Result | Command |
|---|---|---|---|
| "342 tests" | TICKETS.md on DanisHack | **VERIFIED.** `342 tests collected`, `342 passed, 3 warnings in 13.05s` | `pip install -e ".[dev]"` in a clean py3.11 venv, then `pytest tests/ -q` |
| "CI on Py 3.11/3.12/3.13" | TICKETS.md on DanisHack | **VERIFIED.** `.github/workflows/ci.yml` matrix `["3.11","3.12","3.13"]`, ruff + pytest | `cat .github/workflows/ci.yml` |
| DanisHack MIT | TICKETS.md | **VERIFIED.** Full canonical MIT text incl. modify/merge grant and warranty disclaimer | `head LICENSE` |
| TradingAgents "v0.2.4" is current | TICKETS.md | **STALE.** Current tag is **v0.3.1**; tags run v0.1.0 → v0.3.1 | `git tag` |
| Upstream ships decision log at `~/.tradingagents/memory/trading_memory.md` | TICKETS.md | **VERIFIED.** `default_config.py:75` sets `memory_log_path` to exactly that; `tests/test_memory_log.py` exercises it | `grep -rn trading_memory` |
| Upstream ships LangGraph checkpoint resume via `--checkpoint` | TICKETS.md | **VERIFIED, with a correction: it is opt-in, not default.** README:248 "Checkpoint resume is opt-in via `--checkpoint`"; `tests/test_checkpoint_resume.py` exists | `grep -rn -- --checkpoint` |
| Upstream ships structured-output agents | TICKETS.md | **VERIFIED.** `with_structured_output` in `agents/managers/portfolio_manager.py`; `tests/test_structured_agents.py`, `test_structured_agent_prompts.py` | `grep -rln with_structured_output` |
| EmanueleSturzo is "MIT" | TICKETS.md T9 | **FALSE — see §1.5.** | `cat LICENSE` |
| EmanueleSturzo ships "a 10,000-run Monte Carlo" | TICKETS.md T9 | **VERIFIED and better than claimed.** `dcf_model.py:351 def monte_carlo(self, n_simulations=10000, seed=42)` — already seeded. T9's "add a fixed seed" is already done; "raise to 20,000 paths" is a call argument, not an edit. | `grep -n "def \|seed" dcf_model.py` |
| Kronos "36.5k★" | TICKETS.md T16 | Measured **37,500★** today (drifted up, claim was directionally right) | `gh api` |
| Kronos "204 open issues / 76 commits" | TICKETS.md T16 | Measured **264 open issues / 76 commits** | `gh api` |

### 1.5 License audit — three findings that change tickets

```
cat LICENSE   # per repo, compared against canonical MIT/Apache text
curl -s https://pypi.org/pypi/{pkg}/json | jq '.info.license_expression // .info.license'
```

| Item | Declared | Measured | Consequence |
|---|---|---|---|
| **`openbb` (PyPI 4.7.2)** | D3 makes it primary data layer | **`AGPL-3.0-only`** | T1's own rule is "no AGPL code in the tree without a recorded decision." T1 names *Ghostfolio* as the AGPL risk and misses OpenBB, which is the one actually in the default install list. `openbb-mcp-server` (1.4.1) and every `openbb-*` provider extension measured are also `AGPL-3.0-only`. See ADR Phase 4. |
| **`EmanueleSturzo/DCF-Valuation-Model`** | TICKETS.md T9: "MIT" | LICENSE is **titled** "MIT License" but the grant clause reads `to use, copy, publish, distribute, sublicense, and/or sell` — **"modify" and "merge" are deleted**, and the `WITHOUT WARRANTY` paragraph is **absent entirely**. This is why GitHub's classifier returns `NOASSERTION` rather than `MIT`. | T9 is *entirely* a modification task ("raise to 20,000 paths, add a fixed seed, replace its yfinance calls"). The licence as written does not grant the right to modify. **T9 as specified is not executable.** |
| **`td-02/ai-native-hedge-fund`** | TICKETS.md T12: "Adopt the hash-chained audit log pattern" | **No LICENSE file. API returns `null`.** Default = all rights reserved. | Reading it for the *idea* of hash-chaining is fine (ideas are not copyrightable). Copying any of its code is not. T12 already says "pattern," which is the correct framing — keep it that way and note the constraint in `LICENSES.md`. |

Clean licenses confirmed by reading the file: `dafahentra/dcf-valuation-tool` (canonical MIT, modify/merge present, warranty disclaimer present), `DanisHack/ai-hedge-fund` (canonical MIT), `TauricResearch/TradingAgents` (Apache-2.0).

### 1.6 Supply-chain finding: the PyPI name `tradingagents` is not upstream

```
curl -s https://pypi.org/pypi/tradingagents/json | jq '{version:.info.version, urls:.info.project_urls}'
→ {"version":"0.7.0","urls":{"Repository":"https://github.com/Mai0313/tradingagents"}}
```

| | Upstream repo | PyPI `tradingagents` |
|---|---|---|
| Owner | `TauricResearch` | `Mai0313` |
| Version | 0.3.1 (`pyproject.toml`) | 0.7.0 |
| License | Apache-2.0 | MIT |
| Python floor | `>=3.10` | `>=3.12` |

`pip install tradingagents` installs a **third party's fork**, not the audited upstream, at a higher version number that makes it look newer. Install must be from git at a pinned SHA.

### 1.7 Declared-but-unused dependencies in TradingAgents

```
grep -rn "backtrader\|import redis" tradingagents/ cli/ --include='*.py'   → no matches
```

`pyproject.toml` declares `backtrader>=1.9.78.123` and `redis>=6.2.0`. Neither is imported anywhere in the package. Both land in the install tree regardless. Confirmed present in the measured tree (§2.1). Removable in our fork at zero functional cost.

---

## 2. Phase 2 — Dependency footprint

### 2.1 Per-candidate isolated venv probe

```
/opt/homebrew/bin/python3.11 -m venv /tmp/probe-{name}
/tmp/probe-{name}/bin/pip install {pkg}
/tmp/probe-{name}/bin/pip list --format=json | jq length
du -sk /tmp/probe-{name}/lib/python3.11/site-packages
```

Counts exclude `pip`/`setuptools`/`wheel`. Sizes are `site-packages` delta over the empty venv.

| Probe | Packages | Install size | Python floor/ceiling |
|---|---:|---:|---|
| `yfinance` | 23 | 156 MB | none declared |
| `finvizfinance` | 14 | 136 MB | `>=3.9` |
| `langgraph` | 35 | 44 MB | `>=3.10` |
| `langfuse` | 26 | 37 MB | `>=3.10,<4.0` |
| `litellm` | 49 | 194 MB | `>=3.10,<3.15` |
| `quantmind` (PyPI 0.1.0) | **1** | **0.05 MB** | `>=3.8` |
| `openbb` | 98 | 228 MB | `>=3.10,<4` |
| `openbb` + `openbb-mcp-server` | 146 | 300 MB | `>=3.10,<4` |
| Kronos deps (`torch transformers einops matplotlib pandas tqdm huggingface_hub safetensors`) | 44 | **987 MB** | — |
| `git+TauricResearch/TradingAgents` | 107 | 368 MB | `>=3.10` |
| `quantmind` from git checkout (real 0.2.0) | 140 | 613 MB | `>=3.10` |
| **Core ops set**¹ | 96 | 400 MB | `>=3.10,<3.15` (binding: litellm) |
| **Core ops set + openbb + openbb-mcp-server** | 190 | 519 MB | `>=3.10,<3.14` (binding: `openbb-polygon`) |

¹ core ops set = `yfinance finvizfinance langgraph litellm langfuse langchain-anthropic pydantic pyyaml`

**PyPI `quantmind` 0.1.0 is an empty placeholder** — 1 package, 48 KB, zero dependencies. It is *not* the LLMQuant framework, whose own `pyproject.toml` says version 0.2.0 with 16 direct dependencies. Anyone following a "pip install quantmind" instruction gets a shell.

### 2.2 Overlap matrix — shared transitive packages

Cell = packages present in **both** probes. Diagonal = that probe's own total.

| | finviz | kronos | langfuse | langgraph | litellm | openbb+mcp | yfinance |
|---|---:|---:|---:|---:|---:|---:|---:|
| **finvizfinance** | 14 | 7 | 6 | 6 | 6 | 13 | 13 |
| **kronos** | 7 | 44 | 8 | 9 | 19 | 19 | 7 |
| **langfuse** | 6 | 8 | 26 | 15 | 15 | 17 | 7 |
| **langgraph** | 6 | 9 | 15 | 35 | 18 | 17 | 7 |
| **litellm** | 6 | 19 | 15 | 18 | 49 | 33 | 6 |
| **openbb+mcp** | 13 | 19 | 17 | 17 | 33 | 146 | 23 |
| **yfinance** | 13 | 7 | 7 | 7 | 6 | 23 | 23 |

Note `yfinance ∩ openbb = 23` — **all 23** of yfinance's packages are already inside OpenBB's tree (OpenBB bundles `openbb-yfinance`). Likewise `finvizfinance ∩ yfinance = 13` of 14.

### 2.3 Total unique packages for the whole recommended set

```
union of pip list across probes, minus pip/setuptools/wheel
```

| Set | Unique packages | Marginal cost |
|---|---:|---|
| TradingAgents (git) | 107 | — |
| Core ops set | 96 | — |
| **RECOMMENDED SET (union)** | **134** | sum-of-parts 203 → **overlap saves 69 packages** |
| + `openbb` + `openbb-mcp-server` | 220 | **+86 packages** (+64%) |
| + Kronos deps | 148 | +14 packages, **+987 MB** |
| + QuantMind (git) | 203 | **+69 packages** |

The recommended set's union install size was not measured as a single venv (components: TradingAgents 368 MB, core ops 400 MB, overlapping heavily). **Not measured.**

### 2.4 VENDOR candidates — module-level footprint

The T0 rule: *"A 300-line module pulling three packages is worse than a 600-line one pulling none."*

```
wc -l {modules}
grep -hE '^(import|from) ' {modules} | sed -E 's/^(from|import) ([a-z_]+).*/\2/' | sort | uniq -c
```

**DanisHack/ai-hedge-fund — modules TICKETS.md wants (T4, T8, T12, T2, T3):**

| Module | LOC | Ticket |
|---|---:|---|
| `src/backtest/engine.py` | 155 | T8 |
| `src/backtest/metrics.py` | 212 | T8 |
| `src/backtest/portfolio_tracker.py` | 255 | T4 |
| `src/backtest/export.py` | 139 | T8 |
| `src/backtest/models.py` | 93 | T8 |
| `src/backtest/__init__.py` | 14 | T8 |
| `src/data/cache.py` | 49 | T2 |
| `src/paper_trading/state.py` | 129 | T3 |
| `src/agents/risk_manager.py` | 265 | T12 |
| `src/agents/portfolio_manager.py` | 125 | T12 |
| `src/agents/macro_regime.py` | 417 | T6 |
| **Total** | **1,853** | |

Third-party packages those 1,853 lines drag in: **`numpy`, `pandas`, `pydantic`, `rich`, `langchain_core`** — 5 packages, **all five already in the recommended set** for other reasons. Net new packages from this vendoring: **0**. 22 intra-repo `src.*` imports need rewiring to `desk.*`; that is the integration cost TICKETS.md flags, and it is real.

Repo-wide: 76 Python files, 12,527 LOC, 28 test files, 342 tests, all passing.

**Valuation candidates:**

| | EmanueleSturzo/DCF-Valuation-Model | dafahentra/dcf-valuation-tool |
|---|---|---|
| Engine module | `dcf_model.py` — **749 LOC** | `dcf_engine.py` — **207 LOC** |
| Engine imports | `numpy, pandas, yfinance, warnings, json, os, argparse` | **`numpy, scipy`** — nothing else |
| Data coupling | **yfinance called from inside the model class**; `risk_free_ticker="^TNX"` hardcoded as a constructor default | **None.** `calculate_value(p: dict)` takes a params dict. Data fetching lives in a separate `beta_fetcher.py`. |
| Monte Carlo | `monte_carlo(n_simulations=10000, seed=42)` — seeded, in the library | `monte_carlo(..., rng=...)` — vectorized NumPy, rng injected by caller |
| CAPM / WACC | `_calc_wacc()` | `_compute_wacc()` + `_compute_wacc_vectorized()`, `rf`/`mp` as constructor args, beta clipped [0.3, 2.5] |
| Exit multiple | `_calc_terminal_value_exit_multiple(ev_ebitda_multiple=12.0)` | `TERMINAL_VALUE_EXIT_MULTIPLE = 15` fallback when WACC ≈ g |
| Tests in repo | **0** | **0** |
| License | **Defective — no modify/merge grant, no warranty disclaimer** (§1.5) | **Canonical MIT** |
| New packages if vendored | 0 (numpy/pandas/yfinance already present) | **+1 (`scipy`)** |

The `^TNX` default in EmanueleSturzo's constructor collides directly with the yfinance defect measured in §3.3.

---

## 3. Phase 3 — Data provider coverage and cost

### 3.1 Live pricing, fetched 2026-08-18

| Provider | Free tier | Paid tiers (USD/mo) | Source |
|---|---|---|---|
| **Alpha Vantage** | **25 requests/day** | 49.99 (75 rpm) · 99.99 (150) · 149.99 (300) · 199.99 (600) · 249.99 (1200) | alphavantage.co/premium/ |
| **Polygon → "Massive"** (polygon.io 301-redirects to massive.com) | 5 rpm, end-of-day, 2y history | 29 Starter (unlimited calls, 15-min delayed, 5y) · 79 Developer (10y) · 199 Advanced (real-time, 20y+, incl. Financials & Ratios) · **29 Financials & Ratios standalone** | massive.com/pricing |
| **Finnhub — fundamentals ladder** | 60 rpm, **US only, no financials, no estimates, no ownership, no OHLC history** | **$3,500/mo** All-In-One. *There is no tier between them.* | finnhub.io/pricing |
| **Finnhub — market-data ladder** | — | 49.99 Basic (150 rpm, 10y OHLC) · 129.99 Standard (300 rpm, 25y) · 199.99 Professional (900 rpm, 40y+). **Price/OHLC only — no fundamentals, no estimates.** | finnhub.io/pricing-stock-api-market-data |
| **Tiingo** | 50 req/hr, 1,000/day, 500 symbols/mo, EOD + IEX. **No fundamentals, no news.** | 30 Power (10k/hr, 100k/day; fundamentals a further paid add-on) | tiingo.com/pricing |
| **EODHD** | **20 calls/day.** No fundamentals, no live, no options, no indicators, no screener. | 19.99 EOD All-World · 29.99 EOD+Intraday · 59.99 Fundamentals feed · **99.99 ALL-IN-ONE** (only tier with options + screener) | eodhd.com/pricing |
| **FMP** | 250 calls/day, EOD, profile/reference | **19 Starter** (300 rpm, 5y, annual fundamentals, US) · **49 Premium** (750 rpm, 30y, full fundamentals + technical indicators + corporate calendars + DCF) · **99 Ultimate** (3,000 rpm, **13F institutional holdings**, full history) — prices billed annually | site.financialmodelingprep.com/developer/docs/pricing |
| **Finviz Elite** | web screener, delayed 15–20 min | **39.50/mo or 299.50/yr** — real-time, export/API access | finviz.com/elite.ashx |
| **SEC EDGAR** | **Free. 10 requests/second.** Declared `User-Agent` required. Data from 1994. | — | sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data |
| **FRED** | **Free.** API key free; `fredgraph.csv` path needs no key at all. | — | fred.stlouisfed.org/docs/api/terms_of_use.html — exact documented RPM **not measured** |
| **yfinance** | Free, unofficial/scraped, no published limit | — | — |

**Rate-limit headroom against 14 agents × 3 workflows/day:** Alpha Vantage free (25/day) and EODHD free (20/day) cannot serve a single Deep Dive run, let alone three workflows. Both free tiers are disqualified on arithmetic, not on quality. Tiingo free (1,000/day) has the headroom but carries no fundamentals.

### 3.2 Coverage-by-cost matrix

Rows = every metric DESK_DESIGN §1 W2 requires. **✅** = available at that cost. **💲** = available only at the priced tier shown. **❌** = absent from the provider entirely.

| Required metric | yfinance $0 | FRED $0 | SEC $0 | finviz-lib $0 | FMP | Massive | Finnhub | EODHD | AlphaV |
|---|---|---|---|---|---|---|---|---|---|
| **Technical** RSI, VWAP σ, SMA200, DMI, 3-mo, YTD | ✅ (from bars) | — | — | ⚠️ broken §3.3 | 💲$49 | ✅$29 (bars) | 💲$49.99 | 💲$19.99 | 💲$49.99 |
| **Fundamentals** fwd P/E, gross margin, ROE, FCF | ✅ | — | ✅ XBRL | ⚠️ broken | 💲$19 | 💲$29 | 💲**$3,500** | 💲$59.99 | 💲$49.99 |
| **Fundamentals** rev Q/Q | ⚠️ only `revenueGrowth` (YoY-quarterly); `revenueQuarterlyGrowth` **absent** | — | ✅ derivable | ⚠️ broken | 💲$19 | 💲$29 | 💲$3,500 | 💲$59.99 | 💲$49.99 |
| **Estimates** analyst count, consensus rating, consensus target | ✅ | — | ❌ | ⚠️ broken | 💲$49 | ❌ | 💲**$3,500** | ❌ | ❌ |
| **Flow** short % float, days to cover | ✅ | — | ❌ | ⚠️ broken | ❌ | ❌ | 💲$3,500 | ❌ | ❌ |
| **Flow** institutional net | ✅ | — | ✅ 13F | ⚠️ broken | 💲**$99** | ❌ | 💲$3,500 | ❌ | ❌ |
| **Options** ATM IV, open interest, call/put vol | ✅ | — | ❌ | ❌ | ❌ | 💲 Options plan, **not measured** | ❌ | 💲$99.99 | ❌ |
| **Macro** VIX y/y, QQQ/SPY relative | ✅ | ✅ | — | — | 💲$19 | ✅$29 | 💲$49.99 | 💲$19.99 | 💲$49.99 |
| **Macro** UST 10Y | ⚠️ **defective §3.3** | ✅ `DGS10` | — | — | 💲$19 | ❌ | ❌ | ❌ | ❌ |
| **Macro** DXY | ✅ | ✅ `DTWEXBGS` | — | — | ❌ | ❌ | ❌ | 💲$19.99 | 💲$49.99 |
| **Screener** day gainers, SMA-cross | ❌ | — | — | ✅ **working** | 💲$19 | ❌ | ❌ | 💲$99.99 | ❌ |
| **Backtest** long daily bar history | ✅ **6,934 bars (27y)** | — | — | — | 💲$49 (30y) | 💲$79 (10y) | 💲$49.99 (10y) | 💲$19.99 | 💲$49.99 |

### 3.3 Live coverage test — what yfinance actually returns

Not a claim from documentation. This is `yfinance 1.6.0` against `NVDA`, 2026-08-18.

```
/tmp/venv-yf/bin/python yftest.py
```

| Field | Result |
|---|---|
| `info` keys returned | 183 |
| `forwardPE` | 17.079645 |
| `grossMargins` | 0.74144995 |
| `returnOnEquity` | 1.14288 |
| `freeCashflow` | 46,335,873,024 |
| `revenueGrowth` | 0.852 |
| `revenueQuarterlyGrowth` | **`<<absent>>`** |
| `numberOfAnalystOpinions` | 58 |
| `recommendationKey` | `strong_buy` |
| `targetMeanPrice` | 302.82758 |
| `analyst_price_targets` | `{current: 219.255, high: 500.0, low: 180.0, mean: 302.83, median: 300.0}` |
| `shortPercentOfFloat` | 0.0126 |
| `sharesShort` | 292,667,375 |
| `shortRatio` (days to cover) | 2.23 |
| `heldPercentInstitutions` | 0.66192 |
| `institutional_holders` | DataFrame (10, 6) |
| `twoHundredDayAverage` | 195.03966 |
| `history(period="10y")` | (2,512, 7) |
| `history(period="max")` | **(6,934, 7)** — ~27 years |
| `options` expiries | 21 |
| `option_chain(...)` | calls (50, 14), puts (47, 14); `impliedVolatility` ✅, `openInterest` ✅, `volume` ✅ |
| `^VIX history(2y)` | (501, 7) |
| `QQQ history(2y)` | (500, 8) |
| `DX-Y.NYB history(2y)` | (502, 7) |
| `recommendations` | (4, 6) |
| `earnings_estimate` | (4, 7) |
| **`^TNX history(2y)`** | **(17, 7)** ⚠️ |

**The `^TNX` defect, isolated:**

| Call | Rows | First bar |
|---|---:|---|
| `^TNX history(period="2y")` | **17** | 2026-07-23 |
| `^TNX history(start="2024-08-01", end="2026-08-18")` | **16** | 2026-07-23 |
| `^TNX history(period="5y")` | 1,254 | 2021-08-18 |

Two of three call forms silently return ~3 weeks of data instead of two years — **no exception, no warning**. This is the precise failure mode DESK_DESIGN §6.4 warns about, caught in the act. A macro analyst computing "UST 10Y change" off 17 bars produces a confident wrong number.

Meanwhile `FRED DGS10` via `fredgraph.csv`, no API key: **16,859 observations**, last `2026-08-14, 4.68`.
And `SEC data.sec.gov/submissions/CIK0001045810.json` with a declared UA: `NVIDIA CORP`, **1,009 filings**.

### 3.4 Live test — finvizfinance

| Call | Result |
|---|---|
| `Overview().set_filter(signal="Top Gainers").screener_view()` | ✅ **(86, 10)** — works |
| `finvizfinance('NVDA').ticker_fundament()` | ❌ `AttributeError: 'NoneType' object has no attribute 'find_all'` |
| `finvizfinance('AAPL').ticker_fundament()` | ❌ same — **reproducible, not transient** |

The quote scraper is **broken today**. The screener is not. Library last released `v1.3.0` on 2026-01-03 (226 days ago); median first response on recent closed issues is **4,107 hours ≈ 171 days** (§1.2).

TICKETS.md T2 assigns finvizfinance "screener **+ fundamentals**". The fundamentals half does not currently run.

### 3.5 Cheapest set covering every required metric

| Option | Monthly | Coverage | Gaps |
|---|---:|---|---|
| **A. yfinance + FRED + SEC EDGAR + finvizfinance(screener only)** | **$0** | Every required metric except `revenueQuarterlyGrowth` (derivable from two `income_stmt` columns) | Scraping ToS ambiguity; `^TNX` defect (routed around via FRED); finviz fundamentals broken; no SLA on any of it |
| **B. A + FMP Premium** | **$49** | Same, plus a contractual second source for fundamentals/estimates/technicals, 30y history, 750 rpm | Still no options and no short interest from FMP — yfinance remains the only source for both |
| **C. A + FMP Ultimate** | **$99** | Adds 13F institutional holdings and 3,000 rpm | Same two gaps |
| **D. Finnhub All-In-One** | **$3,500** | Everything from one vendor | Absurd at this scale |
| **E. EODHD ALL-IN-ONE** | **$99.99** | Options + screener + fundamentals in one vendor | No analyst estimates or short interest ⇒ yfinance still required ⇒ pays $99.99 to remove nothing |

**Answer: the cheapest set that covers every required metric is $0/month — Option A.**

**Next tier up is Option B at $49/month.** What $49 buys is not coverage; it is a *contract*: a licensed fallback for fundamentals, estimates and technicals, 30 years of history, and 750 rpm of documented headroom. It does not remove the yfinance dependency, because **no provider measured here sells options-chain IV and short-interest data at any tier below $99.99, and no provider sells both together at any price under $3,500.**

That is the honest shape of this budget: coverage is free, and money buys reliability.

---

## 4. Weighted scoring

Sub-scores 0–10, then × weight ÷ 10. Weights: **reliability 40 · dependency economy 30 · subscription cost 30.** Max 100.

Rubric — **reliability**: days idle, bus factor, release cadence, responsiveness, licence validity, does-it-actually-run. **Dependency economy**: net *new* packages added to the recommended set (0 new = 10; ≥80 new = 0). **Subscription cost**: $0/mo = 10; each $50/mo ≈ −1.5.

### 4.1 Committee engine

| Candidate | Rel /10 | Econ /10 | Cost /10 | Weighted | Arithmetic |
|---|---:|---:|---:|---:|---|
| **TauricResearch/TradingAgents** | 8 | 6 | 10 | **80.0** | 8×4 + 6×3 + 10×3 = 32+18+30 |
| virattt/ai-hedge-fund | 8 | 5 | 10 | **77.0** | 32+15+30 · econ UNMEASURED · gated out on fit |
| DanisHack (as DEPEND) | 2 | 9.0 | 10 | **65.0** | 8+27+30 · econ now MEASURED: 8 net-new (§9.6) |
| **DanisHack (as VENDOR)** | **9** | **10** | 10 | **96.0** | 36+30+30 |
| td-02/ai-native-hedge-fund | 2 | — | — | **disqualified** | no licence (§1.5) |
| bit-r/TradingAgents-AI-hedge-fund | 0 | — | — | **disqualified** | bare mirror (§1.3) |

*TradingAgents reliability 8:* 31 days idle, 8 releases/12mo, 19 contributors, Apache-2.0, all three claimed features verified — docked 2 for 79% single-contributor concentration and 365 open issues.
*DanisHack as DEPEND scores 2:* 185 days idle, bus factor **1**, zero releases. *As VENDOR scores 9* because the T0 rule says upstream stops mattering the moment we copy — and what we copy is 1,853 LOC under a clean MIT licence with **342 tests that pass on a clean checkout** and **0 net new packages**. Docked 1 only for the `src.*` → `desk.*` rewiring.

**The mode is the decision.** Same repo, 59 vs 96, purely on how it's adopted.

### 4.2 Valuation

| Candidate | Rel /10 | Econ /10 | Cost /10 | Weighted | Note |
|---|---:|---:|---:|---:|---|
| **dafahentra/dcf-valuation-tool** | 7 | 9 | 10 | **85.0** | 28+27+30. Canonical MIT; 207-LOC engine; imports numpy+scipy only; +1 package |
| EmanueleSturzo/DCF-Valuation-Model | **0** | 10 | 10 | **60.0** | 0+30+30. **Licence forbids modification** (§1.5) — the score is irrelevant, it is blocked |
| Build from scratch | 10 | 10 | 10 | **100** | but costs the build effort T9 was trying to avoid |

Both third-party candidates ship **0 tests**. Whichever is vendored, we write the reproducibility test DESK_DESIGN Phase 4 demands.

### 4.3 Data providers

| Set | Rel /10 | Econ /10 | Cost /10 | Weighted |
|---|---:|---:|---:|---:|
| A — yfinance + FRED + SEC + finviz(screener) | 5 | 10 | 10 | **80.0** (20+30+30) |
| **B — A + FMP Premium $49** | **8** | 9 | 8.5 | **86.7** (32+27+25.5) |
| C — A + FMP Ultimate $99 | 8 | 9 | 7 | **80.0** (32+27+21) |
| E — A + EODHD ALL-IN-ONE $99.99 | 6 | 8 | 7 | **69.0** (24+24+21) |
| D — Finnhub All-In-One $3,500 | 9 | 10 | 0 | **66.0** (36+30+0) |

### 4.4 Ops layer

| Candidate | Rel /10 | Econ /10 | Cost /10 | Weighted | Note |
|---|---:|---:|---:|---:|---|
| LangGraph | 9 | 10 | 10 | **96.0** | already transitive via TradingAgents — 0 net new |
| LiteLLM | 8 | 7 | 10 | **83.0** | 0 days idle, 100+ releases/12mo; docked for 4,960 open issues (8.75/100★, worst measured) |
| Langfuse | 8 | 8 | 10 | **86.0** | 0 days idle; self-hostable; MIT core |
| Hermes-agent | 6 | — | 10 | **not scored on economy** | 0 days idle, 28 releases/12mo, but **33,018 open issues = 14.21/100★, the worst ratio in this audit.** Footprint not measured (git installer, not PyPI) |

### 4.5 Gated line items (scored, not folded into the set)

| Item | Rel /10 | Econ /10 | Cost /10 | Weighted | Verdict |
|---|---:|---:|---:|---:|---|
| **OpenBB + MCP server** | 8 | **0.0** | 10 | **62.0** (32+0+30) | **Drop.** +86 packages (+61% on 142), AGPL-3.0. econ by rubric (§9.1) |
| **Kronos** | 4 | **8.25** | 10 | **70.8** (16+24.75+30) | Stays gated behind T8 on reliability + install size, **not** on score. 127 days idle, 0 releases, 264 open issues; +14 packages but **+987 MB**, which the econ rubric does not price |
| **QuantMind** | 7 | **1.38** | 10 | **62.1** (28+4.14+30) | **Drop on fit** before economy matters — see ADR §Phase-5 |

---

## 5. Re-weighting worksheet

To re-weight without re-measuring, take the sub-scores above and apply new weights `(R, E, C)` summing to 100:

`score = R×(rel/10) + E×(econ/10) + C×(cost/10)`

Sub-scores that would move under a different weighting, and the raw number driving each:

| Item | rel | econ | cost | Raw driver of the econ score |
|---|---:|---:|---:|---|
| TradingAgents | 8 | 6 | 10 | 107 pkgs, 69 shared with core ops set |
| DanisHack (VENDOR) | 9 | 10 | 10 | **0 net new packages** for 1,853 LOC |
| dafahentra | 7 | 9 | 10 | +1 package (`scipy`) for 207 LOC |
| Data set B | 8 | 9 | 8.5 | $49/mo, no new packages |
| OpenBB | 8 | 1 | 10 | **+86 packages** on the 142-package recommended set |
| Kronos | 4 | 5 | 10 | +14 packages / +987 MB |
| QuantMind | 7 | 2 | 10 | +69 packages |

If dependency economy is re-weighted **down** to 10 (reliability 60, cost 30), OpenBB rises to 8×6 + 1×1 + 10×3 = **79.0** and becomes arguable. It does not become correct — the AGPL finding (§1.5) is a licence question, not a weight question, and no re-weighting touches it.

---

## 6. Not measured

Recorded so the human knows the edges of this audit.

- Union install size of the full recommended set as a single venv (components measured separately, §2.1).
- FRED's exact documented requests-per-minute limit — the ToS page fetched does not state it. Keyless `fredgraph.csv` access measured working.
- Massive/Polygon **Options** plan pricing — the Options tab did not render in the fetched page.
- FMP's per-tier attribution for *analyst estimates and price targets* specifically: the plan cards name "Full Fundamentals and Ratios" at Premium $49 but do not name Estimates; the comparison table is div-based and its per-tier legend did not extract. **Verify before purchase.**
- Hermes-agent transitive footprint — installed from a git installer rather than PyPI (DESK_DESIGN §2), not probed.
- OpenBB endpoint/tool count for the MCP argument — introspection failed (`module 'openbb' has no attribute '__version__'`); the **30 bundled provider extensions** were captured from the build log and are listed in the ADR.
- Whether virattt/ai-hedge-fund contains Estimates/Flow/Options/Macro analyst nodes (T6's open question). Upstream TradingAgents was checked and does **not** — its analysts are `fundamentals, market, news, sentiment, social_media`. virattt was cloned but not enumerated for this.
- Kronos install size on Linux/CUDA. The 987 MB figure is macOS arm64 CPU-only `torch`.

---

## 7. Round 2 — donor alternatives sweep (added 2026-08-18, same session)

Round 1 verified the candidate list it was given. It did **not** run the active discovery sweep the T0 brief asked for ("Search actively; the list is not exhaustive"). This section closes that gap and re-tests the DanisHack vendoring decision against alternatives.

### 7.1 Discovery — AI-desk repos not on the original list

```
gh api -X GET search/repositories -f q="<query>" -f sort=updated|stars -f order=desc -f per_page=15
```

Five queries run: `ai hedge fund llm agents`, `multi-agent LLM trading investment committee`, `LLM equity research analyst agent stocks`, `trading agents langgraph`, `investment research multi agent llm fundamentals valuation` — all `language:python`, sorted by **`updated`** as well as `stars` so the sweep was not star-ranked.

Everything surfaced that was not already audited:

| Repo | ★ | Pushed | Licence | Rejected because |
|---|---:|---|---|---|
| `simonlin1212/TradingAgents-astock` | 3,017 | 2026-08-09 | Apache-2.0 | A-share (China) data sources and market rules; wrong market |
| `huygiatrng/AlpacaTradingAgent` | 252 | 2026-07-18 | Apache-2.0 | Its differentiator is Alpaca **order execution** — forbidden by D5 |
| `OnePunchMonk/AgentQuant` | 172 | 2026-08-01 | **NONE** | No licence |
| `IvanWng97/TradingAgents-Telegram` | 45 | 2026-08-16 | MIT | Telegram wrapper over upstream; Hermes already covers delivery |
| `HimanshuMohanty-Git24/RakshaQuant` | 45 | 2026-07-27 | MIT | NSE (India) |
| `cy-Yin/TradingAgents-CN-lite` | 19 | 2026-05-31 | Apache-2.0 | A-share/HK focus |
| `Skopaq-AI/skopaqtrader` | 13 | 2026-08-13 | Apache-2.0 | Indian equities |
| `muye1202/VerumTrade` | 11 | 2026-06-29 | Apache-2.0 | 11★, 1 fork, no test evidence |
| `ronitg1/alpha-terminal` | 11 | 2026-07-15 | NOASSERTION | Licence unresolved |
| `ma-pony/cryptotrader-ai` | 11 | 2026-08-18 | MIT | Crypto |
| `andyluu98/midas-agent` | 7 | 2026-05-14 | Apache-2.0 | XAUUSD M15 scalping |
| `MunjPatel/AlphaCouncil` | 0 | 2025-11-21 | Apache-2.0 | 0★, 9 months idle |
| ~20 further `ai-hedge-fund` results | 0–2 | 2026 | mostly **NONE** | 0★ re-uploads of virattt's repo, majority unlicensed |

**Result: no US-equity donor found that beats DanisHack.** The niche is dominated by unlicensed 0★ re-uploads and by regional forks of TradingAgents for non-US markets — exactly the pattern the T0 brief predicted. This is a null result on the "better AI hedge fund repo" axis.

### 7.2 The reframe — DanisHack is five donations, not one

Round 1 scored DanisHack as a single bundle (96/100). That was the error. The eleven modules split into two structurally different kinds of work:

| Kind | Modules | LOC | Is there a category-best library? |
|---|---|---:|---|
| **Return-series statistics** | `metrics.py` (Sharpe, max DD, Calmar, benchmark alpha/beta) | ~120 of 212 | **Yes — a solved problem** |
| **Trade-level statistics** | `metrics.py::_analyze_trades` (win rate, profit factor, avg win/loss on round trips) | ~92 of 212 | **No — see 7.5** |
| **Discrete-position stepping + deterministic control arm** | `engine.py`, `models.py`, `export.py` | 401 | No library supplies the no-LLM control arm |
| **Exit-rule precedence** | `portfolio_tracker.py` | 255 | Idiosyncratic |
| **Correlation-aware sizing** | `risk_manager.py`, `portfolio_manager.py` | 390 | Partially — portfolio-optimisation libs |
| **Macro regime** | `macro_regime.py` | 417 | No |

### 7.3 Category-best candidates — reliability

```
gh api repos/{r} + /contributors + /releases   (same commands as §1.2)
```

| Repo | ★ | Days idle | Contributors | Releases/12mo | Open issues | Licence |
|---|---:|---:|---:|---:|---:|---|
| `ranaroussi/quantstats` | 7,559 | **29** | 30 | **5** | 31 | **Apache-2.0** |
| `pmorissette/ffn` | 2,635 | **5** | 38 | 3 | 6 | **MIT** |
| `pmorissette/bt` | 2,962 | 11 | 32 | 4 | 84 | **MIT** |
| `skfolio/skfolio` | 2,183 | 4 | 20 | **22** | 25 | BSD-3-Clause |
| `nautechsystems/nautilus_trader` | 26,218 | **0** | 100+ | 12 | 103 | **LGPL-3.0** |
| `robertmartin8/PyPortfolioOpt` | 5,968 | 42 | 45 | 1 | 112 | MIT |
| `dcajasn/Riskfolio-Lib` | 4,447 | 57 | 6 | 0 | 5 | BSD-3-Clause |
| `polakowo/vectorbt` | 8,713 | 16 | 21 | 4 | 136 | **Apache-2.0 + Commons Clause** |
| `kernc/backtesting.py` | 8,864 | 13 | 45 | **0** | 65 | **AGPL-3.0** |
| `stefan-jansen/zipline-reloaded` | 1,923 | 223 | 100+ | 0 | 43 | Apache-2.0 |
| `stefan-jansen/empyrical-reloaded` | 118 | 248 | 22 | **0** | 6 | Apache-2.0 |
| `quantopian/empyrical` | 1,506 | **753** | 15 | 0 | 37 | Apache-2.0 |
| `mementum/backtrader` | 22,880 | **729** | 48 | 0 | 63 | **GPL-3.0** |
| `microsoft/qlib` | 47,695 | 26 | 100+ | 0 | 478 | MIT |

### 7.4 Category-best candidates — footprint

Same probe method as §2.1. **Net-new** = packages not already in the 135-package recommended set (134 + `scipy` from the valuation vendoring).

| Package | Total pkgs | Install size | **Net-new** | What the net-new packages are |
|---|---:|---:|---:|---|
| `empyrical-reloaded` | 8 | 214 MB | **2** | `bottleneck`, itself |
| `quantstats` | 35 | 331 MB | **10** | itself, `tabulate`, `seaborn` + 7 matplotlib deps |
| `ffn` | 39 | 385 MB | 14 | + `scikit-learn`, `joblib`, `threadpoolctl`, `narwhals`, `decorator` |
| `bt` | 42 | 387 MB | 16 | all of ffn's + `bt`, `pyprind` |
| `nautilus_trader` | 15 | **510 MB** | **7** | Rust-backed monolith: few Python deps, large binary |
| `vectorbt` | 58 | **652 MB** | **40** | heaviest measured in this category |

### 7.5 The decisive measurement — do these libraries actually cover T8?

T8 requires: Sharpe · max drawdown **and its duration** · Calmar · win rate · profit factor · SPY benchmark · **expectancy net of spread, slippage and commission**.

```
/tmp/venv-metrics/bin/python metrictest.py   # empyrical-reloaded 0.5.12 + quantstats 0.0.81
# 500 synthetic daily returns, seeded rng(42)
```

| Capability | `empyrical-reloaded` | `quantstats` | DanisHack `metrics.py` |
|---|---|---|---|
| Sharpe | ✅ `0.6098` | ✅ | ✅ hand-rolled |
| Max drawdown | ✅ `-0.1395` | ✅ | ✅ hand-rolled |
| Calmar | ✅ `0.7130` | ✅ | ✅ hand-rolled |
| Alpha / beta vs benchmark | ✅ `[0.1178, -0.0099]` | ✅ | ⚠️ benchmark is buy-and-hold only, no alpha/beta |
| **Drawdown duration** | ❌ **absent** | ✅ **`drawdown_details` → `days: 364`** | ❌ **absent** (start/end indices only) |
| Public stat functions | 59 | 84 | — |
| **Win rate — per round-trip trade** | ❌ none | ⚠️ **per-PERIOD, not per-trade** | ✅ `_analyze_trades` |
| **Profit factor — per round-trip trade** | ❌ none | ⚠️ **per-PERIOD, not per-trade** | ✅ `_analyze_trades` |
| **Expectancy net of costs** | ❌ | ❌ | ✅ (+ commission/slippage in `engine.py`) |

**The trap, measured:** `qs.stats.win_rate(returns)` returned **0.5140** on the synthetic series. That is the fraction of positive *days*, not the fraction of profitable *trades*. `qs.stats.profit_factor` returned **1.1015** on the same per-period basis. Both have the right name, return a plausible number, and answer a different question than T8 asks. Swapping DanisHack's `_analyze_trades` for these would produce a silently wrong autonomy gate — the same failure class as the `^TNX` defect in §3.3.

**Conclusion: these are complementary, not competing.** Return-series statistics are a solved problem and should be a library. Trade-level statistics require round-trip records that a returns series does not contain, and no library measured supplies them.

### 7.6 Re-scored

| Option | Rel /10 | Econ /10 | Cost /10 | Weighted | Arithmetic |
|---|---:|---:|---:|---:|---|
| **DanisHack VENDOR — trade-level + engine + exit rules + sizing** | 9 | 10 | 10 | **96.0** | 36+30+30 |
| **`quantstats` DEPEND — return-series stats** | 8 | 7 | 10 | **83.0** | 32+21+30 |
| `empyrical-reloaded` DEPEND | 4 | 9.5 | 10 | **74.5** | 16+28.5+30 |
| DanisHack `metrics.py` return-stats half, unaided | 9 | 10 | 10 | 96.0 | **but fails T8 — no drawdown duration** |
| `ffn` | 8 | 5 | 10 | 77.0 | 32+15+30 |
| `bt` | 8 | 4 | 10 | 74.0 | 32+12+30 |
| `nautilus_trader` | 9 | **9.12** | 10 | **93.4** | 36+27.36+30 — the highest-scoring *rejected* candidate; **rejected on fit + LGPL, see 7.7** |
| `vectorbt` | 7 | **5.0** | 10 | 73.0 | 28+15+30 · Commons Clause, non-OSI |
| `backtesting.py` | — | — | — | **disqualified** | AGPL-3.0 |
| `backtrader` | — | — | — | **disqualified** | GPL-3.0 + 729 days idle |

`empyrical-reloaded` scores 4 on reliability: 248 days idle, **zero releases in 12 months**, 118★, and its upstream `quantopian/empyrical` has been dead for **753 days**. It is cheaper by 8 packages, and 8 of quantstats' 10 net-new packages are matplotlib/seaborn plotting we do not need. That is the genuine trade; reliability wins it under 40/30/30, and matplotlib is likely to arrive anyway via T10's thesis-card renderer.

### 7.7 Rejections with numbers attached

| Candidate | Rejected because |
|---|---|
| `kernc/backtesting.py` | **AGPL-3.0** — same rule that dropped OpenBB. Also 0 releases in 12 months. |
| `mementum/backtrader` | **GPL-3.0**, **729 days idle**. See 7.8 — it is already in our tree by accident. |
| `polakowo/vectorbt` | **Apache-2.0 + Commons Clause** — source-available, not OSI; forbids selling. Permissible for a private education-only desk but needs a recorded decision. Also **40 net-new packages, 652 MB** — worst economy measured. |
| `nautechsystems/nautilus_trader` | LGPL-3.0-or-later, and it is an **event-driven live-execution platform requiring a venue adapter** — structurally opposed to D5 (paper only, no broker). Scores well (84) on the formula; rejected on fit, which the formula does not measure. |
| `microsoft/qlib` | 478 open issues, 0 releases in 12 months; a full quant research platform, an order of magnitude beyond scope. |
| `ffn` / `bt` | Sound and MIT, but 14/16 net-new packages including `scikit-learn`, and `bt`'s weight-based rebalancing model does not match The Desk's discrete-ticket position model. |
| `PyPortfolioOpt` / `Riskfolio-Lib` / `skfolio` | Solve mean-variance **allocation**. The Desk needs a correlation **cap** (>0.7 over 60 days, group ≤40%), which is 30 lines DanisHack already has. Wrong tool. |
| `zipline-reloaded` | 223 days idle, 0 releases in 12 months. |
| `quantopian/empyrical` | **753 days idle.** Dead. |

### 7.8 Correction to Round 1 — `backtrader` is a licence problem, not housekeeping

Round 1 (§1.7) reported `backtrader` and `redis` as declared-but-unimported dependencies of TradingAgents and called removing them "zero functional cost." That understated it.

```
jq '.[]|select(.name|test("backtrader|redis";"i"))' probes/tradingagents-git.pkglist.json
→ backtrader 1.9.78.123
→ redis 8.1.0

curl -s https://pypi.org/pypi/backtrader/json | jq -r '.info.license'
→ GPLv3+
```

**`backtrader` is GPL-3.0 and it is installed in the tree today** by `pip install git+TauricResearch/TradingAgents`, purely from a `pyproject.toml` declaration that no code imports. GPL-3.0 is copyleft on distribution of a combined work, and this repo is public — the same class of exposure as the OpenBB AGPL finding, arriving through a dependency nobody chose.

Removing the declaration in our fork is therefore a **licence requirement, not tidiness**, and it is free: no code imports it.

### 7.9 Round 2 — not measured

- `nautilus_trader` was not evaluated for whether its backtest engine could run without a venue adapter; rejected on fit before that mattered.
- Whether `quantstats`' matplotlib dependency is genuinely shared with T10's thesis-card renderer — T10 is unbuilt, so the "matplotlib arrives anyway" argument is **an expectation, not a measurement**.
- `virattt/ai-hedge-fund` still not enumerated for Estimates/Flow/Options/Macro analyst nodes (carried over from Round 1 §6).
- Trade-level statistics libraries were searched for and none found; absence of evidence here is weaker than the positive measurements above.

### 7.10 Correction — `TradingAgents-astock` re-examined properly

Round 2 (§7.1) rejected `simonlin1212/TradingAgents-astock` as "A-share (China) data sources and market rules; wrong market." **That rejection was made from the repo's one-line description, not from its code** — the same "README claims are marketing" failure this audit exists to prevent, applied in reverse to dismiss a candidate. Re-measured below. The verdict holds; the reasoning did not, and re-doing it surfaced something worth keeping.

```
gh api repos/simonlin1212/TradingAgents-astock
git clone --depth 100 https://github.com/simonlin1212/TradingAgents-astock.git
```

| Metric | astock | upstream TradingAgents |
|---|---:|---:|
| Stars / forks | 3,017 / 790 | 98,782 / 19,041 |
| `fork` / `parent` | false / none (detached copy) | — |
| Created | 2026-05-13 | 2024-12-28 |
| Days idle | **9** | 31 |
| Releases in 12mo | **21** (≈7/month) | 8 |
| Contributors | 6 | 19 |
| Test files | 30 | 54 |
| Licence | Apache-2.0 | Apache-2.0 |
| Attribution | **LICENSE + NOTICE + README both credit `TauricResearch/TradingAgents`** — Apache-2.0 compliant, not a laundered fork | — |

**On cadence it beats upstream** (9 days idle vs 31; 21 releases vs 8). So "abandoned" is not the objection, and neither is licence hygiene.

#### Why the rejection nonetheless holds — measured, not assumed

**1. The data layer refuses US tickers by design.** `dataflows/a_stock.py` is **2,463 LOC** and contains:

```python
def _reject_non_a_share(original: str, code: str) -> None:
    if code.isdigit() and len(code) == 6:
        return
    ...
    if code and not code.isdigit():
        raise ValueError(f"'{original}' 不是 A 股代码 ...")
```

US tickers are alphabetic, so this raises on every one of them. Not incidental coupling — an explicit guard.

Worth noting *why* they added it, from the docstring: Chinese data sources return empty or "zombie" quotes for codes that don't exist rather than erroring, so the model would write a confident full report on data from the wrong market, and *"报告里完全看不出来"* — the report gives no sign of it. **That is the third independent instance in this audit of the same silent-wrong-number failure class** (`^TNX` §3.3, `qs.stats.win_rate` §7.5). Their fix is a hard guard at the data boundary, which is exactly the mitigation recommended for `desk/data.py`.

**2. The three added analyst nodes are prompt-thin; their substance is A-share-exclusive data.**

| Node | LOC | Tools it names | Portable? |
|---|---:|---|---|
| `hot_money_tracker.py` | 108 | `get_hot_stocks` (涨停 limit-up boards), `get_northbound_flow` (Stock Connect 沪股通/深股通), `get_dragon_tiger_board` (龙虎榜 named brokerage-seat detail), `get_fund_flow` (super-large/large/medium/small order tagging), `get_concept_blocks`, `get_industry_comparison` | **No** |
| `lockup_watcher.py` | 92 | `get_lockup_expiry` (限售解禁 restricted-share unlock calendar) | **No** |
| `policy_analyst.py` | 85 | `get_news`, `get_global_news` | **Yes — but generic** |

Each is essentially a prompt template plus a tool list. Remove the A-share tools and nothing remains. The specific data has no US equivalent at the mechanism level, not merely the vendor level: limit-up boards require a ±10% daily price limit; northbound flow requires the Hong Kong Connect channel; the dragon-tiger list is exchange-published named-brokerage-branch detail that US exchanges do not publish at all.

**This is the part I got wrong in the first pass and should have checked:** `hot_money_tracker` *sounds* like it might answer T6's missing **Flow/Ownership** node. It does not. It is not reusable node architecture — it is a prompt pointed at data that does not exist for US equities. The rejection is correct, but "wrong market" understates it: the node would have to be rewritten entirely, not repointed.

`policy_analyst` is genuinely market-agnostic (news tools only), but it is also the least useful of the three — The Desk's Macro analyst needs VIX / QQQ-SPY / UST 10Y / DXY *numbers* (§3.2), not policy-news synthesis.

#### What the re-examination did surface — `quality_gate.py`

Missed entirely on the first pass. **168 LOC, Apache-2.0, market-agnostic logic**, wired into the graph as a node named `"Quality Gate"` (`graph/setup.py:115,141`) sitting between the analysts and the bull/bear debate.

It grades every analyst report **A–F** before the debate consumes it:

```python
MIN_REPORT_LENGTH = 200
FAILURE_MARKERS = ["无法获取", "I cannot retrieve", "I don't have access",
                   "unable to fetch", "工具调用失败"]
```

`_hard_check_report()` returns `F` for empty, `D` for under 200 chars, and strips/counts failure markers — catching the case where an LLM *politely narrates that it could not fetch the data* and the pipeline treats that prose as a valid report.

That is directly on point for two things this project has already written down: DESK_DESIGN §6.6 (*"Build the eval harness in Phase 3 or you will have no way to distinguish a working committee from a fluent one"*) and T7's rationale (*"failures hide in intermediate steps rather than the final answer"*). A fluent "I don't have access to that data" is precisely a fluent non-answer.

**Caveats, measured:** `ls tests/ | grep -i qual` returns nothing — **there are no tests for it**. The `ANALYST_NAMES` map and all grade strings are Chinese. The `REPORT_FIELDS` map is keyed to astock's seven analysts, not ours.

**Recommendation: read it, don't vendor it.** The portable content is the *pattern* — hard-check analyst outputs for emptiness, length floor, and LLM-failure markers before downstream nodes consume them — which is perhaps 40 lines against our own schema. Attribute it in `LICENSES.md` as Apache-2.0-derived if any code is lifted. Fold into **T7**, alongside the Langfuse instrumentation.

**Net effect on the recommended set: none.** astock remains rejected as base or donor. One 168-LOC pattern moves into T7's scope.

---

## 8. Round 3 — corrected search methodology, and what it found

Rounds 1–2 concluded "no better donor exists" from a search that was too weak to support that conclusion. This section states the methodology explicitly, names its failures, and reports what a corrected sweep found.

### 8.1 What Round 2's methodology got wrong

| Flaw | Consequence |
|---|---|
| **Searched the marketing category, not the functional one.** Queried `"ai hedge fund llm agents"` when what we take from DanisHack contains **zero LLM code**. | Returned a hype niche of 0★ re-uploads; the noise was then reported as evidence of absence. |
| **`search/repositories` matches name / description / README only — never code.** | A repo with an excellent trailing-stop engine and a vague README is invisible. |
| **No star bucketing.** | The 0★ flood drowned the 50–5,000★ band where small well-made libraries live. |
| **Multi-word freeform queries.** GitHub ANDs the terms across name/description/README. | Several Round 2 queries returned **zero results** and that was not noticed — a silent empty result read as "nothing exists." |
| Five queries, 15 results each, one language filter. | Coverage far too thin for a negative conclusion. |

### 8.2 The methodology now used

1. **Decompose the target into functional categories** — what the code *does*, ignoring how the repo markets itself.
2. **Star-bucket every query** (`stars:15..8000`) to skip both the 0★ flood and mega-repo noise.
3. **Prefer `topic:` queries** — curated by maintainers, far higher signal than freeform text.
4. **Keep freeform queries to 2–3 words.** Long queries AND themselves into zero results.
5. **Try `search/code`** for implementation patterns invisible to README search.
6. **Measure survivors** on 40/30/30 + licence + a **co-installation test** against the existing set.

**Honest result of step 5:** code search produced almost pure noise here (`def trailing_stop`, `profit_factor def`, `def calculate_position_size` returned personal bot repos with no licence or tests). Recorded because it was tried, not because it worked.

### 8.3 The category DanisHack actually occupies

Not "AI hedge fund." After the §7.2 split, **no LLM code is taken from it at all**:

> **A deterministic paper-trading, exit-rule and trade-accounting library.**

Correct search categories: *stop-loss / trailing-stop engines · backtesting with transaction costs · round-trip trade accounting · position sizing and correlation caps · paper-trading state persistence · market-regime classification.*

### 8.4 What the corrected sweep surfaced

Queries: `topic:quantitative-finance`, `topic:algorithmic-trading`, `topic:financial-analysis`, `topic:risk-management`, `topic:position-sizing`, `topic:paper-trading`, `topic:backtesting-trading-strategies`, `topic:stop-loss`, each star-bucketed.

| Repo | ★ | Idle | Contrib | Commits | Rel/12mo | Open | Licence |
|---|---:|---:|---:|---:|---:|---:|---|
| **JerBouma/FinanceToolkit** | 5,237 | **0d** | 8 | 1,356 | 8 | **5** | **MIT** |
| coding-kitties/investing-algorithm-framework | 1,706 | 0d | 8 | 1,867 | 100 | 70 | Apache-2.0 |
| guy-hartstein/company-research-agent | 2,235 | 6d | 6 | 256 | 4 | 0 | Apache-2.0 |
| quarkfin/qf-lib | 953 | 13d | 15 | 786 | 4 | 12 | Apache-2.0 |
| quant-sentiment-ai/claude-equity-research | 693 | 1d | 5 | 20 | 0 | 0 | MIT |
| wshobson/maverick-mcp | 646 | 1d | 14 | 486 | 1 | 7 | MIT |
| tfukaza/harvest | 150 | 9d | 6 | 1,161 | 0 | 11 | MIT |
| The-Swarm-Corporation/AutoHedge | 4,218 | 99d | **2** | 37 | 0 | 17 | MIT |

**Every one of these was invisible to Round 2's queries.** None appeared under `"ai hedge fund"`.

### 8.5 `JerBouma/FinanceToolkit` — measured in full

Reliability is the strongest of any candidate in this entire audit: **0 days idle, 1,356 commits, 8 releases in 12 months, 5 open issues (0.10 per 100★), MIT, created 2019-04-08, 94 test files.**

**Footprint** — same probe method as §2.1:

| | Packages | Install size | **Net-new vs recommended set** |
|---|---:|---:|---:|
| `financetoolkit` 2.2.0 | 32 | 326 MB | **7** — `financetoolkit, scikit-learn, joblib, threadpoolctl, narwhals, openpyxl, et-xmlfile` |
| `quantstats` (for comparison) | 35 | 331 MB | 10 |

**It is cheaper than `quantstats` and covers strictly more.**

**Capability inventory** (`inspect.getmembers` over each model module):

| Module | Fns | Verified present |
|---|---:|---|
| `technicals.momentum_model` | 26 | `get_relative_strength_index` · `get_average_directional_index` (= DMI) · `get_moving_average_convergence_divergence` · `get_stochastic_oscillator` |
| `technicals.overlap_model` | 14 | `get_moving_average` (= SMA) · **`get_volume_weighted_average_price`** (= VWAP) · `get_exponential_moving_average` · `get_parabolic_sar` · `get_support_resistance_levels` |
| `ratios.profitability_model` | 23 | `get_return_on_equity` · `get_gross_margin` · `get_return_on_assets` |
| `ratios.valuation_model` | 29 | `get_price_to_earnings_ratio` |
| `performance.performance_model` | 56 | `get_sharpe_ratio` · `get_sortino_ratio` · `get_calmar_ratio` · `get_jensens_alpha` · `get_beta` · **`get_capital_asset_pricing_model`** · `get_treynor_ratio` |
| `risk.risk_model` | 26 | `get_max_drawdown` · **`get_max_drawdown_duration`** · **`get_max_drawdown_recovery_time`** · `get_ui` · `get_skewness` · `get_kurtosis` |
| `options.greeks_model` / `black_scholes_model` | 19 / 9 | **`get_implied_volatility`** + full greeks, binomial trees, SVI |

It also ships `fmp_model.py` **and** `yfinance_model.py` — natively supporting **both** of our chosen providers — plus its own `mcp_server/`.

**Co-installation test** (the gating question, given `pandas>=3.0`):

```
pip install git+TauricResearch/TradingAgents financetoolkit yfinance finvizfinance langgraph litellm langfuse
→ install exit=0
pip check → "No broken requirements found."
resolved: pandas 3.0.5 · numpy 2.4.6 · financetoolkit 2.2.0 · tradingagents 0.3.1 · scikit-learn 1.9.0
import pandas, tradingagents, financetoolkit → all OK
```

**Caveat resolved — the pandas 3.0 gate is now measured, and it passes.**

```
cd DanisHack_ai-hedge-fund
pip install -e '.[dev]' && pip install 'pandas==3.0.5'
pip list  → pandas 3.0.5 · numpy 2.4.6 · langchain-core 1.5.6 · pytest 9.1.1
pip check → "No broken requirements found."
pytest tests/ -q
→ 342 passed, 3 warnings in 29.50s
```

**All 342 DanisHack tests pass under pandas 3.0.5** — the version `financetoolkit` forces. Adopting `financetoolkit` does not break the DanisHack vendoring. The three warnings are pre-existing `websockets`/`polygon` deprecations, identical to the pandas 2.x run in §1.4, and unrelated to pandas.

### 8.6 The `win_rate` trap is now three-way

Reading the source of each:

| Library | `win_rate` means |
|---|---|
| DanisHack `_analyze_trades` | fraction of profitable **round-trip trades** |
| `quantstats.stats.win_rate` | fraction of **positive periods** (measured: 0.5140) |
| `financetoolkit …performance_model.get_win_rate` | *"percentage of periods in which the asset's return exceeds the benchmark's return"* — **benchmark-relative, per period** |

Three libraries, one function name, three mutually incompatible definitions, all returning a plausible number. **DanisHack's trade-level accounting survives every alternative examined.** T8's expectancy-net-of-costs gate must be computed from round-trip records, and nothing measured supplies that.

### 8.7 Revised recommendation

| Change | Rationale |
|---|---|
| **`financetoolkit` REPLACES `quantstats`** | 7 net-new packages vs 10; adds drawdown **duration** *and* **recovery time**; adds **CAPM** (which the T9 valuation vendoring needs); adds RSI/VWAP/SMA/DMI/MACD, reducing T6 hand-written indicator code; adds implied volatility. Reliability 0 days idle / 5 open issues / 8 releases / 94 test files. |
| **DanisHack vendoring UNCHANGED** | Trade-level accounting, exit-rule precedence and the deterministic control arm survive the sweep. |
| **Recommended set: 142 packages** | 134 core + `scipy` + 7 from `financetoolkit` |
| Subscription cost | **unchanged at $49/mo** — and FMP is `financetoolkit`'s native provider, so the two choices reinforce |

Scores: `financetoolkit` rel 9 · econ 8 · cost 10 → **9×4 + 8×3 + 10×3 = 90.0**, against `quantstats` **83.0**. <!-- sc:historical: pre-remediation score, corrected to 86.0 in 9.4 -->

### 8.8 Round 3 — not measured

- `coding-kitties/investing-algorithm-framework`, `qf-lib`, `harvest`, `maverick-mcp`, `claude-equity-research`, `company-research-agent` — surfaced and reliability-measured, **not** functionally evaluated. `maverick-mcp` (US stock analysis MCP server, MIT, 646★) is the most likely to be relevant given the OpenBB MCP drop, and is the first thing to look at if the MCP question is reopened.
- DanisHack's 342 tests under pandas 3.0.5 (see §8.5).
- `financetoolkit`'s numeric agreement with DanisHack's hand-rolled Sharpe/Calmar — not cross-checked.

### 8.9 Can `financetoolkit` replace DanisHack outright?

Asked directly, so tested directly rather than argued. Package-wide grep over the installed 2.2.0 tree:

```
grep -ril "<pattern>" site-packages/financetoolkit --include='*.py' | wc -l
```

| DanisHack core job | Pattern | Files in `financetoolkit` |
|---|---|---:|
| Fixed stop | `stop_loss` | **0** |
| Take-profit | `take_profit` | **0** |
| Position sizing | `position_size` | **0** |
| Slippage modelling | `def.*slippage` | **0** |
| Round-trip trade records | `round_trip` | **0** |
| Profit factor | `profit_factor` | **0** |
| Expectancy | `expectancy` | **0** |
| Trailing stop | `trailing` | 18 — **false positive** |
| Commission modelling | `commission` | 4 — **false positive** |

Both false positives checked rather than assumed:

- `trailing` → `trailing period` (122), `trailing window` (79), `trailing periods` (72), `trailing_eps` (9). **TTM analytics vocabulary, never a trailing stop.**
- `commission` → *"U.S. Commodity Futures Trading Commission"* (COT report docs) and `discountsAndCommissionsPerShare` (an IPO prospectus line item). **Never transaction-cost modelling.**

**Answer: no, and not partially.** `financetoolkit/portfolio/` exposes only `read_portfolio_dataset`, `format_portfolio_dataset`, `read_excel`, `read_yaml_file` — transaction-file ingestion and a performance overview, not position management. `risk/backtesting_model` is **VaR model validation** (Kupiec, Christoffersen, Acerbi-Szekely tests), not strategy backtesting.

The two occupy different layers and do not compete:

| | `financetoolkit` | DanisHack |
|---|---|---|
| Kind | **Analytics** — computes metrics *from* data | **Simulation + bookkeeping** — decides what happens *to* a position, and records it |
| Input | price / fundamental series | positions, rules, orders |
| Output | ratios, indicators, risk & performance statistics | exits fired, trades recorded, sizes assigned |
| T8 role | the return-series half | the trade-level half + the deterministic control arm |

### 8.10 Two further overlaps found while testing this

Not sought; found while enumerating `models/` and `economics/`.

**1. `models/wacc_model` + `models/intrinsic_model` partially overlap the T9 valuation vendoring.**

```
wacc_model:      get_cost_of_debt · get_cost_of_equity · get_weighted_average_cost_of_capital
intrinsic_model: get_intrinsic_value · get_gorden_growth_model · get_free_cash_flow_to_firm
                 get_free_cash_flow_to_equity · get_graham_number · get_residual_income
                 get_two_stage_dividend_discount_model
```

But source scan of `intrinsic_model`: `monte` **0** · `seed` **0** · `random` **0** · `simulat` **0** · `exit_multiple` **0** (`terminal` 31).

So it provides **WACC/CAPM and DCF point estimates but no Monte Carlo, no seeding, and no exit-multiple terminal value** — and DESK_DESIGN Phase 4 requires all three (*"20k paths, seeded for reproducibility"*, *"same seed → identical numbers"*). `dafahentra`'s 207-LOC engine supplies exactly the missing parts.

**Open question for the human, not decided here:** `dafahentra` could shrink to a Monte-Carlo + exit-multiple wrapper over `financetoolkit`'s WACC, or stay whole. Splitting one valuation across two implementations risks two different WACCs in one thesis card. **Not measured:** whether the two WACC implementations agree numerically. Check before splitting.

**2. `economics/fred_model` already wraps FRED.**

```
fetch_single_series · get_fred_data · get_real_yield_curve · get_recession_indicator
get_breakeven_inflation_expectations · get_nonfarm_payrolls · get_initial_jobless_claims
get_industrial_production_index · get_mortgage_rate_30_year · get_retail_sales ...
```

Recommended-set item 8 is "FRED via raw HTTP, no library." `financetoolkit` — already adopted for other reasons — ships a typed FRED client, so that hand-rolled integration may be free. `get_real_yield_curve` is also directly relevant to the UST 10Y requirement that the `^TNX` defect (§3.3) forced onto FRED in the first place. **Not measured:** whether `fetch_single_series` accepts arbitrary series IDs such as `DGS10`.

---

## 9. Round 4 — audit remediation (2026-08-18)

Two adversarial lenses were run against this audit itself. **It failed.** This section records every remediation. Where a number here differs from §1–§8, **this section supersedes**.

### 9.1 Scoring is now computed, not hand-written

Four of twenty-one weighted scores in §4/§7.6 were arithmetically wrong (TradingAgents 74→80, virattt 71→77, Option B 86.7→84.5, QuantMind 58→64) — three identical −6.0 errors from a stale weighting never recomputed. <!-- sc:historical: records pre-remediation values by design -->

**Fix:** [`score.py`](score.py) is now the source of truth. `python3 internal-docs/adr/score.py` regenerates every score from its sub-scores. It also encodes the two rubrics that §4 stated but did not follow:

```
econ = 10 - 10 * net_new_packages / 80
cost = 10 - 1.5 * (usd_per_month / 50)
```

Applying the econ rubric mechanically moves several scores that were previously judged rather than computed — Kronos 61→70.8, OpenBB 65→62.0, QuantMind 58→64.0 (arithmetic) →62.1 (rubric), nautilus_trader 84→93.4. **No recommendation changes as a result**, because each of those was decided on licence or fit, not on score — which is itself the finding in §9.6. <!-- sc:historical: records pre-remediation values by design -->

### 9.2 The fit gate is now explicit — the formula did not make Decision 1

The audit found the 40/30/30 formula was being used to ratify conclusions reached on unstated grounds. Confirmed: `nautilus_trader` now scores **93.4** — the highest-scoring *rejected* candidate, and fourth overall behind build-from-scratch (100.0), DanisHack-as-VENDOR (96.0) and langgraph (96.0) — and is rejected anyway. `virattt` beats TradingAgents on every measured reliability input (11 vs 31 days idle, 11 vs 8 releases/12mo, 39 vs 19 contributors, 0h vs no response).

**Fix:** a **fit gate** is applied *before* scoring and stated plainly:

> A committee-engine candidate must reproduce DESK_DESIGN §1 W2's 14-node graph — bull/bear researcher, research manager, trader, risk manager, fund manager.

`virattt` is architecturally a persona ensemble (Buffett, Burry, Wood…), not that graph, so it is gated out at 77.0 rather than beaten on points. `nautilus_trader` is a live-execution platform requiring a venue adapter, structurally opposed to D5 (paper only). **Decision 1 and the nautilus rejection are fit decisions. The formula did not make them, and §4 implied it did.**

### 9.3 FMP estimates tier — RESOLVED, and the recommendation changes to $19/mo

§6 listed this as "not measured" while §3.2 printed `💲$49` for the Estimates row as fact. Estimates coverage was the load-bearing justification for the purchase, so this was the audit's most consequential gap.

**Resolved by DOM extraction against the rendered comparison table**, bucketing each row's marks against the measured column positions (`Basic@298 · Starter@448 · Premium@595 · Ultimate@758`):

| Row | Basic (free) | **Starter $19** | Premium $49 | Ultimate $99 |
|---|---|---|---|---|
| Financial Estimates | `sample-flag` | **`us-flag`** | `us-uk-can` | `globe_flag` |
| Price Target Consensus | `sample-flag` | **`us-flag`** | `us-uk-can` | `globe_flag` |
| Ratings Snapshot | `sample-flag` | **`us-flag`** | `us-uk-can` | `globe_flag` |
| Historical Stock Grades | `sample-flag` | **`us-flag`** | `us-uk-can` | `globe_flag` |
| Average Directional Index | `sample-flag` | **`us-flag`** | `us-uk-can` | `globe_flag` |
| Income Statement | `sample-flag` | **`us-flag`** | `us-uk-can` | `globe_flag` |

The marks are **coverage flags, not availability ticks** — the legend is inferred from the filenames and corroborated exactly by the plan-card text ("US Coverage" at Starter, "UK and Canada Coverage" at Premium, "Global Coverage" at Ultimate).

**Analyst estimates and price-target consensus are available at Starter, $19/month, with US coverage.** The Desk is US-only equities, so Premium's UK/Canada adds nothing, and its 30-year history is redundant against yfinance's measured free 27 years (6,934 daily bars, §3.3).

Rescored:

| Option | rel | econ | cost | **Score** |
|---|---:|---:|---:|---:|
| A — $0 | 5 | 10 | 10.0 | 80.0 |
| **B19 — A + FMP Starter $19** | 7 | 9 | 9.43 | **83.3** ✅ |
| B49 — A + FMP Premium $49 | 7 | 9 | 8.53 | 80.6 |
| C — A + FMP Ultimate $99 | 7 | 9 | 7.03 | 76.1 |
| E — A + EODHD $99.99 | 6 | 8 | 7.0 | 69.0 |
| D — Finnhub $3,500 | 9 | 10 | 0.0 | 66.0 |

**Recommendation changes from $49/mo to $19/mo.** FMP reliability is scored 7, not 8 — the tier question is resolved but the service still has no live uptime measurement here.

*Still not measured:* FMP's `Institutional Ownership Filings` and `Treasury Rates` rows did not resolve under the same extraction (both returned empty across all four columns). 13F remains attributed to Ultimate from the plan card only.

### 9.4 `financetoolkit` EXECUTED — and it carries a third naming trap

§8.5 scored it rel 9 on metadata and `inspect.getmembers` presence checks without ever calling a function. The audit called this out, given that this project's two best findings exist precisely because metadata-healthy things returned wrong data when invoked. Now executed on the same seeded 500-point series as §7.5: <!-- sc:historical: records pre-remediation values by design -->

| Function | financetoolkit | empyrical | Verdict |
|---|---|---|---|
| `get_max_drawdown` | **-0.1395** | -0.1395 | ✅ exact agreement |
| `get_beta` | **-0.0099** | -0.0099 | ✅ exact agreement |
| `get_max_drawdown_duration` | **195.0** | *(absent)* | ✅ works — the reason it was chosen |
| `get_max_drawdown_recovery_time` | **66.0** | *(absent)* | ✅ works |
| `get_relative_strength_index` | runs, bounded | *(absent)* | ✅ works |
| **`get_sharpe_ratio`** | **0.0384** | **0.6098** | ⚠️ **15.88× apart** |

```
0.0384 × √252 = 0.6096   ≈ empyrical's 0.6098
```

**`financetoolkit.get_sharpe_ratio` returns a PER-PERIOD (daily) Sharpe; `empyrical`/`quantstats` annualise by default.** Not a bug — a convention difference under an identical name, and **the third instance of this exact trap** (`^TNX` §3.3, `win_rate` §7.5/§8.6). Reported as `0.04` instead of `0.61`, T8's autonomy gate reads catastrophically wrong.

`financetoolkit` reliability adjusted **9 → 8** (executed, but ships a documented footgun): **86.0**, still ahead of `quantstats` at 83.0. Recommendation unchanged.

**T8 must annualise explicitly and assert the convention in a test.**

### 9.5 Coverage re-run across a stratified basket — the small-cap concern is rebutted

§3.3 tested `NVDA` only, one day. The audit correctly flagged that T11's screener returns small-caps where these fields routinely go missing. Re-run across nine tickers:

| Ticker | Cap | 12 required `.info` fields | Option expiries | IV | Daily bars |
|---|---|---|---|---:|---:|
| NVDA | mega | **12/12** | 21 | ✅ | 6,936 |
| AAPL | mega | **12/12** | 22 | ✅ | 11,513 |
| MU | mid | **12/12** | 22 | ✅ | 10,636 |
| PLUG | small | **12/12** | 11 | ✅ | 6,741 |
| RIOT | small | **12/12** | 13 | ✅ | 2,612 |
| BBAI | small | **12/12** | 11 | ✅ | 1,351 |
| SOUN | small | **12/12** | 10 | ✅ | 1,081 |
| CLSK | small | **12/12** | 14 | ✅ | 2,451 |
| BLNK | micro | **12/12** | 6 | ✅ | 4,190 |
| TIVO | *delisted* | **0/12** | 0 | ❌ | 0 |
| GIV | *delisted* | **0/12** | 0 | ❌ | 0 |

**9 of 9 live tickers, mega through micro, return all twelve fields plus an option chain with IV.** The concern is rebutted by measurement.

**But it surfaced a different failure, and a worse one.** `TIVO` and `GIV` — two of the five positions in DESK_DESIGN's own example book — are delisted, and yfinance returns **all-MISS across every field with no exception raised**, only a stderr note. Same silent-failure class as `^TNX`. A health check on a delisted holding would silently report nothing rather than refusing.

**Consequence for T2:** the mandated guard cannot be a row-count floor alone — options IV and short interest are `.info` scalars, so the failure mode is a **missing key**, not a short series. `desk/data.py` needs a per-field schema assertion plus an explicit ticker-liveness check.

### 9.6 Sub-scores that were asserted rather than measured

§2.1 had no probe rows for `virattt` or `DanisHack`, yet both carried economy sub-scores. Measured now:

```
pip install .   (clean py3.11 venv, DanisHack repo root)
→ 73 packages, 249 MB, NET-NEW vs the 142-package recommended set = 8
  ai-hedge-fund, alpaca-py, groq, langchain, langchain-groq, msgpack,
  polygon-api-client, sseclient-py
```

Rubric econ = `10 − 10×8/80` = **9.0**, not the 7 asserted. **DanisHack-as-DEPEND is therefore 65.0, not 59.0.** The DEPEND→VENDOR swing is **65 → 96**, not 59 → 96. The point stands; the number was wrong.

**`score.py` mixes rubric-computed and judged economy sub-scores.** `econ_from_net_new()` is applied to six rows; the rest carry judged values. Under the pure rubric `quantstats` would be 8.75 (→~88.2) and `financetoolkit` 9.125 (→~89.4), narrowing that margin from 3.0 to **1.2**. Same decision, much thinner. This is disclosed rather than silently reconciled because changing it moves nine scores and none of the decisions. For completeness the two largest moves are `ffn` 77.0→~86.8 and `bt` 74.0→~86.0 — `bt` would tie `financetoolkit`'s current 86.0, which is worth knowing even though both are rejected on fit.  
*(`~` marks a hypothetical score under an alternative rubric, not a value `score.py` produces. The self-check skips `~`-prefixed numbers.)*

*`virattt` footprint: probe did not complete — **not measured**. Its econ 5 remains unsupported, and it is gated out on fit regardless (§9.2).*

### 9.7 The `backtrader` retraction, propagated

§7.8 is titled *"`backtrader` is a licence problem, not housekeeping"* and concluded it was *"the same class of exposure as the OpenBB AGPL finding."* **That conclusion is withdrawn.** Installing a copyleft package into a local virtualenv is not conveying it, and nothing imports `backtrader`. The correct reason to remove it is **dead weight** — 22.9k★, 729 days idle, zero imports.

The same reasoning was withheld from OpenBB, where it would have been inconvenient. OpenBB's exclusion survives on: **86 net-new packages** (econ 0.0 by the rubric), +119 MB, zero unique metrics, and — the argument that actually holds — that `desk/data.py` would *import* it and this repo is *public*, so we would publish source forming a combined work with an AGPL-3.0 library.

The unbounded criterion *"No AGPL package in the environment"* is **withdrawn** and replaced by an enforceable T1 invariant: **no distribution in the resolved environment carries a GPL/AGPL classifier, asserted by a test.**

### 9.8 Package count reconciled

The document previously stated 134, 142 and 220 in different sections. **The recommended set is 142 packages** (verified: union of the TradingAgents git tree, the core ops set, `scipy`, and `financetoolkit`). OpenBB's marginal cost is **+86 packages on that 142 base (+61%)**, not "+64% on a 134-package base."

### 9.9 The $19 tier has a coverage gap the remediation missed — found by the verification audit

§9.3 checked what Premium adds over Starter and concluded UK/Canada coverage and 30-year history, both irrelevant here. **It missed the one that matters.** FMP's own plan cards, re-read on the live page:

```
Starter $19 : "... US Coverage · ANNUAL Fundamentals and Ratios · Historical Stock Price Data ..."
Premium $49 : "... UK and Canada Coverage · FULL Fundamentals and Ratios · Intraday Charts ..."
```

DESK_DESIGN §1 W2 requires **`rev Q/Q`**. Annual statements cannot produce a quarter-over-quarter figure. **Starter does not deliver a fundamentals fallback for that metric**, and §3.2 billing `rev Q/Q` at `💲$19` contradicts §3.1's own plan-card row on the same page. The `Income Statement` row in §9.3's extraction carries no periodicity, so the DOM evidence does not resolve it either.

**Does it sink the $19 recommendation? Measured, no — but only just.**

```
yfinance quarterly_income_stmt   (free, no key)
  NVDA: shape (39, 5), cols 2026-04-30 … — Total Revenue 81,615,000,000 / 68,127,000,000
        -> rev Q/Q = 19.80%   ✅ computes
  SOUN: shape (55, 7) — Total Revenue latest quarter = NaN
        -> rev Q/Q = nan      ⚠️ silent gap on a small cap
```

`rev Q/Q` therefore has a working free primary source, and paying **$360/year more** to gain a *fallback* for one derivable metric out of 26 is poor value. **Recommendation stays at $19 Starter**, with the gap recorded rather than hidden:

- `rev Q/Q` is **single-sourced on yfinance** at the $19 tier. If a licensed fallback for it is required, the price is $49, not $19.
- The SOUN result is a **fourth instance** of this project's recurring failure class — a NaN in the latest quarter, returned without error. The T2 per-field guard must treat NaN as missing, not as a value.

### 9.10 Honest sensitivity — the paid tier is a close call resting on an unmeasured sub-score

B19's 83.3 beats A's 80.0 by **3.3 points**, and that margin is driven almost entirely by FMP's reliability sub-score of **7 versus A's 5**. That 7 is an *estimate*: FMP has never been live-tested here — no key, no uptime observation, no latency measurement.

| FMP reliability | B19 score | vs A (80.0) |
|---:|---:|---|
| 8 | 87.3 | pay |
| **7 (used)** | **83.3** | **pay** |
| 6 | 79.3 | **free wins** |
| 5 | 75.3 | free wins |

**A one-point move in an unmeasured sub-score flips the decision.** Stated plainly because the earlier draft of this audit presented the paid tier as clearly correct when it never was. $0 (Option A) remains defensible, and the ADR's own revisit clause — drop to $0 if T8 shows no edge — should be honoured with a **monthly**, not annual, subscription.
