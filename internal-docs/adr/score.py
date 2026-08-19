#!/usr/bin/env python3
"""Recompute the weighted scores in ADR 0001 from their sub-scores.

The first draft of 0001-scoring.md computed these by hand and got four of
twenty-one wrong. This script is the source of truth for every score it
carries. Run:  python3 internal-docs/adr/score.py
Self-check:   python3 internal-docs/adr/score.py --check

Weights: reliability 40 · dependency economy 30 · subscription cost 30.
Economy rubric:  econ = 10 - 10 * net_new_packages / 80   (clamped 0..10)
Cost rubric:     cost = 10 - 1.5 * (usd_per_month / 50)   (clamped 0..10)

TWO HONEST CAVEATS, both raised by the verification audit and disclosed
rather than silently reconciled:

1. Economy sub-scores are MIXED. econ_from_net_new() is applied wherever a
   net-new package count was actually measured; the remainder are judged
   values carried over from the narrative. Rows using the rubric are marked
   `rubric` in the note column; the rest are marked `judged`. Under the pure
   rubric quantstats would be 8.75 (88.3) and financetoolkit 9.125 (89.4),
   narrowing that margin from 3.0 to 1.1 -- same decision, thinner.

2. Some sub-scores rest on unmeasured inputs. Those rows are flagged
   `UNMEASURED` and their scores must not be cited as measured results.
"""

W_REL, W_ECON, W_COST = 40, 30, 30


def econ_from_net_new(n):
    return max(0.0, min(10.0, round(10 - 10 * n / 80, 2)))


def cost_from_usd(usd):
    return max(0.0, min(10.0, round(10 - 1.5 * (usd / 50), 2)))


def score(rel, econ, cost):
    return round(rel * W_REL / 10 + econ * W_ECON / 10 + cost * W_COST / 10, 1)


# (label, reliability, economy, cost, note)
ROWS = [
    ("-- Decision 1: committee engine (FIT-GATED, see note) --", None, None, None, ""),
    ("TauricResearch/TradingAgents", 8, 6, 10, "judged; PASSES fit gate; 31d idle, 8 rel/12mo, 19 contrib"),
    ("virattt/ai-hedge-fund", 8, 5, 10, "UNMEASURED econ (probe never completed); FAILS fit gate anyway: persona ensemble, not the 14-node graph"),
    ("DanisHack as DEPEND", 2, econ_from_net_new(8), 10, "rubric; econ MEASURED 2026-08-18: 8 net-new pkgs"),
    ("DanisHack as VENDOR", 9, 10, 10, "160 relevant tests pass; 0 net-new"),

    ("-- Decision 3: valuation --", None, None, None, ""),
    ("dafahentra/dcf-valuation-tool", 7, 9, 10, "judged; canonical MIT, 207 LOC, numpy+scipy only"),
    ("EmanueleSturzo/DCF-Valuation-Model", 0, 10, 10, "judged; BLOCKED: licence omits modify/merge grant"),
    ("Build valuation from scratch", 10, 10, 10, "judged; upper bound, costs the effort T9 avoids"),

    ("-- Ops layer --", None, None, None, ""),
    ("langgraph", 9, 10, 10, "judged; already transitive via TradingAgents, 0 net-new"),
    ("litellm", 8, 7, 10, "judged; 0d idle but 4,960 open issues (8.75/100 stars)"),
    ("langfuse", 8, 8, 10, "judged; 0d idle, MIT core, self-hostable"),

    ("-- Decision 4: data providers --", None, None, None, ""),
    ("A  yfinance+FRED+SEC+finviz  $0", 5, 10, cost_from_usd(0), "covers every required metric"),
    ("B19 A + FMP Starter    $19/mo", 7, 9, cost_from_usd(19), "estimates VERIFIED at Starter (us-flag)"),
    ("B49 A + FMP Premium    $49/mo", 7, 9, cost_from_usd(49), "adds 30y history + UK/CA we do not need"),
    ("C   A + FMP Ultimate   $99/mo", 7, 9, cost_from_usd(99), "adds 13F + 3000rpm"),
    ("E   A + EODHD all-in  $100/mo", 6, 8, cost_from_usd(99.99), "removes no dependency"),
    ("D   Finnhub all-in   $3500/mo", 9, 10, cost_from_usd(3500), ""),

    ("-- Decision: metrics library --", None, None, None, ""),
    ("financetoolkit", 8, 8, 10, "judged econ (rubric would be 9.12 -> 89.4); EXECUTED: max_dd+beta agree w/ empyrical, Sharpe is PER-PERIOD"),
    ("quantstats", 8, 7, 10, "judged econ (rubric would be 8.75 -> 88.3); 10 net-new, 8 of them plotting"),
    ("empyrical-reloaded", 4, 9.5, 10, "judged; 248d idle, 0 releases/12mo, upstream dead 753d"),
    ("ffn", 8, 5, 10, "judged; 14 net-new incl scikit-learn"),
    ("bt", 8, 4, 10, "judged; 16 net-new; weight-rebalancing model, not discrete tickets"),

    ("-- Gated / rejected --", None, None, None, ""),
    ("OpenBB + mcp-server", 8, econ_from_net_new(86), 10, "86 net-new pkgs"),
    ("Kronos", 4, econ_from_net_new(14), 10, "+987MB (not in the econ rubric; see note)"),
    ("QuantMind", 7, econ_from_net_new(69), 10, "69 net-new pkgs"),
    ("nautilus_trader", 9, econ_from_net_new(7), 10, "REJECTED ON FIT: live-execution platform vs D5"),
    ("vectorbt", 7, econ_from_net_new(40), 10, "Commons Clause, non-OSI"),
]

