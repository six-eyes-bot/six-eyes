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

---

# Stage B — vendoring the engine (2026-08-19)

Branch `desk-t1-engine` off `main` @ `4a11a6d`. Executes T1 spec rev 3 stage B:
D3 (`engine/`), the manifest, `tooling-config`, and invariants 5, 6 and 8.
Steps 1–4 of the ship loop were already banked in spec rev 3, so this is step 5
onward: TDD, per-step review, drift check, verification gate.

## The pin

`TauricResearch/TradingAgents` @ **`01477f9afb7a47b849ed4c9259d3a9a4738d9fda`**.

`v0.3.1` is an **annotated** tag and therefore carries two SHAs — the tag object
`5a3d1b51d339202d03c4b57c1a1012f69376495f` and the commit above. The commit is
pinned. Recorded in `versions.lock` and `engine/PROVENANCE.md` because pinning
the tag object is a plausible-looking mistake that resolves to a tag, not a tree.

## Measurements taken

| Claim | Measured |
|---|---|
| upstream size | 158 files, 4,740,672 bytes at the pinned SHA |
| vendored | **84 files, 644 KB** |
| `assets/` | 11 files, 4.0 MB — **85% of the payload**, all README screenshots |
| `backtrader` / `redis` | declared in upstream `pyproject.toml`, **imported by zero `.py` files** — independently re-confirms ADR 0001 |
| upstream vs our ruff config | **179 errors** |
| upstream vs our mypy config | **100 errors in 39 files** |
| `NOTICE` | absent — so Apache-2.0 §4(d) does not bind. §4(b) does |
| upstream `LICENSE` appendix | unfilled (`Copyright [yyyy] [name of copyright owner]`); body intact |
| `.env.enterprise.example` | **Azure OpenAI** settings, not a separately-licensed `ee/` tree |

That last row was checked specifically because `litellm` and `langfuse` both
carve out enterprise directories under different terms. This upstream does not.

## Decisions taken during execution

| # | Decision | Why |
|---|---|---|
| B1 | Omit `assets/`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `requirements.txt`, `.env*`, `.gitignore` **in addition to** the spec's `pyproject.toml` / `tests/` / `.github/` | **Deviation from the spec's literal three-item list**, taken under `VENDORING.md` §4b's general rule and recorded in `engine/PROVENANCE.md`. `assets/` is 85% of the bytes and zero function; the Docker files build from the omitted `pyproject.toml` and so cannot work; `requirements.txt` contains only `.`. Cost: broken image links in the vendored `README.md`. |
| B2 | `engine/` **is** in mypy's `files` | The spec's mypy row only makes sense if mypy actually walks `engine/`. With manifest-derived exemptions by exact name, anything new under `engine/` is typed from its first commit — which is the point. |
| B3 | mypy module names come from **mypy's own resolver**, not a hand-rolled rule | Two hand-rolled rules were written and both were wrong, in opposite directions (see below). |
| B4 | `scripts/` added to mypy's `files` | It is first-party code. Adding it immediately found a real bug — `BuildSource.path` is `str \| None` and was being passed to `Path()` unguarded. |

## The mypy module-name trap (worth carrying)

The exemption list must be **exact module names**. `module = ["tradingagents.*"]`
is the enumerated-vs-glob mistake reintroduced through mypy's back door: T6's
four analyst nodes land in `engine/tradingagents/agents/analysts/`, squarely
inside that glob, and would be born untyped.

Deriving those names by hand failed twice:

| Path | Guess | Actual |
|---|---|---|
| `engine/scripts/smoke_structured_output.py` | `scripts.smoke_structured_output` | `smoke_structured_output` |
| `engine/tradingagents/agents/analysts/market_analyst.py` | `market_analyst` | `tradingagents.agents.analysts.market_analyst` |

The first guess was "strip `engine/`, join with dots"; the second was "climb
while `__init__.py` exists". `namespace_packages` defaults to True, which breaks
both. **The failure is silent** — a non-matching override never applies and the
only signal is a `warn_unused_configs` note that does not fail the build. That
note is the only reason it was caught.

## Per-step review (ship-workflow §6) — NON-SKIPPABLE

Scope: `scripts/vendor_engine.py`, `pyproject.toml`, `Makefile`,
`versions.lock`, `tests/test_invariants.py`, `engine/PROVENANCE.md`.
Stance: adversarial — assume defects; "tests pass" is not correctness.

| # | Finding | Sev | Triage |
|---|---|---|---|
| R1 | `cmd_vendor` called `shutil.rmtree(ENGINE)` directly beneath a comment promising it would *not* — would delete T6's first-party nodes on every re-vendor | **High** | **Fixed.** Unlinks only manifest-claimed paths. |
| R2 | `main()` called `parse_args()` twice | Low | **Fixed.** |
| R3 | Manifest generated from the working tree would re-bless T6's files as vendored | **High** | **Prevented by design** — `manifest` downloads the pinned SHA and fails closed. Demonstrated: the first run failed closed on a TLS error rather than falling back. |
| R4 | `test_a_vendored_file_is_not_linted` picked `sample[0]` = `engine/cli/__init__.py`, which passes our config, so it asserted nothing | Med | **Fixed.** Rewritten set-wide; now proves 179 real errors are suppressed. |
| R5 | TLS verification failed on a bare interpreter; tempting fix is an unverified context | **High** | **Fixed properly** — `certifi` bundle, never `_create_unverified_context`. The pin is meaningless without TLS. |
| R6 | `Path(src.path)` where `src.path` is `str \| None` | Med | **Fixed** — found by mypy once `scripts/` entered its scope, not by review. |
| R7 | Tarball extraction could write outside the target directory | Med | **Fixed** — members with absolute paths or `..` are rejected before extraction. |
| R8 | Canary files could leak into the tree if a test body raised | Med | **Fixed** — both canaries unlink in `finally`, and both assert no canary is already present. |

**Rejected:** none. Every finding above survived verification and was implemented.

## Proof the gates can fail

Each invariant was mutation-tested, not asserted:

| Mutation | Result |
|---|---|
| `extend-exclude = ["engine/**"]` (the forbidden glob) | invariant 5 fails *stale tooling config, 84 files*; invariant 8 fails *"the gate has a hole in it"* |
| append one line to `engine/tradingagents/default_config.py` | invariant 6 names the edited file and points at §4(b) |
| `module = ["tradingagents.*"]` | both mypy invariants fail, **and** the type canary at T6's exact path is silently accepted — proving the glob is the real hazard |

## Verification (ship-workflow §8)

```
$ make test
ruff check .   -> All checks passed!
mypy           -> Success: no issues found in 85 source files
pytest -q      -> 27 passed in 8.85s
make test: all green
```

CI's other three gates re-run locally on this branch: `.gitignore` blocks none
of the 84 vendored files; the secret-shaped-file grep is clean; `score.py
--check` reports 0 failures. `internal-docs/TICKETS.md` and
`internal-docs/DESK_DESIGN.md` are unmodified.
