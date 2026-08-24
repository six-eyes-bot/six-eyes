# T5 decision log — health report + staleness guard

Branch `desk-t5-health` off `main` @ `7a9bbcb`.

## Tier override: standard, not the ticket's `micro`

TICKETS T5 reads in full: *"Unchanged from v1. Build. Stale book produces a
refusal, not a report."* That is a one-liner, but **DESK_DESIGN §5 Phase 2**
scopes the same work far wider — a report renderer, the staleness guard, the
assembly layer, and an exit rule T4 does not have. Announced and treated as
standard.

## A gap between TICKETS and DESK_DESIGN

§5 Phase 2 requires the engine to cover "at minimum: stop breach, trailing
stop, time stop, thesis-invalidation flag, **earnings-proximity alert**".
T4's ticket named a different five and T4 shipped those.

| Source | Rules |
|---|---|
| TICKETS T4 | fixed stop · trailing · **take-profit** · time stop · thesis invalidation |
| DESK_DESIGN §5 Phase 2 | stop breach · trailing · time stop · thesis invalidation · **earnings proximity** |

The union is six. T5 adds the missing one.

## The word "alert" is load-bearing

§5 says "earnings-proximity **alert**", not an exit rule — so it never causes
one. `ALERT_ONLY` rules are evaluated **outside** `PRECEDENCE`, because they
are not competing to decide an exit. Auto-exiting before every earnings date
would quietly close half the book four times a year, and an alert that
suppressed the real exit reason would be worse still.

`Decision.alerts` is kept separate from `Decision.also_fired`: the latter holds
**exit** rules that lost on precedence. Conflating "this would have exited too"
with "look at this" would misreport both.

## Decisions

| # | Decision | Why |
|---|---|---|
| D1 | Staleness is an **exception**, not a report field | A caller that forgets to check a field still gets stopped. §4.5: a report against a stale book "is worse than no health report, because it reads as current" |
| D2 | `BookNeverImported` is distinct from `BookStale` | The operator is told to import, not to re-import |
| D3 | Freshness is asserted **before** any evaluation | Otherwise a stale book with missing prices reports "not evaluated" instead of refusing. Pinned by a test |
| D4 | A position with no price, or no cost basis, is **not** a HOLD | It is a position we did not check. Saying HOLD would be a false all-clear — the same class as the UNMANAGED rule |
| D5 | `horizon: 2w+` is **not** parsed into a time stop | It is free text; inventing a day count would fabricate an exit rule the operator never wrote. A time stop must be stated as one |
| D6 | Earnings dates come from `book.yaml`, by hand | A provider-backed date needs a new method on the `MarketData` Protocol, which T2 does not ship. Widening a merged interface from T5 is not justified for one field; recorded as a follow-up |

## Per-step review (ship-workflow §6) — NON-SKIPPABLE

| # | Finding | Sev | Triage |
|---|---|---|---|
| T5-R1 | `config/book.example.yaml` produced **two identical `fixed_stop` rules** — `stop: 150.00` and an explicit `fixed_stop` entry both map to one condition | Med | **Fixed.** Harmless at runtime (one trigger per kind) but a confusing thing to ship as the file people copy. Test asserts no duplicate kinds in the example |
| T5-R2 | The coverage gate dropped to **88.8%**: engine code added in T5 was tested from `test_health.py`, not the engine's own suite | Med | **Fixed** — 9 engine-level tests added. The gate caught it, which is the argument for wiring `make cover` into `make test` |
| T5-R3 | A T3 test pinned the OLD redundant example shape and failed | Low | **Test updated**, not the config. The failure was correct |
| T5-R4 | A stale `next_earnings` in `book.yaml` would alert forever | Med | **Fixed** — a date in the past is "already reported", not proximity. Tested |

**Rejected:** none.

## Mutation tests

| Mutation | Tests failed |
|---|---|
| staleness guard disabled | 2 |
| UNMANAGED counted as HOLD | 1 |
| earnings alert promoted to an exit | 1 |

## Verification

```
ruff check .   -> All checks passed!
mypy           -> clean
pytest -q      -> all green
make cover     -> desk/exit_rules.py 160 stmts, 64 branches, 100%
```

Both Phase 2 Done criteria are asserted directly: the seeded five-position
book yields `5× HOLD · 0 EXITS TRIGGERED`, and moving one stop above spot
flips **exactly one** position to triggered.

## Carried forward

- **The high-water mark is still not persisted.** `check()` accepts one and
  falls back to `avg_cost`, so the trailing stop is correct only from cost
  until something supplies it. Options remain a column or deriving it from
  `daily_bars` since `opened_at`.
- **Nothing wires a real price feed in yet.** `check()` takes a mapping; the
  T2 `MarketDataService` call site belongs with the cron entrypoint (T13).
- **Earnings dates are manual** — see D6.
