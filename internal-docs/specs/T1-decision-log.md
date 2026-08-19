# T1 — Decision Log

**Ticket:** T1 scaffold · **Tier:** standard · **Branch:** `desk-t1-scaffold` off `main` @ 6ee1a14
**Status:** spec audited, escalated, and **unblocked** — ADR 0001 accepted, E1/E2/E3 all resolved. Next: revise this spec against M1–M11, then build. No application code written yet.

## Locked decisions (NON-NEGOTIABLE)

| # | Decision | Set by |
|---|---|---|
| L1 | Build to ADR 0001 as revised — drop OpenBB, add `financetoolkit` | Sir, 2026-08-18 |
| L2 | ~~ADR stays `Status: Proposed`~~ — **SUPERSEDED.** Sir set a condition ("if audit 3 passes, accept"); pass 4 returned ACCEPT-WITH-CAVEATS, its must-fix was corrected, and the ADR is now **Accepted** with six caveats on the record | Sir, 2026-08-18 (revised same day) |
| L3 | DanisHack vendoring confirmed — but executed in T4/T8/T12, not T1 | Sir, 2026-08-18 |

## Panel run

Lean panel per `skeptic-panel.md` (standard tier): **staff-engineer** + **red-teamer**, plus **pre-mortem**, all as read-only `ship-auditor` subagents. 19 concerns returned; synthesis below.

---

## ESCALATIONS — Sir's call, build is blocked on these

### E1 · SEVERE RISK — public repo, secret scanning off, `.gitignore` gap. Live now, independent of T1.

Measured on `six-eyes-bot/six-eyes` 2026-08-18:

```
private: false
secret_scanning: disabled
secret_scanning_push_protection: disabled
secret_scanning_non_provider_patterns: disabled
```

`git check-ignore` dry-run against the current `.gitignore` (which has exactly one import rule, `imports/*.csv`):

| Path | Result |
|---|---|
| `imports/positions.csv` | IGNORED |
| `imports/statement.pdf` | **WOULD BE TRACKED** |
| `imports/positions.xlsx` | **WOULD BE TRACKED** |
| `imports/export.ofx` | **WOULD BE TRACKED** |
| `config/desk.yaml` | **WOULD BE TRACKED** |
| `.envrc` | **WOULD BE TRACKED** |

DESK_DESIGN §4.5 routes Wells Fargo exports into `imports/`. Wells Fargo exports are commonly `.pdf`/`.xlsx`/`.ofx`/`.qfx` — **only the `.csv` case is covered.** A statement dropped there publishes Sir's actual positions to a public, indexed repo. §3 makes `config/desk.yaml` the risk-limits file — the natural place an API key gets pasted — and it is tracked.

This is not a T1 risk. It exists today.

### E2 · ADR is "Proposed" but T1 executes it, and nothing adjudicates it

Ruleset `protect-main` measured: rules are `deletion`, `non_fast_forward`, `pull_request` with **`required_approving_review_count: 0`** and **no `required_status_checks`**. The T1 PR is self-mergeable with no human review and no green build.

L2 says the ADR stays Proposed. But D1's dependency set, D5's findings, D6's provider set and an executable Done criterion all encode its outcome. A Proposed ADR becomes binding-by-CI on public `main` without ever being accepted — and if Sir later rejects it, the reverting history is permanently public (`non_fast_forward` on, `bypass_actors: []`, `current_user_can_bypass: never`).

### E3 · Engine-entry is effectively forced, and one option needs Sir's approval

The spec offered (a) pinned git dep, (b) GitHub fork, (c) vendor in-tree. The panel killed (a) twice over: T6 must edit engine source (upstream registers analysts through a hardcoded factory dict in `graph/setup.py` — no registry or entry-point hook), and the spec's own Done criterion `pip list | grep backtrader` → nothing is **unsatisfiable** under (a), because upstream's `pyproject.toml` declares it.

Frozen DESK_DESIGN §3 puts `engine/` **in-tree**, which forecloses (a) and (b) as written. (b) additionally requires creating a **public fork** under Sir's org — an outward-facing action I will not take unasked.

---

## MUST-FIX (spec revision, once E1–E3 are answered)

