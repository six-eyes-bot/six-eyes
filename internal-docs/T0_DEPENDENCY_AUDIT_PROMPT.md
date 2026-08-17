# T0 — Dependency Audit (run in Claude Code, before `/ship` T1)

**Paste everything below this line as the prompt.**

---

You are running a research and measurement task. **Do not write application code, do not scaffold the project, do not run `/ship`.** The only artifacts you produce are an ADR and a scoring worksheet. A human audits your recommendation before any of it is implemented.

## Goal

Select the dependency set for "The Desk" — an AI investment-committee system specified in `internal-docs/DESK_DESIGN.md` and `internal-docs/TICKETS.md`. Optimize, in priority order:

1. **Reliability** — maintained, tested, unlikely to break or be abandoned
2. **Dependency economy** — fewest distinct things relied on; prefer candidates sharing transitive deps
3. **Data subscription cost** — this is the budget being optimized. LLM token cost is out of scope for this audit; it's handled by model routing in T14.

## The rule you are applying

Selection criteria differ by **adopt mode**, and classifying each candidate is part of your job:

- **DEPEND** — installed via a package manager, upgraded over time, someone else's release cadence is our problem. Reliability metrics matter heavily here.
- **VENDOR** — copied into our tree, becomes our code, upstream stops mattering the moment we copy. Here popularity is nearly irrelevant; license, test coverage, size, and *transitive dependency footprint* are what matter.

Do not select on stars. In the AI-finance niche specifically, star counts track how well a concept travels on social media, not code quality — the most-starred candidates carry READMEs stating they are unfit for real capital. Use stars as one weak input among several, never as a tiebreak on its own.

## Candidates

**Committee engine (DEPEND or VENDOR — you decide):**
- `TauricResearch/TradingAgents` — current pick, Apache-2.0
- `virattt/ai-hedge-fund`
- `DanisHack/ai-hedge-fund` — MIT, 342 tests, currently slated for vendoring
- `td-02/ai-native-hedge-fund`
- Anything better you find. Search actively; the list is not exhaustive.

**Valuation:** `EmanueleSturzo/DCF-Valuation-Model`, `dafahentra/dcf-valuation-tool`, alternatives

**Data:** OpenBB (+ its underlying providers), yfinance, finvizfinance, Alpha Vantage, Polygon, Finnhub, Tiingo, EODHD, FMP, SEC EDGAR, FRED

**Ops:** LiteLLM, Langfuse, `NousResearch/hermes-agent`, LangGraph

**Knowledge / research-retrieval layer (establish fit *before* measuring):**
- `LLMQuant/quant-mind` (QuantMind) — MIT, agent-native knowledge-extraction and retrieval framework for quant finance: refines papers, news, and filings into typed, cited, timestamped knowledge for downstream retrieval. **Its fit is not established.** The Desk's required metrics (§1 W2) are overwhelmingly structured — prices, fundamentals, estimates, options, macro — and the only obvious consumer of an unstructured-knowledge/RAG layer is the News/Sentiment analyst node, with a possible secondary role feeding research/macro context. So answer the scoping question first: **does this system need a knowledge-extraction layer at all, and if so, which node(s) consume it?** If the honest answer is no, drop it with that reasoning and do not fold it into the recommended set — a null result here is a valid, cheap outcome. If yes, scope it narrowly, then measure it on the same axes as every other candidate (reliability, transitive footprint, install size) and report it as a **standalone line item, gated behind the fit decision** — never bundled into the core set. Treat it like the Kronos line below: measured, but scoped separately.

**Forecasting (measure, but scope separately):** `shiyu-coder/Kronos` — MIT, 36.5k★. Slated as optional T16, gated behind T8. Measure its dependency footprint anyway: it brings PyTorch + HF transformers, and the install size number is what makes the keep/drop argument concrete. Report it as a standalone line item, not folded into the recommended set.

## Phase 1 — Measure repo reliability

For every repo candidate, use `gh api` and record **raw numbers, not impressions**:

```
gh api repos/{owner}/{repo} --jq '{stars:.stargazers_count, forks:.forks_count, pushed:.pushed_at, open_issues:.open_issues_count, archived:.archived, license:.license.spdx_id, is_fork:.fork}'
gh api repos/{owner}/{repo}/commits --jq 'length' -X GET -f per_page=100
gh api repos/{owner}/{repo}/contributors -X GET -f per_page=100 --jq 'length'
gh api repos/{owner}/{repo}/releases --jq '[.[].published_at]'
```

Derive and tabulate: days since last commit · release cadence over 12 months · contributor count (bus factor) · median time-to-first-response on the 20 most recent closed issues · open-issue-to-star ratio · **fork status and, if a fork, commits ahead of upstream**.

A bare mirror fork is disqualifying. We already made that mistake once with `bit-r/TradingAgents-AI-hedge-fund` — 149 inherited commits, zero divergence, a README identical to upstream, and a feature credited to it that was actually native to upstream. Check `parent` and compare.

