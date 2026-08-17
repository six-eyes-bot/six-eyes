# Six Eyes

Six Eyes is a self-hosted, cron-driven **AI investment committee** — a "desk" that
health-checks a live book of positions, screens for new setups, and writes
research theses with conviction scores. A committee of specialized agents
(analysts, a bull/bear debate, a risk manager, and a fund-manager verdict) reasons
over one ticker at a time, while a deterministic exit-rule engine watches open
positions and reports on their health.

## Education only. It places no orders.

Six Eyes is built for **research and education**. **No code path places a trade.**
Every workflow terminates at `AWAITING_APPROVAL` behind a human approval gate —
and this is structural, not a toggle. The custodian (Wells Fargo) exposes no
retail trading API, aggregators can read positions but explicitly cannot trade,
and none is added here. Every generated artifact carries an education-only footer.
**Nothing in this repository is investment advice.**

## Where to start

Read [`internal-docs/`](internal-docs/) — the design and plan live there:

- **[`DESK_DESIGN.md`](internal-docs/DESK_DESIGN.md)** — architecture, workflows, and rationale
- **[`TICKETS.md`](internal-docs/TICKETS.md)** — the build queue, one `/ship` per ticket (T1–T17)
- **[`T0_DEPENDENCY_AUDIT_PROMPT.md`](internal-docs/T0_DEPENDENCY_AUDIT_PROMPT.md)** — the dependency audit that runs *before* any code
- **[`SIX_EYES_BOOTSTRAP.md`](internal-docs/SIX_EYES_BOOTSTRAP.md)** — the human runbook
- `adr/` — architecture decision records (starting with T0's `0001-dependency-selection.md`)

## Repository layout

| Path | Purpose |
|---|---|
| `internal-docs/` | Design doc, ticket queue, ADRs, runbook — **start here** |
| `desk/` | Core system (data, ingest, committee, exit rules, screener, ticket state) |
| `adapters/` | Broker/export adapters (e.g. the Wells Fargo CSV mapping) |
| `playbooks/` | YAML trade playbooks (screening edge, e.g. `edge_breakout_v2.yaml`) |
| `config/` | Configuration |
| `imports/` | Raw book imports (gitignored `*.csv`) |
| `hermes-skills/` | Scheduling / delivery / session-state skills |
| `tests/` · `tests/fixtures/` | Test suite and fixtures |

## Status

**Pre-implementation.** The tree is scaffolded and the design docs are in place;
no dependencies are installed yet. **T0 decides what gets installed** — see
[`internal-docs/T0_DEPENDENCY_AUDIT_PROMPT.md`](internal-docs/T0_DEPENDENCY_AUDIT_PROMPT.md).