| # | Finding | Lens |
|---|---|---|
| M1 | Option set incomplete — missing (d) resolver-level `override-dependencies` and (e) git submodule at `engine/`. Neither (d) alone nor (a) survives T6; the honest matrix is 2-D (dep control × source editability) | staff |
| M2 | Vendoring into `engine/` breaks `make test` on day one — pytest collects upstream's 54 test files, ruff/mypy scan 257 commits of foreign code. **Exclude by enumerated file list, never a directory glob**, or T6's four net-new analyst nodes are born permanently outside the quality gate | staff + pre-mortem |
| M3 | D1–D6 cannot deliver "green from a clean clone": no `make setup`, `versions.lock` is prose not a lockfile, no CI workflow exists despite "pin CI to 3.11", no Python **upper** bound (measured ceiling `<3.15`) | staff |
| M4 | Frozen TICKETS/DESK_DESIGN still prescribe OpenBB as primary (T2 Adopt list, T2 Done criterion, §2 install block, §3 `openbb_mcp.py`). Add `internal-docs/SUPERSEDED.md` — a new file violates no freeze and makes the drift greppable | staff + pre-mortem + red-team |
| M5 | D2's "one real passing test" is theatre. Make it the **invariant test**: every runtime dep imports, installed versions match `versions.lock`, no distribution carries a GPL/AGPL classifier. Then `make test` green means something | staff + pre-mortem |
| M6 | `litellm` and `langfuse` are **composite** licences — that is why the API returns NOASSERTION. litellm carves out `enterprise/`; langfuse carves out `ee/`, `web/src/ee/`, `worker/src/ee/`. Both remainder-MIT. A `LICENSES.md` row saying "MIT" would be materially wrong | staff |
| M7 | No vendoring convention (location, provenance format, exclusion policy) — yet T4/T8/T9/T12 each vendor from a different upstream and will each invent one. mypy strictness unspecified against untyped `yfinance`/`finvizfinance`/`financetoolkit` | staff |
| M8 | T1 must stub `desk/data.py` with the `MarketData` Protocol (typed signatures, `NotImplementedError`, row-count-floor contract in the docstring). It is the seam three vendored codebases repoint at, and **DESK_DESIGN §3's tree omits it** | pre-mortem |
| M9 | Record *who* forces `pandas==3.0.5` (financetoolkit) and whether its drawdown-duration/recovery functions run under pandas 2.x — one measurement now vs an unplanned migration during high-stakes T8 | pre-mortem |
| M10 | Engine dataflow ownership: ADR drops OpenBB **and** Finnhub; §3 assigned the engine's primary source to `openbb_mcp.py`. Nothing owns repointing `engine/dataflows/` at `desk/data.py`. (Upstream does ship `alpha_vantage`, `y_finance`, `fred` dataflows, so the engine is not dataless — but the *owner* is unassigned) | red-team |
| M11 | Do not publish non-lawyer adverse legal characterisations of named third-party repos on a public repo. Keep vendor-by-vendor assessments in the private record; public `LICENSES.md` states only what the project does, dated and SHA-stamped, with "engineering record, not legal advice" | red-team |

## NICE-TO-HAVE

- N1 · Add `required_status_checks` to `protect-main` in the same PR that adds the CI workflow, or the workflow runs and is ignored.
- N2 · Decide now whether a bypass actor exists for secret-scrub emergencies (`bypass_actors: []` today) rather than discovering it mid-incident.

## REJECTED (with reasons)

| Finding | Why rejected |
|---|---|
| Pre-mortem #1 — "the 342 tests won't port; they import `polygon`/`websockets`" | **Disproved by measurement.** The 8 test files covering the vendor-target modules import only `pytest`, `unittest`, `datetime`, `json`, `csv`, `__future__`, `src`. `grep -rlE "polygon\|websockets\|alpaca" tests/` returns **nothing**. Ran them in isolation: **160 passed in 3.55s**. The polygon warning comes from `src/config/settings.py` transitively, not the tests. |

---

## Corrections to my own prior work (surfaced by the panel)

**C1 — My licence correction was asymmetric in my own favour.** Red-team, and it is right. I argued "installing a GPL package into a venv is not conveying it" for `backtrader` — which unlocks the cheapest engine option — but withheld the identical reasoning from `openbb`, where it would undermine my ADR's headline finding. At T1 nothing imports either. OpenBB's exclusion **does** survive, but on the grounds I failed to state: +86 packages / +119 MB / 0 unique metrics, and — distinctly stronger — that publishing *importing source* from a **public** repo is a far better conveying argument than a local venv. The ADR's "same class of exposure as the OpenBB AGPL finding" line and the "No AGPL package in the environment" Done criterion both need rewriting.