## Phase 2 — Measure dependency footprint

For each DEPEND candidate, in an isolated venv:

```
python -m venv /tmp/probe-{name} && /tmp/probe-{name}/bin/pip install {pkg}
/tmp/probe-{name}/bin/pip install pipdeptree && /tmp/probe-{name}/bin/pipdeptree --json-tree > /tmp/{name}.json
du -sh /tmp/probe-{name}/lib/python*/site-packages
```

Record: unique transitive packages · install size on disk · Python version floor/ceiling · any package appearing in a known-abandoned or CVE-flagged state.

Then build an **overlap matrix** across all candidates. Shared transitive deps are a strong positive — if two candidates both sit on LangGraph, adopting both costs far less than the sum of their trees. Report total unique packages for the whole recommended set, not per-candidate.

For each VENDOR candidate, additionally: LOC of the modules we'd actually take (not the whole repo), test count and whether tests pass on a clean checkout, and — most important — how many packages that specific module drags in. A 300-line module pulling three packages is worse than a 600-line one pulling none.

## Phase 3 — Data provider cost (the budget being optimized)

Build a **coverage-by-cost matrix**. Rows: every metric the system requires. Columns: every provider. Cells: available / paywalled / absent, plus the tier and price required.

Required metrics, from `internal-docs/DESK_DESIGN.md` §1 W2:
- Technical — RSI, VWAP σ, SMA200, DMI, 3-month and YTD change
- Fundamentals — fwd P/E, rev Q/Q, gross margin, ROE, FCF
- Estimates — analyst count, consensus rating, consensus target
- Flow/Ownership — short % float, institutional net, days to cover
- Options — ATM IV, cycle open interest, call/put volume ratio
- Macro — VIX y/y, QQQ/SPY relative, UST 10Y, DXY
- Screener — day gainers, SMA-cross filters
- Plus: historical daily bars back far enough for the T8 backtest

Web-fetch each provider's live pricing and rate-limit page; do not rely on training data for prices. Note free-tier request limits explicitly — a free tier that allows 25 requests a day cannot serve 14 agents.

Then answer directly: **what is the cheapest set of providers that covers every required metric?** Give the monthly figure. Give the next tier up and what it buys. Rate-limit headroom counts as a cost — a cheaper provider that throttles us into a second provider is not cheaper.

**Flag for review, don't decide unilaterally:** yfinance and finvizfinance are free but scrape, break on upstream markup changes, and have terms-of-service ambiguity for automated use. State the risk plainly and let the human decide.

## Phase 4 — The OpenBB verdict

Answer as a standalone section with evidence.

OpenBB is primarily a normalization layer over other providers, not a data source. We are already writing `desk/data.py` as our own provider-agnostic interface, so OpenBB may be an abstraction beneath an abstraction. Determine:

1. Which required metrics does OpenBB serve that the chosen direct providers don't — and on which underlying provider, at which paid tier?
2. What is its transitive dependency count and install size versus calling providers directly?
3. Is the MCP server its only unique value? If so, quantify what that saves — how many tool definitions would we otherwise hand-write, and is that a one-time cost?
4. If dropped, what breaks, and what is the migration cost of adding it back later?

**Recommend keep or drop with a number attached.** It is in the source post, which is a reason to examine it, not a reason to keep it.

## Phase 5 — Output

Write `internal-docs/adr/0001-dependency-selection.md`:

- **Status:** Proposed *(not Accepted — a human signs off)*
- **Context** — the three optimization criteria and the vendor/depend distinction
- **Decision** — the recommended set, each item tagged DEPEND or VENDOR
- **Options Considered** — per decision point, with the measured table
- **Trade-off Analysis** — say explicitly where reliability and dependency economy conflicted and which you chose. They *will* conflict: the most popular options in this space are also the heaviest.
- **Consequences** — what gets easier, what gets harder, what needs revisiting
- **Action Items** — which tickets in `internal-docs/TICKETS.md` change, as a diff-style list. Do not edit that file.

Also write `internal-docs/adr/0001-scoring.md`: the full raw measurement tables. Every number traceable to the command that produced it. Weights: reliability 40, dependency economy 30, subscription cost 30 — state them, apply them, and show the arithmetic so the human can re-weight without re-measuring.

## Rules

- Every claim carries a measured number or a fetched citation. Where a number couldn't be obtained, write "not measured" — never estimate and never present a README claim as a verified fact.
- README claims are marketing until verified. "342 tests" means you cloned it and ran them.
- If measurement contradicts a recommendation in `internal-docs/TICKETS.md`, say so directly and show the evidence. Two of its recommendations were already wrong; assume more are.
- If the best answer is "keep the current pick," say that. A null result is a valid outcome and cheaper than a change.
- Do not modify `internal-docs/TICKETS.md`, `internal-docs/DESK_DESIGN.md`, or any application code. Recommend; don't apply.
- Timebox to roughly 90 minutes of tool time. If you're over, ship the ADR with the unmeasured items flagged rather than continuing.
