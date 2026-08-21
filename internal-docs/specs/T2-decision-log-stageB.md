# T2 decision log — stage B, the LiteLLM gateway

Branch `desk-t2-llm` off `main` @ `cc3225c`.

## Per-step review (ship-workflow §6) — NON-SKIPPABLE

Run inline. Scope: `desk/llm.py`, `desk/spend.py`, `tests/test_llm.py`,
`tests/conftest.py`, `config/desk.example.yaml`.

| # | Finding | Sev | Triage |
|---|---|---|---|
| B-R1 | **Two independent clocks.** The ledger stamped rows with real UTC now while the budget asked an injected `today`. A budget reading a different day than the ledger writes is a ceiling that does not hold | **High** | **Fixed** — one injected `now`, used for both. Found by the tests, not by reading |
| B-R2 | **litellm fetches its price map over the network at import.** The default suite was not hermetic, and worse, spend-ceiling prices could change between runs with no code change | **High** | **Fixed** — pinned to the bundled map in `conftest.py` and `desk/llm.py`; test asserts both tier models are priced locally. Suite 59.6 s → 5.25 s |
| B-R3 | A cost function that raised propagated out of `complete()` and killed the run, but only on the injected path — the litellm path degraded to 0.0. Two behaviours for one failure | Med | **Fixed** — both paths degrade to $0.00 with an ERROR log, and the call is still recorded. A call that happened and was not recorded is worse than one recorded at an unknown price |
| B-R4 | An unpriceable model raises from the **cost** path, not the call path — so the committee would make a real, billed request and only then fail while recording it | Med | **Fixed** — models validated at construction |
| B-R5 | `anthropic/claude-opus-5` vs `claude-opus-5` would have been flagged as a reroute on every call | Low | **Fixed** — compared on the base name |
| B-R6 | Ceiling is checked before a call, but cost is only knowable after | Low | **Accepted and documented** — worst case is one call's overshoot, once. Stated in the error message and the config comment |

**Rejected:** none.

## Mutation test

Disabling the budget check (`if spent >= self._ceiling` → `if False`) fails 2
tests. A ceiling whose removal breaks nothing is decoration.

## Verification

```
ruff check .   -> All checks passed!
mypy           -> Success: no issues found in 97 source files
pytest -q      -> 91 passed in 5.25s
```

## Carried forward

- **No LLM provider key is exercised.** Every gateway test injects
  `completion_fn`; the one cost test uses litellm's real calculator on a
  synthetic `ModelResponse`. A live smoke call belongs wherever the first real
  agent lands (T6/T7).
- **T14 is now mostly configuration**, as its ticket predicts: tiers, the
  ceiling, and the reroute log all exist. What remains there is the cron
  kill-switch wiring.
