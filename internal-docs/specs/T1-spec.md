# T1 Spec — Scaffold, pinned engine, licence audit (rev 3)

**Tier:** standard · **Branch:** `desk-t1-scaffold` · **Base:** `main` @ 90f399b
**Authority:** `internal-docs/TICKETS.md` T1, as revised by **`internal-docs/adr/0001-dependency-selection.md` (Status: Accepted, 2026-08-18)**.
**Rev 2** applied the eleven must-fixes. **Rev 3** applies the light plan audit's six findings — two of which were structural: rev 2 mandated "never a directory glob" and then printed one, and rev 2 had no orderable green intermediate at all.

## Locked decisions

| # | Decision |
|---|---|
| L1 | Build to ADR 0001 — drop OpenBB, add `financetoolkit` |
| L2 | ~~ADR stays Proposed~~ **SUPERSEDED** — ADR is **Accepted**; six caveats on its record |
| L3 | DanisHack vendoring confirmed, but executed in T4/T8/T12, **not T1** |
| L4 | **Engine enters the tree as vendored source at `engine/`** (option c) |

## Goal

From a clean clone: `make setup` provisions, `make test` is green, and every external source is pinned in a real lockfile with no unrecorded licence landmine.

## Deliverables

| # | Deliverable | Closes |
|---|---|---|
| D1 | `pyproject.toml` — `desk` package, `requires-python = ">=3.11,<3.15"`, ADR dependency set | M3 |
| D2 | `desk/` skeleton incl. **`desk/data.py` `MarketData` Protocol** (typed, `NotImplementedError`, guard contract in docstring) | **M8** |
| D3 | `engine/` — TradingAgents copied at a pinned SHA, `backtrader`/`redis` stripped, upstream `pyproject.toml`/`tests/`/`.github/` omitted, `PROVENANCE.md` stating changes | M1, L4, M2b |
| D4 | `Makefile` — `setup`, `test`, `tooling-config`, `vendor-manifest`; **plus amending `ci.yml` to `make setup && make test`** | M2, M3 |
| D5 | `uv.lock`/`requirements.lock` — a real lockfile, plus `versions.lock` recording SHAs | M3 |
| D6 | `tests/test_invariants.py` — the invariant test, not a placeholder | **M5** |
| D7 | `internal-docs/LICENSES.md` — factual, dated, SHA-stamped | M6, M11 |
| D8 | `internal-docs/SUPERSEDED.md` — what ADR 0001 overrides in the frozen docs | **M4** |
| D9 | `internal-docs/VENDORING.md` — the convention T4/T8/T9/T12 all follow | **M7** |
| D10 | `.env.example` — revised provider set | — |
| D11 | root `LICENSE` — the repo is public and has none | M2b |

## Out of scope

DanisHack modules (T4/T8/T12) · `desk/data.py` *implementation* (T2 — T1 ships the Protocol only) · valuation (T9) · Hermes (T13) · the FMP purchase (T18) · the yfinance ToS decision (T19).

---

## M1 — engine entry: decided, with the rejected options recorded

Five options were considered; the matrix is two-dimensional (dependency control × source editability):

| | Controls deps? | Source editable by T6? | Verdict |
|---|---|---|---|
| (a) pinned git dependency | ✗ upstream's pyproject wins | ✗ lives in site-packages | **Dead.** T6 must edit `graph/setup.py`'s hardcoded analyst factory dict |
| (d) resolver `override-dependencies` | ✓ | ✗ | Solves only half; dies to T6 |
| (e) git submodule at `engine/` | ✓ | partial — edits need a push target, i.e. a fork | Collapses into (b) |
| (b) GitHub fork | ✓ | ✓ | Needs a **public fork** under the org + a permanent rebase obligation |
| **(c) vendor source at `engine/`** | ✓ | ✓ | **Chosen.** Matches frozen DESK_DESIGN §3's layout |

**Cost of (c), accepted:** ~10 MB of foreign source (as a copy at a pinned SHA — **one** commit, not 257; see M2b); re-vendoring is a fresh copy; Apache-2.0 §4(b) obliges us to state our changes. §4(d) does not bind — upstream ships no `NOTICE` (measured).

## M2 — the quality gate must not leak (rev 3: corrected)