def self_check():
    """Verify the rubrics and the weighting are internally consistent.

    This exists because the hand-computed first draft shipped four wrong
    scores. Returns a list of failure strings; empty means clean.
    """
    fail = []

    # rubric boundary conditions
    for n, want in [(0, 10.0), (80, 0.0), (8, 9.0), (40, 5.0)]:
        got = econ_from_net_new(n)
        if got != want:
            fail.append(f"econ_from_net_new({n}) = {got}, expected {want}")
    for n in (200, -5):  # must clamp, never go out of range
        got = econ_from_net_new(n)
        if not 0.0 <= got <= 10.0:
            fail.append(f"econ_from_net_new({n}) = {got} escaped [0,10]")

    for usd, want in [(0, 10.0), (50, 8.5), (19, 9.43), (3500, 0.0)]:
        got = cost_from_usd(usd)
        if got != want:
            fail.append(f"cost_from_usd({usd}) = {got}, expected {want}")

    # weights must sum to 100, else scores are not out of 100
    if W_REL + W_ECON + W_COST != 100:
        fail.append(f"weights sum to {W_REL + W_ECON + W_COST}, not 100")

    # a perfect candidate must score exactly 100
    if score(10, 10, 10) != 100.0:
        fail.append(f"score(10,10,10) = {score(10, 10, 10)}, expected 100.0")
    if score(0, 0, 0) != 0.0:
        fail.append(f"score(0,0,0) = {score(0, 0, 0)}, expected 0.0")

    # every data row must be well-formed and in range
    for label, rel, econ, cost, _note in ROWS:
        if rel is None:
            continue
        for name, v in (("rel", rel), ("econ", econ), ("cost", cost)):
            if not 0 <= v <= 10:
                fail.append(f"{label}: {name}={v} outside [0,10]")
        s = score(rel, econ, cost)
        if not 0 <= s <= 100:
            fail.append(f"{label}: score {s} outside [0,100]")

    # the decisions the ADR actually rests on, asserted
    def s_of(prefix):
        for label, rel, econ, cost, _ in ROWS:
            if rel is not None and label.startswith(prefix):
                return score(rel, econ, cost)
        return None

    claims = [
        ("DanisHack as VENDOR", "DanisHack as DEPEND", "VENDOR must beat DEPEND"),
        ("financetoolkit", "quantstats", "financetoolkit must beat quantstats"),
        ("B19", "A  yfinance", "B19 ($19) must beat A ($0) or the ADR is wrong"),
        ("B19", "B49", "B19 ($19) must beat B49 ($49)"),
        ("dafahentra", "EmanueleSturzo", "dafahentra must beat the licence-blocked pick"),
    ]
    for hi, lo, why in claims:
        a, b = s_of(hi), s_of(lo)
        if a is None or b is None:
            fail.append(f"claim rows missing: {hi} / {lo}")
        elif not a > b:
            fail.append(f"{why}: {hi}={a} !> {lo}={b}")
    return fail


if __name__ == "__main__":
    import sys

    if "--check" in sys.argv:
        problems = self_check()
        for p in problems:
            print(f"FAIL  {p}")
        print(f"\nself-check: {len(problems)} failure(s)")
        sys.exit(1 if problems else 0)

    print(f"weights: rel {W_REL} / econ {W_ECON} / cost {W_COST}\n")
    print(f"{'candidate':38}{'rel':>5}{'econ':>7}{'cost':>7}{'SCORE':>8}  note")
    for label, rel, econ, cost, note in ROWS:
        if rel is None:
            print(f"\n{label}")
            continue
        print(f"{label:38}{rel:>5}{econ:>7}{cost:>7}{score(rel, econ, cost):>8}  {note}")

    print("\nFIT GATE (applied BEFORE scoring, per audit finding):")
    print("  A candidate must reproduce DESK_DESIGN §1 W2's 14-node graph")
    print("  (bull/bear researcher, research manager, trader, risk manager, fund manager).")
    print("  virattt scores 77.0 but is architecturally a persona ensemble -> gated out.")
    print("  This is stated because the formula did NOT make Decision 1; fit did.")
