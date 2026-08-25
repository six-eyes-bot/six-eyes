"""First-party committee wiring, inside engine/ but outside `tradingagents/`.

Three constraints pin this location, and only this location satisfies all of
them:

  1. It must NOT live in `engine/tradingagents/graph/`. That package's
     `__init__.py` eagerly imports `trading_graph`, which imports both
     `llm_clients` and `langgraph.checkpoint.sqlite` — packages T6 measured
     and deliberately excluded. Importing anything from that directory drags
     all 21 back in.
  2. It must NOT live in `desk/`. VENDORING.md §4b: "engine/ may import desk;
     desk must never import engine." This module imports the engine's analyst
     nodes, so it belongs on the engine side of that arrow.
  3. It must NOT be a vendored file. Invariant 6 hashes those against
     upstream and no local edit can be blessed — verified, appending one
     comment to `setup.py` fails it.

So: a new first-party package inside engine/, absent from
`.vendored-manifest`, linted and typed like anything else.
"""