**Rev 2 contradicted itself here.** It mandated "enumerated file list, never a directory glob" and then printed `extend-exclude = ["engine/tradingagents/**"]`, which is a glob and exempts exactly the files T6 will add. Corrected:

`engine/.vendored-manifest` is the **single source of truth** — one line per file, `sha256␠path`, generated from the **pinned upstream SHA, never from the local working tree**. `make tooling-config` regenerates all three tool exclusion lists from it, so they cannot drift:

| Tool | Mechanism | Why not the obvious one |
|---|---|---|
| ruff | `extend-exclude` = explicit paths from the manifest | a glob exempts T6's files forever |
| mypy | per-module `[[tool.mypy.overrides]] ignore_errors = true`, modules listed from the manifest | mypy's `exclude` does **not** stop analysis of an excluded module that is *imported* |
| pytest | `testpaths = ["tests"]` + `norecursedirs = ["engine"]` | otherwise it collects upstream's own `tests/` |

Anything under `engine/` **not** in the manifest is ours, and is linted, typed and tested.

## M2b — vendoring mechanic and integrity (rev 3, new)

- **Copy at a pinned SHA, not `git subtree`.** Rev 2 claimed "257 commits in our history"; that is subtree behaviour. A copy adds one commit and ~10 MB, and re-vendoring is a fresh copy rather than a merge. `versions.lock` holds the SHA.
- **These upstream files are deliberately NOT vendored** — they fight our tooling: `pyproject.toml` (uv would treat it as a workspace member; ruff resolves settings from the nearest one), `tests/` and any `conftest.py` (duplicate top-level `tests` module → mypy and pytest collection errors), `.github/`. Their removal is recorded in the statement of changes.
- **Dependency direction: `engine/` may import `desk`; `desk` must never import `engine`.** T6 puts first-party nodes inside `engine/` that call `desk.data`. Stating the rule so T6 does not invent one.
- **Integrity:** the manifest carries a sha256 per file, and invariant 6 asserts vendored content still matches. Without it an in-place edit to vendored source is invisible, which would undermine the Apache-2.0 statement-of-changes obligation.
- **Measured:** upstream ships `LICENSE` but **no `NOTICE`**, so Apache-2.0 §4(d) does not bind. §4(b) — stating changes — does. Rev 2's "retain NOTICE" criterion is withdrawn as unfounded.
- **This repo has no root `LICENSE` at all** (`git ls-files` → none). It is public and about to contain Apache-2.0 third-party source. **Adding one is in T1 scope**; the choice of licence is Sir's.

## M3 — sequencing, and CI (rev 3: corrected)

**Rev 2 had no orderable green intermediate.** Invariants 1/2/4 need the lockfile installed; invariant 5 needs the manifest; so `make test` could not be green until every deliverable landed at once — a big-bang commit, not ten verifiable steps. Worse, `ci.yml`'s `application suite` step flips from no-op to `make test` the instant a `Makefile` with a `test:` target appears, and runs it against a bare `setup-python` with **zero dependencies installed** — so invariants 1, 2 and 4 would fail on the very PR that introduces them, on the required status check.

**Two stages, each green before the next:**

| Stage | Lands | Green means |
|---|---|---|
| **A** | D1 `pyproject` · D5 lockfile · D4 `setup`+`test` · **`ci.yml` amended to `make setup && make test`** · D6 invariants **1, 2, 3, 4** · D2 Protocol · D7/D10/D11 | deps resolve and import, no GPL/AGPL, no OpenBB/backtrader/redis |
| **B** | D3 `engine/` · manifest · `tooling-config` · D6 invariants **5, 6** | vendored tree matches its manifest by hash, exclusions derived from it |

Amending `ci.yml` is **part of stage A**, not a follow-up.

## M3b — "green from a clean clone" made real

- `make setup` — creates `.venv` on Python 3.11, installs from the lockfile
- `requires-python = ">=3.11,<3.15"` — floor is DanisHack's verified matrix, ceiling is litellm's measured constraint
- A **real lockfile** with hashes; `versions.lock` separately records the TradingAgents SHA and provenance
- CI exists (`.github/workflows/ci.yml`, on `main` since `fd98f92`) and its `test` job is a required status check

