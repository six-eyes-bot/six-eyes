# T2 decision log — stage A, the data layer

Branch `desk-t2-data` off `main` @ `72a18db`. Spec: `T2-spec.md` (rev 2).

## Locked decisions

| # | Decision | Source |
|---|---|---|
| L1 | Ship the fallback **mechanism** with a stub secondary. Write the FMP adapter but mark it **unverified** — no key exists. T18 remains the gate for live verification and for the money. | Sir, 2026-08-20 |
| L2 | Two PRs, data layer first. | Sir, 2026-08-20 |

## Measurements

Every one taken in this branch, none inherited.

| Claim | Result |
|---|---|
| **FRED needs no API key** | `fredgraph.csv?id=DGS10` → **HTTP 200**, 268,427 bytes, 1962-01-02 → 2026-08-19. The documented API 400s without a key. So `macro_series` works with **zero credentials** |
| FRED provider live | 408 observations correctly windowed, `float64`, guard (a) fires on a 3-row window |
| **`^TNX` no longer reproduces** | T0 measured 17 bars for `period="2y"`. Under yfinance 1.6.0 it now returns **502**. See drift below |
| SOUN NaN quarter | **reproduces exactly** — 2026-06-30 is NaN while 2026-03-31 → 2025-03-31 are populated, and 2024-12-31 is NaN too |
| `revenueQuarterlyGrowth` absent | **reproduces** — NVDA `.info` has 184 scalar keys, not one of them that |
| Delisted tickers | **reproduce** — TIVO 11 keys, GIV 23 keys, no price field in either, no exception raised |
| DataFrame JSON round-trip | `orient="table"` alone drifts ~5e-11; with `double_precision=15` it is **bit-exact** |

## Drift — the `^TNX` measurement went stale

T1 recorded, present tense, that `^TNX` returns 17 bars for `period="2y"`. It
no longer does. That is not a reason to drop guard (a):

- the failure class is real and was observed in this system's own dependency;
- a row-count floor costs one comparison;
- and T2 no longer routes UST 10Y through `^TNX` **at all** — FRED's `DGS10`
  serves it keylessly, which is strictly better than the series that motivated
  the guard.

The stale note in `desk/data.py` has been corrected in place rather than
deleted, so the history of the claim survives. **Not escalated**: it changed a
docstring and one fixture strategy, not the plan.

## Decisions taken during execution

| # | Decision | Why |
|---|---|---|
| D1 | **The TTL cache is BUILT, not adopted** | T2's ticket says fold in DanisHack `src/data/cache.py`. Measured at `6d7a3ab`: 50 lines, in-memory with a module singleton, one flat TTL, naive `datetime.now()`. The Desk is **cron-driven** — separate processes at 16:15 and 09:00 — so an in-memory cache has a ~0% hit rate across runs, and one flat TTL cannot express *past is immutable / today is volatile*. Adopting 50 lines that then need all four fixed is worse than writing ~80 correct ones. Same judgement the ticket queue already makes for Ghostfolio (T3) and EmanueleSturzo (T9). **No DanisHack code is vendored by T2.** |
| D2 | Fallback policy is a **per-method table**, not a wrapper | The real matrix is not uniform. A generic try-primary-else-secondary would manufacture the exact silent failure this interface exists to prevent |
| D3 | `TickerNotLive` is **not** fallback-eligible | Asking a second provider the same meaningless question about a delisted symbol wastes a call and risks dressing an empty answer up as a real one |
| D4 | Guard failures **are** fallback-eligible | A bad response from provider A is precisely when B is worth trying. The fallback must clear the same guard, and if it does not, the **original** error is raised — never the fallback's, which would misattribute the failure |
| D5 | `Sourced` gains `cached: bool` | See review finding R7 |
| D6 | No pickle anywhere near the cache | A cache file must not be able to execute code when read |

## Per-step review (ship-workflow §6) — NON-SKIPPABLE

Run inline across red-team / pre-mortem / interface lenses; Sir's setup forbids
dispatching subagents. Scope: `desk/cache.py`, `desk/data.py`,
`desk/providers/*`, `tests/test_cache.py`, `tests/test_market_data.py`.

**Spec-stage findings (10, all applied — see T2-spec.md rev 2):** stub-secondary
naming, `is_live` re-entrancy, look-ahead placement, atomic writes, no-pickle,
copy-on-read, conformance test, the `ticker_fundament` invariant, the FRED
measurement, and **guard tests must use recorded real responses rather than
mocks**.

**Implementation-stage findings:**

| # | Finding | Sev | Triage |
|---|---|---|---|
| R7 | A cache hit returned `source="cache"`, **destroying provenance** — the one thing `Sourced` exists to carry. A cached read is still yfinance data | **High** | **Fixed.** Cache carries `meta`; `Sourced` gains `cached: bool`, orthogonal to `source`. Test asserts a cache hit still names `yfinance` |
| R8 | `quote_scalars` used `f in info`, so a key **present with value `None`** passed the guard and then died in `float()` with a `TypeError` — a crash instead of an actionable `DataQualityError` | **High** | **Fixed** + regression test |
| R9 | `.info` is loosely typed; a numeric-looking field can be a string, and a bare `float()` raises `ValueError`, which reads as our bug rather than upstream's bad data | Med | **Fixed** — `_as_floats` raises `DataQualityError` naming the offending values |
| R11 | FRED's CSV parser appended the value **before** parsing the date. A single unparseable date desynced the two lists, **silently shifting every later observation by one day** | **High** | **Fixed** — parse both, append both, or skip. Re-verified live: index monotonic, lengths equal |
| R3 | `_liveness` dict grows unbounded | Low | **Accepted.** The service is constructed per cron run; a long-lived process would need eviction. Recorded, not fixed |
| R12 | The finviz screener call is not live-verified | Low | **Accepted and recorded** — same class as FMP. Screener behaviour belongs to T11 |

**Rejected:** none. Every finding above survived verification.

## Proof the guards can fail

Not asserted — mutation-tested. Each guard disabled in turn:

| Guard disabled | Tests that failed |
|---|---|
| (a) minimum row count | 1 |
| (b) per-field presence / NaN | 2 |
| (c) liveness | 2 |
| look-ahead rejection | 1 |

A guard whose removal breaks nothing is decoration.

The `ticker_fundament` invariant is worth its own note: the first version
**grepped the source text and immediately produced a false positive** on
`finviz_provider.py`'s own docstring, which names the function in order to
forbid it. Rewritten with `ast`. Same false-positive class as T1's
pandas-is-GPL bug, where bundled licence text *discussing* the GPL matched a
naive regex — prose about a thing is not the thing.

## Verification

```
$ make test
ruff check .   -> All checks passed!
mypy           -> Success: no issues found in 94 source files
pytest -q      -> 67 passed in 6.51s
```

No network in the default suite. `TICKETS.md` and `DESK_DESIGN.md` unmodified.

## Carried forward

- **FMP is unverified.** `FMPProvider.VERIFIED is False`, asserted by a test.
  T18 owns the purchase and the live check.
- **The finviz screener is not live-verified.** T11 exercises it for real.
- **`rev Q/Q` has no fallback** at $19/mo, and **options IV / short interest
  have none at any price under $3,500/mo.** Encoded in `FALLBACK_POLICY` as
  single-element chains, and asserted by a test that they raise rather than
  degrade.
