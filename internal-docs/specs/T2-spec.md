# T2 Spec — Market data interface (stage A of two)

**Tier:** standard · **Branch:** `desk-t2-data` · **Base:** `main` @ 72a18db
**Authority:** `internal-docs/TICKETS.md` T2, as overridden by
`internal-docs/SUPERSEDED.md` and `adr/0001-dependency-selection.md` (Accepted).

T2 bundles two independent deliverables. This spec covers **stage A, the data
layer only**. The LiteLLM gateway is stage B, a separate branch and PR.

## Locked decisions

| # | Decision | Source |
|---|---|---|
| L1 | Ship the fallback **mechanism** with a stub secondary. Write the FMP adapter behind the same interface but mark it **unverified** — no key exists. **T18 remains the gate** for live verification and for the money. | Sir, 2026-08-20 |
| L2 | Two PRs, data layer first. | Sir, 2026-08-20 |
| L3 | yfinance primary, FMP Starter fallback, finvizfinance screener-only, FRED macro. **No OpenBB, no Finnhub.** | ADR 0001 / SUPERSEDED |

## Goal

`desk/data.py` ships a working `MarketData` implementation. The same call
returns the same shape from any backend; a forced primary failure surfaces a
**visible, logged** fallback; and a metric with **no** licensed fallback fails
loudly rather than degrading quietly.

## The fallback matrix is NOT uniform — this is the central design fact

Measured in ADR 0001 (§9.3, §9.9, and the $3,500/mo finding):

| Metric group | Primary | Fallback | Behaviour on primary failure |
|---|---|---|---|
| estimates, annual fundamentals, technicals | yfinance | FMP Starter ($19) | fall back, `degraded=True`, log WARNING |
| macro series | FRED | yfinance | fall back, `degraded=True`, log WARNING |
| **`rev Q/Q`** (quarterly income) | yfinance | **none at $19** — Starter is annual; quarterly is $49 | **RAISE** |
| **options IV, short % float** | yfinance | **none under $3,500/mo** | **RAISE** |
| screener | finvizfinance | none | **RAISE** |

A uniform "try primary, else secondary" wrapper would be **wrong** and would
manufacture exactly the silent-failure class this interface exists to prevent.
Fallback policy is therefore **declared per method**, and a method with no
fallback must never return a degraded value.

## Deliverables

| # | Deliverable |
|---|---|
| D1 | `desk/cache.py` — TTL cache keyed `(metric, ticker, as_of)`, **disk-backed**, with as_of-aware TTL |
| D2 | `desk/providers/base.py` — provider ABC, typed errors, the HTTP transport seam |
| D3 | `desk/providers/yfinance_provider.py` — primary; all nine methods it can serve |
| D4 | `desk/providers/fred_provider.py` — `macro_series` |
| D5 | `desk/providers/finviz_provider.py` — `screen` only. `ticker_fundament()` is broken upstream and MUST NOT be called |
| D6 | `desk/providers/fmp_provider.py` — secondary. **UNVERIFIED**: no key exists, wire format untested. Marked in code and docs |
| D7 | `desk/data.py` — `MarketDataService`, per-method fallback policy, guards (a)(b)(c) |
| D8 | tests — hermetic unit tests on fixtures; opt-in live contract tests marked `live` |

## Why the TTL cache is BUILT, not adopted

T2's ticket says to fold in DanisHack `src/data/cache.py`. Measured at
`6d7a3ab`, it is 50 lines and does not fit:

| It does | We need |
|---|---|
| in-memory, module-level singleton | The Desk is **cron-driven** (16:15 and 09:00 daily) — separate processes, so an in-memory cache has a ~0% hit rate across runs |
| one flat `default_ttl_minutes` | a **past** `as_of` is immutable and should cache indefinitely; **today** is volatile and must expire in minutes. One TTL cannot express both |
| `datetime.now()`, naive local time | date-keyed data that crosses timezones |
| unbounded growth, no eviction | a long-lived on-disk store |

Adopting 50 trivial lines that then need all four fixed is worse than writing
~80 correct ones. Same judgement the ticket queue itself already makes for
Ghostfolio (T3) and EmanueleSturzo (T9): adopt-first is the default, not a rule.
**No DanisHack code is vendored by T2.**

## Guards — each is a measured failure, and each gets a test

| Guard | Rule | Measured evidence |
|---|---|---|
| (a) | historical series enforce a **minimum row count**; short series RAISE | yfinance `^TNX` returns 17 bars for `period="2y"` but 1,254 for `"5y"` — no exception, no warning |
| (b) | `.info` scalars enforce **per-field** presence; **NaN is MISSING**, not a value | `revenueQuarterlyGrowth` is simply absent; SOUN's latest quarterly revenue is NaN while neighbours are populated |
| (c) | `is_live()` is called **before** anything else | delisted tickers return ALL fields missing with no exception — only a note on stderr. TIVO and GIV, two of the five positions in DESK_DESIGN's own example book, are delisted today |