## M5 — the invariant test (D6) (rev 3: corrected)

`tests/test_invariants.py`. Six assertions, and **the two "prove it" criteria become pytest cases rather than checkboxes a human ticks once**:

| # | Assertion | Stage |
|---|---|---|
| 1 | every runtime dependency imports | A |
| 2 | installed versions match the lockfile | A |
| 3 | no distribution in the resolved environment is GPL/AGPL — see below | A |
| 4 | `openbb`, `backtrader`, `redis` are absent | A |
| 5 | the derived exclusion lists equal the manifest, with a failure message distinguishing *stale manifest* from *unblessed new file* | B |
| 6 | every vendored file's sha256 matches the manifest | B |
| **7** | **assertion 3 detects a synthesised GPL distribution** (mutation test) | A |
| **8** | **a file added under `engine/` outside the manifest IS linted** — write one containing a deliberate lint error, assert `ruff check` exits non-zero | B |

**Assertion 3 must not key on Trove classifiers alone.** PEP 639 packages emit `License-Expression: GPL-3.0-or-later` and often carry **no classifier at all** — so a real GPL wheel would pass while a synthetic fixture written *with* a classifier "proves" the check works. Read `License-Expression`, `License`, **and** classifiers; treat absence of all three as **unknown, not clean**, and record that policy in `LICENSES.md`.

## M8 — `desk/data.py`, the seam (D2) (rev 3: methods enumerated)

**Rev 2 named zero methods** — T1's central seam deliverable had no acceptance surface. And `Protocol` is *structural*: mypy enforces nothing until something asserts conformance, and T1 ships no consumer. Both corrected.

The method set is derived from the 26 metrics in DESK_DESIGN §1 W2 and from T2's own Done criteria — every call carries `as_of` (T2 needs a TTL cache keyed on ticker/metric/date) and returns a value **plus a source tag** (T2 needs a forced failure to surface a *visible* fallback). Both are signature-level; omitting them would mean T2 edits the Protocol instead of satisfying it.

```python
@dataclass(frozen=True)
class Sourced(Generic[T]):
    value: T
    source: str          # "yfinance" | "fmp" | "fred" | "sec" | "finviz"
    as_of: date
    degraded: bool = False   # a fallback was used; T2 must log it

class MarketData(Protocol):
    def is_live(self, ticker: str) -> Sourced[bool]: ...
    def daily_bars(self, ticker: str, start: date, end: date) -> Sourced[DataFrame]: ...
    def quote_scalars(self, ticker: str, fields: Sequence[str], as_of: date) -> Sourced[Mapping[str, float]]: ...
    def quarterly_income(self, ticker: str, as_of: date) -> Sourced[DataFrame]: ...
    def annual_fundamentals(self, ticker: str, as_of: date) -> Sourced[Mapping[str, float]]: ...
    def estimates(self, ticker: str, as_of: date) -> Sourced[Mapping[str, float]]: ...
    def option_chain(self, ticker: str, expiry: date | None, as_of: date) -> Sourced[DataFrame]: ...
    def macro_series(self, series_id: str, start: date, end: date) -> Sourced[Series]: ...
    def screen(self, filters: Mapping[str, str], as_of: date) -> Sourced[DataFrame]: ...
```

T1 ships these with `NotImplementedError` bodies **and a conformance assertion** so mypy has something to fail:

```python
class _Unimplemented:  # noqa: D101
    ...
_: MarketData = _Unimplemented()   # mypy errors here if the Protocol drifts
```

The docstring carries the guard contract the ADR's caveats demand:

```
Every implementation MUST enforce, and T2 MUST test:
  (a) historical series -> minimum-row-count assertion.
      Measured: yfinance ^TNX returns 17 bars for period="2y", silently.
  (b) .info scalars (ATM IV, shortPercentOfFloat, shortRatio) -> per-FIELD
      schema assertion. Failure mode is a MISSING KEY, not a short series.
      TREAT NaN AS MISSING: SOUN's latest quarterly revenue is NaN.
  (c) ticker liveness -> is_live(). Measured: delisted tickers (TIVO, GIV,
      both in DESK_DESIGN's own example book) return ALL-MISS, no exception.
```

