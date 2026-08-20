# Provenance — TauricResearch/TradingAgents

- **Upstream:**  https://github.com/TauricResearch/TradingAgents
- **SHA:**       `01477f9afb7a47b849ed4c9259d3a9a4738d9fda`
- **Tag:**       `v0.3.1` — an **annotated** tag, so it carries two SHAs. The tag
                 object is `5a3d1b51d339202d03c4b57c1a1012f69376495f`; the commit
                 above is what is pinned, and what `versions.lock` records.
- **Committed:** 2026-07-05
- **Retrieved:** 2026-08-19
- **Licence:**   Apache-2.0 (`./LICENSE`, copied verbatim)
- **Method:**    copy of the source tarball at the pinned SHA — not `git subtree`.
                 One commit, not 257; re-vendoring is a fresh copy, not a merge.

Regenerate with `make vendor-engine && make vendor-manifest && make tooling-config`.
The rules below live in `scripts/vendor_engine.py` and nowhere else.

## Apache-2.0 obligations, as they actually apply

- **§4(a)** — `LICENSE` is copied into this directory.
- **§4(b) — statement of changes.** Required, and satisfied by the two sections
  below. This is the clause that makes the omissions worth enumerating.
- **§4(d) — NOTICE.** **Does not bind.** It only applies "if the Work ...
  contains a NOTICE file". Measured at the pinned SHA: upstream ships `LICENSE`
  and **no `NOTICE`**. An earlier draft of the T1 spec asserted a
  retain-NOTICE obligation; that assertion was unfounded and is withdrawn.

Separately, and recorded as fact rather than as any characterisation of
upstream: the appendix of upstream's `LICENSE` is unfilled — it reads
`Copyright [yyyy] [name of copyright owner]`. The body of the licence is intact
and unmodified, so the grant is unaffected.

## Files taken

84 files: `tradingagents/` (71), `cli/` (8), `scripts/` (1), `main.py`,
`README.md`, `CHANGELOG.md`, `LICENSE`. Every one is hashed in
`.vendored-manifest`. Nothing was edited on the way in — the manifest hashes are
of the **upstream** bytes, so any later in-place edit fails invariant 6.

## Files deliberately NOT taken, and why

Upstream has 158 files; we vendored 84. Omissions are part of the §4(b)
statement of changes.

| Omitted | Why |
|---|---|
| `pyproject.toml` | uv would treat a nested one as a workspace member, and ruff resolves settings from the **nearest** one — it would silently override ours for everything under `engine/`. Also the sole source of the `backtrader` / `redis` declarations. |
| `requirements.txt` | contains only `.` — i.e. "install the omitted `pyproject.toml`". |
| `tests/` (53 files), `test.py` | a second top-level `tests` package gives mypy duplicate-module errors and breaks pytest's rootdir detection. |
| `.github/` | their CI is not ours. |
| `assets/` (11 files, 4.0 MB) | README screenshots. 85% of the payload by bytes and zero function. **This omission is a deviation from the T1 spec's literal three-item list**, taken under `VENDORING.md` §4b's general rule; it leaves broken image links in the vendored `README.md`, which is harmless. |
| `Dockerfile`, `docker-compose.yml`, `.dockerignore` | all three build from the omitted `pyproject.toml` / `requirements.txt`, so vendoring them ships build files that cannot build. |
| `.env.example`, `.env.enterprise.example` | this repo is public and ships its own `.env.example`; `scripts/vendor_engine.py` refuses any `.env*` path unconditionally, not just these two. |
| `.gitignore` | ours governs the tree. |

## Local changes to the code taken

**None yet.** The 84 files are byte-identical to upstream at the pinned SHA,
which is what `.vendored-manifest` asserts on every CI run.

Changes are expected and must each be recorded here when they land:

- **T6** adds first-party analyst nodes *inside* `engine/`. They are **not**
  vendored, are **not** added to the manifest, and are linted, typed and tested
  like any other first-party code. That is what invariant 8 protects.
- **Unassigned (T1 spec M10):** nobody yet owns repointing `engine/dataflows/`
  at `desk/data.py`. ADR 0001 drops OpenBB and Finnhub; upstream does ship
  `alpha_vantage`, `y_finance` and `fred` dataflows, so the engine is not
  dataless. Tracked in `internal-docs/SUPERSEDED.md`.

## Dependency notes

- `backtrader>=1.9.78.123` (GPLv3+) and `redis>=6.2.0` are declared in
  upstream's `pyproject.toml`. **Measured at the pinned SHA: neither is
  imported by a single `.py` file in the repository.** Since the `pyproject.toml`
  is not vendored, they never enter our resolution at all; invariant 4 asserts
  their absence independently.
- `.env.enterprise.example` refers to **Azure OpenAI** deployment settings, not
  to a separately-licensed enterprise source tree. Checked because `litellm`
  and `langfuse` both carve out `enterprise/` / `ee/` directories under
  different terms; upstream has no such directory.

## Direction of dependency

`engine/` may import `desk`. **`desk` must never import `engine`.**

---

*The Desk is an education-only research system. It places no orders.*
