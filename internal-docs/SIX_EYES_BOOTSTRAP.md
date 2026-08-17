# Six Eyes — Bootstrap Instructions

Run these **in Claude Code**, on your Mac, before `/ship` touches anything.

## Before you start

Have the four downloaded files somewhere reachable. Confirm `gh` is authenticated as the account with access to `arkadian-sparrow`:

```bash
gh auth status
```

If it authenticates as a personal account without org access, `gh repo create arkadian-sparrow/six-eyes` fails silently into your personal namespace. Check before, not after.

---

## Step 1 — Scaffold and repo

Paste this to Claude Code:

> Create a new project at `~/Projects/Six Eyes`. Inside it:
>
> 1. `git init` with `main` as the default branch
> 2. Create directories: `internal-docs/`, `internal-docs/adr/`, `desk/`, `tests/`, `tests/fixtures/`, `playbooks/`, `config/`, `imports/`, `hermes-skills/`, `adapters/`
> 3. Write a `.gitignore` covering: `.env`, `*.db`, `imports/*.csv`, `__pycache__/`, `.venv/`, `.DS_Store`, `*.pkl`, model weight caches (`.cache/huggingface/`)
> 4. Write `.env.example` with empty placeholders for every key the stack needs — Anthropic, and one placeholder per data provider still under consideration in T0. No real values.
> 5. Write a `README.md`: what Six Eyes is, that it is education-only and places no orders, and a pointer to `internal-docs/`
> 6. `gh repo create arkadian-sparrow/six-eyes --private --source=. --remote=origin` then push
> 7. On GitHub, enable branch protection on `main` requiring status checks before merge
>
> Do not install dependencies or scaffold Python packages yet — T0 decides what gets installed.

**A note on the folder name.** I've used `~/Projects/Six Eyes` with the space since that's the product name, but the *repo* is `six-eyes`. If you'd rather avoid the space in paths entirely — it does make shell work fiddlier — say `Six-Eyes` and everything else holds.

**Why branch protection matters here:** the ship-framework README is explicit that its own gates are advisory. Branch protection is the only layer that actually blocks a red merge. Set it now, while the repo is empty and it costs nothing.

---

## Step 2 — Place the docs

Copy the downloaded files in, with these renames:

| Downloaded file | Goes to |
|---|---|
| `THE_DESK_SPEC.md` | `internal-docs/DESK_DESIGN.md` |
| `THE_DESK_TICKETS.md` | `internal-docs/TICKETS.md` |
| `T0_DEPENDENCY_AUDIT_PROMPT.md` | `internal-docs/T0_DEPENDENCY_AUDIT_PROMPT.md` |
| `THE_DESK_TICKETS_v1.md` | discard, or `internal-docs/archive/` |

**The `DESK_DESIGN.md` rename is load-bearing.** Both `TICKETS.md` and the T0 prompt reference that exact path. If you rename it something else, grep and fix both.

Then commit:

```bash
git add . && git commit -m "docs: design, ticket queue, and T0 audit prompt" && git push
```

---

## Step 3 — Run T0

Paste the contents of `internal-docs/T0_DEPENDENCY_AUDIT_PROMPT.md` as a prompt. It's a measurement task — it produces `internal-docs/adr/0001-dependency-selection.md` and `0001-scoring.md`, and changes no code.

**Then stop and read it.** Status will be `Proposed`. You audit, you accept or amend, and only then does T1 start. Two recommendations in the ticket queue were already wrong on inspection; assume the ADR contains at least one more.

Once accepted, update the ADR status to `Accepted`, commit it, and apply the Action Items to `internal-docs/TICKETS.md` yourself.

---

## Step 4 — First `/ship`

```
/ship T1
```

with the T1 ticket body from `internal-docs/TICKETS.md`, amended by whatever T0 changed.

---

## Ticket order

```
T0 audit  →  [you audit]  →  T1 → T2 → T3 → T4 → T5
                                        ↓
                                   T6 → T7 → T8   ← gate
                                        ↓
                                   T9 → T10
                                        ↓
                                  T11 → T12
                                        ↓
                                  T13 → T14
                                        ↓
                              T15 (needs WF export)
                              T16 (optional, only if T8 says so)
                              T17 (research only, after T8 expectancy)
```

T8 is the real gate, and it now reports two numbers. Directional accuracy gates Tracks C and D. Expectancy net of costs gates everything about autonomy — T16, T17, and any future `RuleApprover`. Neither T16 nor T17 starts until T8 can score them.

---

## Two things to carry forward

**Nothing places an order.** Not in T12, not in T16, not as a config flag. Wells Fargo has no retail trading API anyway — aggregators can read positions but explicitly cannot trade — so this is structural, not just policy. Every workflow ends at `AWAITING_APPROVAL`.

**Every generated artifact carries the education-only footer.** Asserted in a test in T10, per the source post's own thesis card.
