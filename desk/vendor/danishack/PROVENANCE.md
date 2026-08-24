# Provenance — DanisHack/ai-hedge-fund

- **Upstream:**  https://github.com/DanisHack/ai-hedge-fund
- **SHA:**       `6d7a3abb269c96c7e25ac89bf05c8208784ccd18`
- **Retrieved:** 2026-08-21
- **Licence:**   MIT (cleared in `internal-docs/LICENSES.md`, 2026-08-18)

## What was taken

**No file was copied.** What was adopted from
`src/backtest/portfolio_tracker.py::check_stop_orders` is the **stop-order
logic and its trigger precedence**, re-expressed in `desk/exit_rules.py`
against our own `PositionState`.

A verbatim copy was the wrong call and `desk/vendor/danishack/` holds no code:

- upstream's function is a **backtester method** that mutates
  `self.positions`, `self.cash` and `self.trades`, and **auto-sells**. The
  Desk places no orders (DESK_DESIGN D5), so the side effects are not merely
  unwanted, they are forbidden;
- it depends on upstream's `StopLossConfig`, `Trade`, `HoldingDetail` and
  `PortfolioSnapshot` models, none of which we use;
- T4 adds two rules it lacks, which changes the shape of the result.

Per `internal-docs/VENDORING.md` §1, a *pattern* read but not copied is cited
rather than vendored. This file is that citation, and the module docstring
carries it too.

## What was preserved exactly

| Property | Detail |
|---|---|
| **Trigger precedence** | fixed stop → trailing stop → take-profit, upstream's `if reason is None` short-circuit order. This is the thing actually worth adopting: "exactly the kind of thing you get wrong on a first pass and only notice when two rules fire on the same bar" |
| **Inclusive boundary** | `>=`, not `>`, on all three comparisons |
| **Percentage arithmetic** | `(avg_cost - price) / avg_cost`, `(hwm - price) / hwm`, `(price - avg_cost) / avg_cost` |
| **High-water-mark default** | falls back to `avg_cost`, matching `pos.get("high_water_mark", avg_cost)` |
| **One exit per position per cycle** | upstream deletes the position after one sell; we return at most one `triggered` |

## Deliberate deviations

| # | Deviation | Why |
|---|---|---|
| 1 | **Non-positive price or cost RAISES** | Upstream does `if price is None or price <= 0: continue`, silently skipping. For a backtester that is fine. Here it would render HOLD on unreadable data, and a health report that says HOLD because it could not read the price reads as an all-clear |
| 2 | **Units are explicit** (`price` / `pct` / `days` / `flag`) | Upstream is percentage-only. `config/book.yaml` is human-authored and naturally mixes "$150 stop" with "8% trailing". Inferring the unit from magnitude would misread a $0.40 stop on a $0.50 stock as 40% |
| 3 | **Losing triggers are retained** in `Decision.also_fired` | Upstream reports one reason and discards the rest. For an audit trail, knowing the thesis was already dead when the stop fired is worth the two bytes |
| 4 | **Two rules added** — `time_stop`, `thesis_invalidation` | T4. **Appended** to the precedence order, never interleaved, so adopting the port did not quietly rewrite the semantics it was adopted for |
| 5 | No auto-sell, no cash, no commission or slippage | D5: no code path places an order. Commission/slippage belong to T8's backtest, not to rule evaluation |

## Tests

Upstream has **8** stop-order tests in `tests/test_portfolio_tracker.py`. All
8 are represented in `tests/test_exit_rules.py`, adapted to `PositionState`,
including its precedence test under the same name.

Carried caveat from `VENDORING.md` §6: those tests were written by the same
author in the same burst as the code, so they establish self-consistency, not
correctness against a specification. Each one was therefore **re-derived by
hand** here — the arithmetic in each ported test's docstring is that check.

---

*The Desk is an education-only research system. It places no orders.*
