# T3 Spec — Book schema + canonical ingest

**Tier: high-stakes.** Not "standard". This creates the schema every other
ticket writes into, and DESK_DESIGN §4 says of it directly: *"it costs nothing
now and a migration later."* The ticket's own warning is sharper —
**"An import that silently clobbers a stop loss is the single most damaging bug
this system can have."** A stop is the only thing standing between a thesis
going wrong and it going wrong without limit.

**Branch:** `desk-t3-book` · **Base:** `main` @ ef220f5
**Authority:** TICKETS T3 · DESK_DESIGN §4, §4.5 (both frozen).

## Goal

`desk/ingest.py` reconciles a canonical CSV against the book, `--dry-run` by
default, and **never** touches a stop, target, exit rule or thesis link.

## Reconciliation — "these are the whole ballgame" (§4.5)

| Case | Rule |
|---|---|
| in CSV, not in book | new position, `status=UNMANAGED`, flagged as needing stops before it can be evaluated |
| in book, not in CSV | closed at the custodian. **Do NOT delete.** `status=CLOSED`, retain thesis and run history |
| in both | update qty and cost basis **only**. Never stops, targets, exit rules, `thesis_run_id` |
| qty changed | write to `audit` — a size change not made through a ticket is worth surfacing |
| always | write the raw CSV to `imports/` unmodified; every reconciliation replayable |

## Three gaps in the frozen schema

§4 and §4.5 disagree with each other. Recording rather than silently patching,
per the `SUPERSEDED.md` convention.

| # | Gap | Resolution |
|---|---|---|
| G1 | §4.5 matches on **`(ticker, account)`** but `positions(...)` in §4 has **no `account` column** | Add `account NOT NULL DEFAULT ''`. Without it the matching key cannot be expressed, and the same ticker in two accounts would collide into one row |
| G2 | §4.5 says stamp **`book.last_import_at`**, but §4 defines no `book` table | Add a `book_meta(key, value)` single-row-per-key table. W1's staleness refusal (default 3 days) reads it |
| G3 | `positions.status` values are never enumerated; §4.5 uses `UNMANAGED` and `CLOSED` | `status ∈ {OPEN, UNMANAGED, CLOSED}` with a CHECK constraint. `OPEN` = imported **and** covered by `config/book.yaml` |

## Two sources of truth, layered — never merged blindly (§4.5)

| Source | Owns |
|---|---|
| `imports/positions_YYYYMMDD.csv` (custodian) | ticker, qty, cost_basis, market_value, account |
| `config/book.yaml` (Sir) | stop, target, exit rules, thesis link, horizon |

A broker export contains *what* you hold, never *why* or *when you'd leave*.
The layering direction is one-way and absolute: **CSV may never write a
book.yaml-owned field.**

## Deliverables

| # | Item |
|---|---|
| D1 | `desk/db.py` — DDL for all seven §4 tables + `book_meta`, `schema_version`, foreign keys ON |
| D2 | `adapters/canonical.py` — header normaliser. **Fails loudly on an unrecognised column; never silently drops one** |
| D3 | `desk/book.py` — `config/book.yaml` loader (stops, targets, exit rules, thesis, horizon) |
| D4 | `desk/ingest.py` — reconciliation + `--dry-run` default / `--commit`, raw-CSV archival, audit rows |
| D5 | `config/book.example.yaml` · `tests/fixtures/positions_*.csv` |
| D6 | tests, including the Done criterion asserted directly |

## Done criteria

- [ ] **re-import with changed quantities preserves every stop, target and thesis link** — asserted explicitly, and mutation-tested
- [ ] `--dry-run` is the DEFAULT and writes nothing — asserted by hashing the DB file before and after
- [ ] an unrecognised CSV column **raises**; it is never dropped
- [ ] a ticker missing from the CSV becomes `CLOSED`, is **not deleted**, and keeps its `thesis_run_id`
- [ ] a qty change writes an `audit` row
- [ ] the raw CSV lands in `imports/` byte-identical
- [ ] `tickets.state` and `decided_by_kind` CHECK constraints reject bad values
- [ ] `book_meta.last_import_at` is stamped, and a staleness helper reports days
- [ ] `TICKETS.md` / `DESK_DESIGN.md` unmodified

## Non-goals

The Wells Fargo header adapter (**T15** — it needs a real export; §4.5 says so
explicitly) · exit-rule *evaluation* (T4) · the health report (T5) · ticket
sizing and approval (T12). T3 creates the `tickets` and `verdicts` tables but
writes no rows to them.

---

*The Desk is an education-only research system. It places no orders.*
