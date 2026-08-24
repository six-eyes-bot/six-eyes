# T4 decision log — exit-rule engine

Branch `desk-t4-exits` off `main` @ `fb57e75`. **Tier: standard** — deterministic
rules, no LLM calls, and D5 guarantees no order is ever placed, so the blast
radius is a report rather than a trade. The trigger-precedence logic is the
kind that is silently wrong, so it gets full mutation testing regardless.

## The ticket's claim, verified before relying on it

T4 says DanisHack has "three of the five rules implemented, tested, and with
the trigger-precedence question already answered." That is a README-shaped
claim, so it was measured at pinned SHA `6d7a3ab`:

| Claim | Measured |
|---|---|
| three rules exist | **True** — `check_stop_orders` implements fixed stop, trailing stop, take-profit |
| precedence is documented | **True** — numbered comments `1.`/`2.`/`3.` and an `if reason is None` short-circuit |
| tested | **True** — 8 stop-order tests in `tests/test_portfolio_tracker.py`, including `test_fixed_stop_takes_priority_over_trailing` |
| boundary | `>=`, not `>` — inclusive, and load-bearing |

## No code was copied

`desk/vendor/danishack/` holds a `PROVENANCE.md` and **no code**. Upstream's
function is a backtester method that mutates `self.positions`/`self.cash` and
**auto-sells** — side effects that D5 forbids outright — and it depends on four
upstream models we do not use. Per `VENDORING.md` §1 a pattern read but not
copied is cited, not vendored.

What was preserved exactly: the precedence order, the inclusive `>=` boundary,
the three percentage formulae, the high-water-mark default of `avg_cost`, and
one exit per position per cycle.

## Decisions

| # | Decision | Why |
|---|---|---|
| D1 | The two new rules are **appended** to the precedence order, never interleaved | Adopting a port for its precedence and then rewriting that precedence would discard the only thing worth adopting |
| D2 | **Units are explicit** (`price`/`pct`/`days`/`flag`) | Upstream is percentage-only; `book.yaml` is human-authored and naturally mixes "$150 stop" with "8% trailing". Inferring from magnitude would misread a $0.40 stop on a $0.50 stock as 40%. A test pins exactly that case |
| D3 | A `pct` threshold ≥ 1 is **refused** | `8` is a typo for `0.08`, not 800%. A rule that can never fire is a stop that silently is not there |
| D4 | Non-positive price or cost **raises** | Upstream `continue`s past it. Here that renders HOLD on unreadable data, and a health report saying HOLD because it could not read the price reads as an all-clear |
| D5 | Losing triggers retained in `also_fired` | Upstream reports one reason and discards the rest. Knowing the thesis was already dead when the stop fired is worth two bytes |
| D6 | The module is **pure** — no DB, no network, no clock | `PositionState` carries everything. This is what makes 100% branch coverage reachable rather than aspirational; T5 assembles the state |

## Per-step review (ship-workflow §6) — NON-SKIPPABLE

| # | Finding | Sev | Triage |
|---|---|---|---|
| T4-R1 | **A mutation deleting the `break` in `evaluate()` passed all 37 tests at 100% branch coverage.** No test had two armed rules of the same kind | **High** | **Fixed** — test added; the mutation now fails. Branch coverage is not behaviour coverage, and this is the proof |
| T4-R2 | The comment on that `break` claimed "the tightest wins by ordering". It does not — the first in book order wins | Med | **Fixed** — comment corrected to describe what the code does. A comment asserting behaviour the code lacks is worse than none |
| T4-R3 | The absolute-price take-profit branch had **no test**, and it is the form `config/book.example.yaml` actually ships | Med | **Fixed** — found by the coverage gate at 97% |
| T4-R4 | `class X(str, Enum)` flagged by ruff UP042 | Low | **Fixed** — `StrEnum`; messages already used `.value`, so no behaviour change |

**Rejected:** none.

## Mutation tests

| Mutation | Tests failed |
|---|---|
| precedence inverted (trailing before fixed) | 3 |
| boundary `>=` → `>` | 1 |
| `break` removed (same-kind double count) | **0 → 1 after T4-R1** |

## Verification

```
ruff check .   -> All checks passed!
mypy           -> Success: no issues found in 104 source files
pytest -q      -> 38 passed
make cover     -> desk/exit_rules.py 137 stmts, 50 branches, 100% (gate: --cov-fail-under=100)
```

`make cover` is wired into `make test`, so CI enforces the Done criterion
rather than trusting this note.

## Carried forward

- **`config/book.example.yaml` needs a `unit:` field per rule** (T5, when the
  book overlay is actually read into rules). T4's engine requires it; the T3
  example config predates it.
- **T5 assembles `PositionState`** from the book, the DB and a market feed —
  including the high-water mark, which nothing currently persists. Options are
  a new column or deriving it from `daily_bars` since `opened_at`; T5's call.
- `exit_rules.armed` in the T3 schema maps to `Rule.armed`. Nothing writes
  that table yet.
