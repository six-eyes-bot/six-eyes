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
make vendor-manifest      # fetches the PINNED UPSTREAM SHA and writes
                          # engine/.vendored-manifest as `sha256<space>path`
make tooling-config       # regenerates ruff/mypy/pytest exclusions FROM it
```

**The manifest is generated from the pinned upstream SHA, never from the local
working tree.** Listing the local tree is the obvious implementation and it is
wrong: re-running it after T6 would silently re-bless T6's new files as
vendored and exempt them forever. It fails closed if upstream is unreachable.

Each tool needs a different mechanism, and the obvious one is wrong in two of
the three cases:

| Tool | Mechanism | Why not the obvious one |
|---|---|---|
| ruff | `extend-exclude` = explicit paths | a glob exempts T6's files forever |
| mypy | per-module `ignore_errors` | mypy's `exclude` does **not** stop analysis of an excluded module that is *imported* |
| pytest | `testpaths` + `norecursedirs` | otherwise it collects the upstream's own tests |

The manifest carries a **sha256 per file** and an invariant asserts contents
still match — without it, an in-place edit to vendored source is invisible to
CI, which would undermine the Apache-2.0 statement-of-changes obligation. Anything else under `engine/` is **ours** and is checked. `tests/test_invariants.py` asserts the exclusion list still equals the manifest, so the two cannot drift apart silently.

Regenerate the manifest **only** when deliberately re-syncing to a new upstream SHA, and say so in the commit message.

## 4. Typing

`ignore_missing_imports` is granted **per module, listed explicitly** — never globally:

```toml
[[tool.mypy.overrides]]
module = ["yfinance.*", "finvizfinance.*", "financetoolkit.*"]
ignore_missing_imports = true
```

Adding a name here is a review-worthy change. A global `ignore_missing_imports = true` silently disables type checking against every dependency and must not be used.

## 4b. What NOT to vendor, and which way imports point

Vendoring a whole project drags in files that fight your tooling. **Omit these and record the omission** in `PROVENANCE.md`:

| File | Why |
|---|---|
| upstream `pyproject.toml` | uv treats a nested one as a workspace member; ruff resolves settings from the *nearest* one |
| upstream `tests/`, `conftest.py` | a second top-level `tests` package → mypy "duplicate module" and pytest rootdir errors |
| upstream `.github/` | their CI is not ours |

**Dependency direction: vendored code may import first-party code; first-party code must never import vendored code.** T6 puts our analyst nodes *inside* `engine/` and they call `desk.data`. Stating the rule so nobody invents a different one.

Prefer **a copy at a pinned SHA over `git subtree`** — a copy adds one commit, and re-vendoring is a fresh copy rather than a merge conflict.

## 5. Licence hygiene

- Copy the upstream `LICENSE` into the vendored directory. Apache-2.0 §4(b) requires **stating your changes** (§2 above). §4(d) requires retaining `NOTICE` **only if upstream ships one** — check before asserting it. (Measured: TradingAgents ships `LICENSE`, no `NOTICE`.)
- Record the vendoring in `internal-docs/LICENSES.md` — factually, dated and SHA-stamped. That file is public; see its header.
- **Never vendor from a repo with no LICENCE.** `td-02/ai-native-hedge-fund` has none — its hash-chained audit-log *idea* may be read and reimplemented, but no line of its code may be copied.
- **Check the grant clause, not the title.** `EmanueleSturzo/DCF-Valuation-Model`'s LICENSE is headed "MIT License" but deletes `modify` and `merge` from the grant and omits the warranty disclaimer. It cannot be vendored-and-adapted. Read the text.
- The invariant test asserts no GPL/AGPL distribution is in the resolved environment. It must read **`License-Expression`, `License` and Trove classifiers** — PEP 639 packages often carry no classifier at all, so a classifier-only check passes real GPL wheels. Absence of all three is **unknown, not clean**.

## 6. Tests come with the code

If the upstream has tests covering the modules taken, port them in the same commit and say how many pass. They are the reason vendoring is safer than rewriting.

Measured precedent: of DanisHack's 342 repo-wide tests, **160** cover the 11 modules T4/T8/T12 take, and all 160 pass in isolation in 3.55s under both pandas 2.x and 3.0.5 — importing only pytest, stdlib and the repo's own `src`.

**Caveat worth carrying:** those tests were written by the same author in the same three-day burst as the code. They establish self-consistency, not correctness against a specification. Where a ported module gates a real decision — `_analyze_trades` feeding T8's expectancy number — verify it independently against a hand-built fixture before trusting it.
