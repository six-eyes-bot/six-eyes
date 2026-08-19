# Vendoring convention

Four tickets vendor code from four different upstreams — T1 (TradingAgents), T4/T8/T12 (DanisHack), T9 (dafahentra), and T7 reads a pattern from TradingAgents-astock. Without one convention each would invent its own and retro-edit `pyproject.toml`. This is that convention.

**Rule of thumb:** vendored code is *ours* the moment we copy it. Upstream's release cadence stops mattering; its licence does not.

---

## 1. Where it goes

| What | Location |
|---|---|
| The committee engine (whole project) | `engine/` |
| Module-level ports from another project | `desk/vendor/<upstream-name>/` |
| A *pattern* read but not copied | nowhere — cite it in the ticket and in `LICENSES.md` |

## 2. Provenance is mandatory

Every vendored directory carries `PROVENANCE.md`:

```markdown
# Provenance — <upstream name>

- Upstream:  https://github.com/<owner>/<repo>
- SHA:       <full 40-char SHA>          <- never a branch or tag alone
- Retrieved: YYYY-MM-DD
- Licence:   <SPDX>  (LICENSE copied to ./LICENSE)
- Files taken:
    src/foo.py -> desk/vendor/x/foo.py
- Local changes (Apache-2.0 §4(b) requires stating these):
    - repointed src.data.* imports at desk.data
    - <every other deviation>
```

The SHA also goes in `versions.lock`. A vendored directory without `PROVENANCE.md` fails review.

## 3. The quality gate must not leak

**Exclusions are an enumerated file list, never a directory glob.**

A glob like `exclude = ["engine/"]` exempts everything in that directory *forever* — including the four analyst nodes T6 adds **inside** `engine/`, which are the highest-value net-new files in Track B. They would be born outside lint, typing and tests and nobody would notice.

```bash
make vendor-manifest      # writes engine/.vendored-manifest from the pinned SHA
```

Ruff and mypy exclude exactly the files in that manifest. Anything else under `engine/` is **ours** and is checked. `tests/test_invariants.py` asserts the exclusion list still equals the manifest, so the two cannot drift apart silently.

Regenerate the manifest **only** when deliberately re-syncing to a new upstream SHA, and say so in the commit message.

## 4. Typing

`ignore_missing_imports` is granted **per module, listed explicitly** — never globally:

```toml
[[tool.mypy.overrides]]
module = ["yfinance.*", "finvizfinance.*", "financetoolkit.*"]
ignore_missing_imports = true
```

Adding a name here is a review-worthy change. A global `ignore_missing_imports = true` silently disables type checking against every dependency and must not be used.

## 5. Licence hygiene

- Copy the upstream `LICENSE` into the vendored directory. Apache-2.0 additionally requires retaining `NOTICE` and **stating your changes** (§2 above).
- Record the vendoring in `internal-docs/LICENSES.md` — factually, dated and SHA-stamped. That file is public; see its header.
- **Never vendor from a repo with no LICENCE.** `td-02/ai-native-hedge-fund` has none — its hash-chained audit-log *idea* may be read and reimplemented, but no line of its code may be copied.
- **Check the grant clause, not the title.** `EmanueleSturzo/DCF-Valuation-Model`'s LICENSE is headed "MIT License" but deletes `modify` and `merge` from the grant and omits the warranty disclaimer. It cannot be vendored-and-adapted. Read the text.
- The invariant test asserts no GPL/AGPL-classified distribution is in the resolved environment.

## 6. Tests come with the code

If the upstream has tests covering the modules taken, port them in the same commit and say how many pass. They are the reason vendoring is safer than rewriting.

Measured precedent: of DanisHack's 342 repo-wide tests, **160** cover the 11 modules T4/T8/T12 take, and all 160 pass in isolation in 3.55s under both pandas 2.x and 3.0.5 — importing only pytest, stdlib and the repo's own `src`.

**Caveat worth carrying:** those tests were written by the same author in the same three-day burst as the code. They establish self-consistency, not correctness against a specification. Where a ported module gates a real decision — `_analyze_trades` feeding T8's expectancy number — verify it independently against a hand-built fixture before trusting it.
