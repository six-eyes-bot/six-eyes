# T3 decision log — book schema + canonical ingest

Branch `desk-t3-book` off `main` @ `ef220f5`. **Tier: high-stakes** — this
creates the schema every other ticket writes into, and §4 says of it directly
that it "costs nothing now and a migration later."

## The governing sentence

> "An import that silently clobbers a stop loss is the single most damaging bug
> this system can have." — DESK_DESIGN §4.5

A stop is the only thing between a thesis going wrong and it going wrong
without limit. Everything below is arranged around that.

## Three gaps found INSIDE the frozen docs

§4 and §4.5 contradict each other. Recorded in `SUPERSEDED.md`, resolved in
`desk/db.py`:

| # | Gap | Resolution |
|---|---|---|
| G1 | §4.5 reconciles on `(ticker, account)`; §4's `positions` has **no `account` column** | Added, with `UNIQUE (ticker, account)`. Test proves the same ticker in two accounts stays two rows |
| G2 | §4.5 stamps `book.last_import_at`; §4 defines no `book` table | Added `book_meta(key, value)`; `days_stale()` serves W1's refusal |
| G3 | `positions.status` never enumerated | `{OPEN, UNMANAGED, CLOSED}` + CHECK. OPEN = imported **and** covered by `book.yaml` |

## Decisions

| # | Decision | Why |
|---|---|---|
| D1 | The UPDATE names its three columns **literally** | A loop over "whatever changed" is how `stop` eventually joins the SET clause during a refactor nobody reviews closely |
| D2 | Dry run operates on a **scratch copy** of the database | Rolling back is not enough. Opening the real path *creates* the file when absent and leaves WAL sidecars when present. "Writes nothing" is now literally true and the test hashes the file to prove it |
| D3 | `shutil.copy2`, never move, when archiving the raw CSV | The operator's export must survive an ingest that fails halfway |
| D4 | Foreign keys explicitly ON per connection | SQLite disables them **by default**. A schema full of unenforced REFERENCES looks exactly like one that is enforced |
| D5 | `types-PyYAML` added rather than exempting `yaml` | T1's house style — pandas is typed via stubs, not exempted. Lockfile diff is exactly one line, no version churn |
| D6 | T3 creates `tickets` and `verdicts` but writes no rows | They belong to T12/T7. The tables exist now because adding columns later is a migration |

## Per-step review (ship-workflow §6) — NON-SKIPPABLE

| # | Finding | Sev | Triage |
|---|---|---|---|
| T3-R1 | **The dry run created the database file.** Found in my own smoke test, not by a test I wrote — the Done criterion says it writes nothing, and creating a file is a write | **High** | **Fixed** — scratch copy (D2). Two tests: no file created when absent, byte-identical when present |
| T3-R2 | The structural "no book-owned column in the UPDATE" test **sliced source text** and missed a mutation that appended `stop = NULL` to the second line of a concatenated SQL string | **High** | **Fixed** — rewritten to trace every statement SQLite actually executes via `set_trace_callback`. Reading what ran beats reading what was written. Re-mutated: now both tests fail |
| T3-R3 | Two tests invented `thesis_run_id` values with no matching `runs` row | Med | **Tests fixed, schema vindicated** — the FK caught it, which is the point of D4 |
| T3-R4 | First `make test` after a fresh venv took 59.5s, the same signature as T2's network-fetch bug | Med | **Investigated, benign** — 95% CPU with no I/O stall; it is bytecode compilation (722 `__pycache__` dirs under litellm alone). Cold import 3.8s vs warm 2.2s, both with the local price map. Not a regression of the T2 fix |

**Rejected:** none.

## Mutation tests — the three most damaging failure modes

| Mutation | Tests that failed |
|---|---|
| UPDATE also sets `stop = NULL` | 2 (behavioural + SQL trace) |
| `--commit` becomes the default | 3 |
| CLOSED implemented as `DELETE` | 1 |

## Verification

```
ruff check .   -> All checks passed!
mypy           -> Success: no issues found in 102 source files
pytest -q      -> 113 passed in 7.27s
```

`TICKETS.md` and `DESK_DESIGN.md` unmodified.

## Carried forward

- **The Wells Fargo adapter is T15**, exactly as §4.5 directs — it needs a real
  export. The seam is a mapping dict; if adding it requires touching
  reconciliation, the seam was drawn wrong.
- **W1 must call `days_stale()` and refuse loudly above 3 days** (T5). T3
  provides the number; it does not enforce the refusal.
- `runs.token_cost` is populated from T2's ledger:
  `total_for_run(run_id)`. Nothing writes `runs` yet.