**C2 — "342 tests come along with the vendoring" is imprecise.** Measured: **160** of the 342 cover the 11 vendor-target modules (`test_portfolio_tracker` 40, `test_risk_manager` 29, `test_macro_regime` 20, `test_paper_trading` 18, `test_metrics` 15, `test_export` 13, `test_portfolio_manager` 13, `test_engine` 12). The other 182 test persona agents (`ackman`, `buffett`, `burry`, …) we are **not** taking. 160 is still a strong number and the vendoring verdict is unchanged — but the ADR should say 160.

---

## ADR ADVERSARIAL AUDIT — **FAILED** (2026-08-18)

Sir's condition for E2: *"if it passes adversarial audits by /ship, then proceed."*
Two lenses run against the ADR itself (red-team on recommendations; measurement-integrity on the numbers). **It did not pass.** T1 remains blocked.

### Blocking defect 1 — four weighted scores are arithmetically wrong

Both auditors found the same four independently; recomputed mechanically and confirmed:

| Row | Printed | Actual | Δ |
|---|---:|---:|---:|
| §4.1 TradingAgents | 74.0 | **80.0** | −6.0 |
| §4.1 virattt | 71.0 | **77.0** | −6.0 |
| §4.3 Option B ($49) | 86.7 | **84.5** | +2.2 |
| §4.5 QuantMind | 58.0 | **64.0** | −6.0 |

The three identical −6.0 errors suggest a stale copy from an earlier weighting. The worksheet's stated purpose was "show the arithmetic so the human can re-weight without re-measuring" — it cannot be used for that.

### Blocking defect 2 — the $49 subscription flips to $0

Corrected: A ($0) = 80.0, B ($49) = 84.5, margin +4.5 not +6.7.

FMP was **never live-tested** (no key, no uptime observation), and §6 states *"FMP's per-tier attribution for analyst estimates and price targets … Verify before purchase"* — yet §3.2's Estimates row prints `💲$49` as measured fact, and estimates coverage is the load-bearing justification for the purchase (yfinance already supplies estimates free).

Score FMP reliability 6 instead of 8 — justified, since it is unverified on the exact capability being bought — and **B = 76.5 < A = 80. Option A wins at the ADR's own weights, no re-weighting needed.**

Also unscored: **FMP Starter at $19/mo** appears in the §3.1 pricing table and never enters the A–E ladder.

### Blocking defect 3 — the base-engine choice may flip

virattt beats TradingAgents on **every measured reliability input**: 11 vs 31 days idle, 11 vs 8 releases/12mo, 39 vs 19 contributors, 0h vs n/a first response. Both were assigned rel 8. At rel 9 — which the raw table supports — virattt = 81.0 > TradingAgents = 80.0.

TradingAgents may still be right, but on **fit** (its graph matches the source system 1:1), which is not in the rubric. The formula was used to ratify a conclusion reached on unstated grounds.

### Further defects (non-blocking but must fix)

| # | Defect |
|---|---|
| A1 | §2.1 has **no probe rows for virattt or DanisHack** — both were given econ sub-scores with no measurement behind them |
| A2 | The retracted backtrader/GPL argument is **still live in three places**: scoring §7.8 (titled "a licence problem, not housekeeping"), the ADR's T1 action item (`LICENCE-CRITICAL`), and Consequences→Easier. Only the Trade-off section was corrected |
| A3 | Package total inconsistent across the document: **134 / 142 / 220**. OpenBB's "+64%" headline is computed off the stale base |
| A4 | Econ sub-scores do not follow the stated rubric (`0 new = 10; ≥80 new = 0`). `financetoolkit` and `nautilus_trader` both measure **7 net-new** and are scored **8 and 6** |
| A5 | Coverage proven on **NVDA only, one day**. T11's screener returns small/mid-caps where `shortPercentOfFloat`, `institutional_holders` and option chains are routinely absent |
| A6 | The "minimum-row-count assertion" mitigation **cannot catch the actual failure mode** for options IV and short interest — those are `.info` scalars, so the failure is a silently missing key (as `revenueQuarterlyGrowth` was), not a short series |
| A7 | `financetoolkit` scored rel 9 without a single function ever being executed — presence checked via `inspect.getmembers`, never called |
| A8 | T18 specifies "$49/mo **billed annually**" = a $588 prepaid lock-in, contradicting the revisit clause "if it doesn't [work], drop to $0" |

### Rejected finding (with evidence)

Red-team claimed DanisHack's ported tests import `polygon`, which would break the "0 net new packages" claim. **Measured and false.** The 8 test files covering the taken modules import only `pytest`, `unittest`, `datetime`, `json`, `csv`, `__future__`, `src`. `grep -rlE "polygon|websockets|alpaca" tests/` returns nothing; the deprecation warning originates in `src/config/settings.py` transitively. econ 10 stands.