**Guard (d) is deliberately NOT here.** Rev 2 baked "rev Q/Q is single-sourced on yfinance at the $19 tier" into a *provider-agnostic* interface, while T18 and T19 — the tickets that decide the tier and the ToS question — are out of scope and unresolved. It moves to `SUPERSEDED.md` as a T2 policy note.

## M6 + M11 — `LICENSES.md` (D7)

Composite licences must not be flattened to "MIT":

- **litellm** — MIT, **except `enterprise/`** under its own licence
- **langfuse** — MIT Expat, **except `ee/`, `web/src/ee/`, `worker/src/ee/`**

Both carry a **do not vendor or enable EE paths** constraint.

**M11:** this file is public. It records *what this project does and why*, dated and SHA-stamped — not adverse legal characterisations of named third-party repos. "Not used — licence terms could not be confirmed as of 2026-08-18 at `<SHA>`" is the register. Header: *engineering record, not legal advice.* The vendor-by-vendor assessments stay in the ADR's scoring worksheet.

## M9 — pandas provenance

`versions.lock` records that **`financetoolkit` forces `pandas==3.0.5`**, that DanisHack's 160 tests pass under both 2.x and 3.0.5, and — **not yet measured** — whether financetoolkit's drawdown-duration/recovery functions run under pandas 2.x. That single measurement is the escape route if the pin ever breaks; it is a T1 note, not a T1 task.

## M10 — engine dataflow ownership

ADR 0001 drops OpenBB **and** Finnhub; frozen §3 assigned the engine's primary source to `openbb_mcp.py`, which will not exist. Upstream does ship `alpha_vantage`, `y_finance` and `fred` dataflows, so the engine is not dataless — but **nobody owns repointing `engine/dataflows/` at `desk/data.py`**. T1 records this in `SUPERSEDED.md` as an unassigned action item. It is **not** T1 work.

## M4 — `SUPERSEDED.md` (D8)

`TICKETS.md` and `DESK_DESIGN.md` are frozen and must not be edited. A new file violates nothing and makes the drift greppable. It enumerates each overridden line: T2's Adopt list, T2's Done criterion, §2's `pip install openbb` block, §3's `openbb_mcp.py`, T9's donor, T18's tier — plus the unassigned M10 owner.

## M7 — `VENDORING.md` (D9)

T4, T8, T9 and T12 each vendor from a different upstream. One convention, defined once:

- location: `engine/` for the committee engine, `desk/vendor/<name>/` for module-level ports
- provenance: `<dir>/PROVENANCE.md` — upstream URL, SHA, date, files taken, local diffs, licence
- exclusion policy: enumerated manifest, never a glob (M2)
- mypy: `ignore_missing_imports` for untyped `yfinance`/`finvizfinance`/`financetoolkit` only, listed per-module — never globally

## Done criteria

**Stage A**
- [ ] `make setup && make test` green from a clean clone on Python 3.11
- [ ] `ci.yml`'s `application suite` step runs `make setup && make test` (not `make test` alone)
- [ ] invariants 1–4 and 7 pass; **7 proves 3 can fail**
- [ ] `pip list | grep -Ei 'openbb|backtrader|redis'` returns nothing
- [ ] root `LICENSE` exists

**Stage B**
- [ ] `engine/` present at the pinned SHA; upstream `pyproject.toml`, `tests/`, `.github/` absent; `PROVENANCE.md` states every change
- [ ] `make vendor-manifest` fetches from the **pinned upstream SHA**, not the working tree, and fails closed if upstream is unreachable
- [ ] invariants 5, 6 and 8 pass; **8 proves an unblessed file under `engine/` is linted**
- [ ] `make test` still green

**Both**
- [ ] `LICENSES.md`, `SUPERSEDED.md`, `VENDORING.md` exist and carry the findings above
- [ ] `internal-docs/TICKETS.md` and `internal-docs/DESK_DESIGN.md` **unmodified**
- [ ] `score.py --check` still passes (CI enforces it)

## Open — needs Sir, not blocking stage A

**Which licence for the root `LICENSE`?** The repo is public and will contain Apache-2.0 third-party source. Apache-2.0 is the low-friction choice (matches the vendored engine, patent grant); MIT is simpler; a proprietary/all-rights-reserved notice is also legitimate for a personal project. I will not pick this one.
