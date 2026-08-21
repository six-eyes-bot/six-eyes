"""Test-suite bootstrap.

This module runs before any test imports litellm, which matters: litellm
fetches its model-price map over the NETWORK at import time unless
LITELLM_LOCAL_MODEL_COST_MAP is set. Measured 2026-08-20 — the first suite run
took 59.6s and subsequent ones 5.8s, which is what a one-time remote fetch
looks like.

Pinning it here makes the default suite genuinely hermetic. `desk/llm.py` sets
the same default for production, and for a stronger reason: a spend ceiling
computed from prices fetched off the internet can move without a code change.
"""

import os

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