Guard (b) is why a row-count floor is not sufficient on its own: the failure
mode for `.info` scalars is a missing key, not a short series.

## Cache semantics

Key: `(metric, ticker, as_of.isoformat())` — exactly the Protocol's signature,
which is why every method carries `as_of`.

| `as_of` | TTL | Why |
|---|---|---|
| strictly before today | 30 days | the past does not change; re-fetching is pure cost |
| today | 15 minutes | intraday volatility |
| future | **rejected** — raises | a look-ahead bug, not a cache miss |

Values are stored on disk under `.cache/` (git-ignored). **Only successful,
guard-passing reads are cached.** Caching a degraded or partial response would
make one transient upstream failure sticky for its whole TTL.

## Non-goals

LiteLLM gateway (stage B) · SEC EDGAR (no metric in DESK_DESIGN §1 W2 needs it;
13F is FMP Ultimate per ADR) · buying anything (T18) · the yfinance ToS
question (T19) · repointing `engine/dataflows/` (unassigned, before T6).

## Done criteria

- [ ] `make test` green; no network in the default suite
- [ ] a forced yfinance failure on a **fallback-eligible** method returns `degraded=True`, logs a WARNING naming both providers, and returns the same shape
- [ ] a forced yfinance failure on `option_chain` / `quarterly_income` **raises** — asserted explicitly, because degrading here is the bug
- [ ] guards (a)(b)(c) each have a test that **fails when the guard is removed**
- [ ] a future `as_of` raises
- [ ] cache hit avoids a second transport call — asserted by counting calls, not by timing
- [ ] `internal-docs/TICKETS.md` and `DESK_DESIGN.md` unmodified

---

*The Desk is an education-only research system. It places no orders.*

---

# Rev 2 — skeptic panel + pre-mortem applied

Run inline (Sir's setup forbids dispatching subagents), across three lenses:
red-team, pre-mortem, interface-contract. Ten findings, all must-fix.

## Measurement that changed the design

**FRED needs no API key.** Measured 2026-08-20:

| Endpoint | Result |
|---|---|
| `fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10` | **HTTP 200**, 268,427 bytes, 1962-01-02 → 2026-08-19 |
| `api.stlouisfed.org/fred/series/observations` (no key) | HTTP 400 — *"Variable api_key is not set"* |

So `macro_series` is fully functional in T2 with **zero credentials**, and UST
10Y is served by `DGS10` rather than by `^TNX`, which guard (a) exists because
of. `fredgraph.csv` is a graph-export endpoint rather than the documented API,
so: use it keyless by default, and prefer the official API when
`FRED_API_KEY` is present. Record it as working-but-undocumented.

## Must-fix, applied

| # | Finding | Change |
|---|---|---|
| M1 | "forced yfinance failure surfaces FMP" is untestable — L1 says FMP is unverified with no key | The fallback test injects a **stub secondary**. FMP is **never exercised** in the default suite. Stated in the Done criteria. |
| M2 | Guard (c) "call `is_live` first" is under-specified: it would re-enter the provider on every read, and `is_live` itself is a Protocol method | `MarketDataService` resolves liveness **once per `(ticker, as_of)`**, caches it, and `is_live()` itself does **not** re-enter the guard |
| M3 | Future-`as_of` rejection was placed in the cache | Moved to `MarketDataService`, before any provider call. The cache stays dumb — a look-ahead bug is a domain rule, not a cache miss |
| M4 | A non-atomic disk write corrupts the cache | Write to a temp file and `os.replace`. A corrupt or unreadable entry is treated as a **miss**, never an exception |
| M5 | Pickle in a disk cache is arbitrary code execution on read | **No pickle.** JSON for scalars/mappings, CSV for frames. A cache file can never execute |
| M6 | `Sourced.value` is a mutable DataFrame; two callers share one cached object | Return a **copy** on cache hit |
| M7 | "same shape from any backend" is asserted nowhere | A **provider conformance test**, parameterised over every provider, asserting return types and `Sourced` shape |
| M8 | `finvizfinance.ticker_fundament()` is broken upstream and nothing stops a future call | A source-grep **invariant test**, same pattern as T1's |
| M9 | The spec assumed FRED was reachable | Measured — see above |
| M10 | Guards tested against hand-written mocks would pass while the real failure still got through | **Guard tests use recorded REAL responses** — the actual 17-bar `^TNX`, the actual SOUN NaN quarter, an actual delisted ticker. Recorded once, committed as fixtures |

M10 is the highest-value item on this list. The guards exist because of three
specific measured failures; testing them against mocks written from my own
understanding of those failures would prove only that I am self-consistent.

## Rejected

- **Make `Source` an `Enum`.** It is `str` in the merged T1 Protocol. Changing a
  shipped interface for tidiness is not worth a fork; validate against a
  frozenset instead.
- **Vendor DanisHack `cache.py`.** See the main spec — measured, does not fit.
