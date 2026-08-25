# T8 decision log — stage A: the metrics that gate autonomy

Branch `desk-t8-eval` off `main` @ `6307300`. **Tier: high-stakes** — the
ticket's own classification, and the number this produces is the one T8 says
"gates autonomy".

T8 is large. **Stage A is the metrics core**, which is where the risk is.
Stage B is the two-arm experiment, and it needs a decision from Sir first
(below).

## The port was rejected, on evidence

T8 says "Port DanisHack's backtest module wholesale". `VENDORING.md` §6 says
verify `_analyze_trades` first "because it gates a real decision". Verified at
`6d7a3ab` against a hand-built fixture:

| | |
|---|---|
| buy 1 @ 100, sell @ 110 | +$10 |
| buy 1000 @ 100, sell @ 95 | −$5,000 |
| **actual** | **−$4,990** |
| **DanisHack reports** | **win rate 50.0%, profit factor 2.00** |

Five defects, all structural:

1. a round trip is appended **once per FIFO match, unweighted by quantity**;
2. `profit_factor` sums **percentages**, not currency;
3. returns come from raw prices — **gross**, while T8 requires *"net of
   spread, slippage and commission"* and *"do not assume frictionless fills"*;
4. a **flat** round trip is counted as a loss;
5. a sell with **no matching buy is silently discarded**.

Defect 3 is the one that matters most: it would have produced a gross number
under a name that implies net, for the metric that decides whether this system
is ever allowed to run unattended.

**`_analyze_trades` is not ported.** DanisHack's Sharpe, drawdown and
benchmark are sound and used as written — and its Sharpe **is** annualised,
which is the concern `SUPERSEDED.md` had flagged. This says nothing about the
modules T4 took; those were verified separately.

## Decisions

| # | Decision | Why |
|---|---|---|
| D1 | Expectancy in **currency, quantity-weighted, net of costs** | The three defects above. Mutation-tested: dropping quantity weighting fails 4 tests, dropping costs fails 2 |
| D2 | Costs are **per fill**, and an entry cost is **amortised per share** | A partial exit should carry its share of the entry cost, not all of it |
| D3 | Unmatched sell quantity is **returned**, not discarded | A short sale or a data gap should be visible |
| D4 | A flat trade is **neither** a win nor a loss | Counting 0 as a loss biases the win rate down |
| D5 | Drawdown reports **duration**, measured peak→recovery (or peak→end if still underwater) | T8: "the number that decides whether a system keeps running is the one you can sit through" |
| D6 | The Sharpe convention is **in the function name** | `annualised_sharpe` / `per_period_sharpe`. Measured 15.87× apart, matching the recorded 15.88× |

## Per-step review (ship-workflow §6) — NON-SKIPPABLE

| # | Finding | Sev | Triage |
|---|---|---|---|
| T8-R1 | **`sd == 0` did not catch a constant series.** Zero variance in exact arithmetic is ~1e-19 in floating point, and dividing by it produced a Sharpe of **5.8e16** — a number that would sail through any plausibility check a human applied to a report | **High** | **Fixed** with a threshold scaled to the data, plus a test that a genuinely tiny *real* variance still reports |
| T8-R2 | `Expectancy` has 12 fields; the empty-input path passed 11 positionally | Med | **Fixed** — constructed by keyword. Positional construction of a 12-field record was the underlying mistake |
| T8-R3 | The FIFO lot was `list[float \| date]`, needing a cast at every access | Med | **Fixed** — a `_Lot` dataclass. Heterogeneous lists are how a date ends up multiplied by a quantity |

**Rejected:** none.

## Verification

```
ruff check .   -> All checks passed!
mypy           -> clean
make test      -> all green (20 eval-metric tests)
```

## ⚠️ Stage B needs a decision before it can run

The experiment T8 actually specifies — committee vs deterministic baseline
over held-out dates — **requires real LLM calls**. Nothing in this project has
ever made one: every test to date injects a `completion_fn`.

Measured in T2: **~$0.62 per committee run**. A meaningful held-out sample is
tens to hundreds of runs, so the experiment costs real money and needs an
API key that does not yet exist.

It also has consequences beyond cost. T8 says: *"If the committee doesn't win
on (1), stop and reconsider before building Tracks C and D."* This is the
gate for the rest of the project, so the sample size and the dates are Sir's
call, not mine.

**Recorded, not decided.** Stage A ships the metrics; stage B waits.
