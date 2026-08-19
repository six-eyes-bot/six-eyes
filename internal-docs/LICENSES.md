# Licence record

**This is an engineering record, not legal advice.** It states what this project does and why. Every entry is dated and, where it concerns third-party code, pinned to the SHA or version examined. Nothing here is a legal opinion about anyone else's work.

*Last reviewed: 2026-08-18. Enforcement is automated — see below.*

---

## How this is enforced

A hand-maintained table of 142 packages would be stale within a week. The enforcement is `tests/test_invariants.py`, which runs on every commit:

| Invariant | What it asserts |
|---|---|
| 3 | no strong-copyleft (GPL/AGPL) distribution in the resolved environment |
| 4 | `openbb`, `openbb-mcp-server`, `backtrader`, `redis` are absent |
| 7 | invariant 3 can actually fail — a mutation test, so the check cannot rot into a no-op |

**Detection policy.** Invariant 3 reads **`License-Expression`, `License` *and* Trove classifiers**. A classifier-only check is not sufficient: PEP 639 packages emit `License-Expression: GPL-3.0-or-later` and frequently carry no classifier at all, so a real GPL wheel would pass while a synthetic fixture written *with* a classifier would appear to prove the check works.

**Absence of all three is recorded as *unknown*, not *clean*.** Unknown packages are counted and printed, not failed — many well-behaved packages declare nothing, and failing on them would make the check unusable and therefore ignored. The count is surfaced so it cannot grow quietly.

**LGPL is treated as weak copyleft** and does not fail the check. We link dynamically and modify nothing.

## Decisions on record

| Item | Examined | Finding | What we do |
|---|---|---|---|
| `openbb`, `openbb-mcp-server`, all `openbb-*` providers | PyPI, 2026-08-18 | `AGPL-3.0-only` | **Not used.** Also +86 packages and no required metric the direct providers don't serve. `desk/data.py` would *import* it and this repo is public, so the combined work would be conveyed. |
| `backtrader` | PyPI 1.9.78.123, 2026-08-18 | `GPLv3+`; arrives only via an unused declaration in the vendored engine's `pyproject.toml`, imported by nothing | **Removed** from the vendored engine's dependency list. Reason is **dead weight** — a package nothing imports. Installing copyleft into a local virtualenv is not conveying it; an earlier draft of ADR 0001 overstated this and that framing is withdrawn. |
| `redis` | same | declared, never imported | Removed alongside. |
| `TauricResearch/TradingAgents` | v0.3.1, 2026-08-18 | Apache-2.0. Ships `LICENSE`; **ships no `NOTICE`** | Vendored at a pinned SHA. §4(b) obliges us to state our changes — recorded in `engine/PROVENANCE.md`. §4(d) does not bind, as there is no `NOTICE` to retain. |
| `litellm` | LICENSE text, 2026-08-18 | MIT, **except `enterprise/`** which is separately licensed | Used as a dependency only. **Do not vendor, and do not enable EE paths.** A row reading simply "MIT" would be materially wrong. |
| `langfuse` | LICENSE text, 2026-08-18 | MIT Expat, **except `ee/`, `web/src/ee/`, `worker/src/ee/`** | Same: dependency only, **do not vendor or enable EE paths**. |
| `EmanueleSturzo/DCF-Valuation-Model` | LICENSE text, 2026-08-18 | Terms could not be confirmed as granting modification rights | **Not used.** T9 uses `dafahentra/dcf-valuation-tool` instead. |
| `td-02/ai-native-hedge-fund` | repo contents, 2026-08-18 | No licence file present | **No code used.** Its hash-chained audit-log *approach* may be independently reimplemented; ideas are not copyrightable. |
| `simonlin1212/TradingAgents-astock` | 2026-08-18 | Apache-2.0 | Not vendored. If T7 adopts its quality-gate *pattern*, attribute here and in the source file. |
| `DanisHack/ai-hedge-fund`, `dafahentra/dcf-valuation-tool`, `financetoolkit`, `langgraph`, `finvizfinance` | 2026-08-18 | MIT | Cleared for vendoring/use. |
| `yfinance` | 2026-08-18 | Apache-2.0 | Cleared. Separately: it is an unofficial client and its terms of use for automated access are unresolved — that is **T19**, a product decision, not a licence one. |

## This repository's own licence

**Open — needs a decision.** This repo is public and is about to contain Apache-2.0 third-party source under `engine/`, and it currently has no root `LICENSE` file at all.

Reasonable options: **Apache-2.0** (matches the vendored engine, includes a patent grant), **MIT** (simpler, permissive), or an explicit **all-rights-reserved** notice (legitimate for a personal project — "public" and "open source" are not the same thing).

Tracked as T1 deliverable **D11**. Not chosen here.
