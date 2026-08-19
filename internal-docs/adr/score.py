#!/usr/bin/env python3
"""Recompute every weighted score in ADR 0001 from its sub-scores.

The first draft of 0001-scoring.md computed these by hand and got four of
twenty-one wrong. This script is the source of truth; the tables are generated
from it. Run:  python3 internal-docs/adr/score.py

Weights: reliability 40 · dependency economy 30 · subscription cost 30.
Economy rubric:  econ = 10 - 10 * net_new_packages / 80   (clamped 0..10)
Cost rubric:     cost = 10 - 1.5 * (usd_per_month / 50)   (clamped 0..10)
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
    ("TauricResearch/TradingAgents", 8, 6, 10, "PASSES fit gate; 31d idle, 8 rel/12mo, 19 contrib"),
    ("virattt/ai-hedge-fund", 8, 5, 10, "FAILS fit gate: persona architecture, not the 14-node graph"),
    ("DanisHack as DEPEND", 2, econ_from_net_new(8), 10, "econ MEASURED 2026-08-18: 8 net-new pkgs"),
    ("DanisHack as VENDOR", 9, 10, 10, "160 relevant tests pass; 0 net-new"),

    ("-- Decision 3: valuation --", None, None, None, ""),
    ("dafahentra/dcf-valuation-tool", 7, 9, 10, "canonical MIT, 207 LOC, numpy+scipy only"),
    ("EmanueleSturzo/DCF-Valuation-Model", 0, 10, 10, "BLOCKED: licence omits modify/merge grant"),

    ("-- Decision 4: data providers --", None, None, None, ""),
    ("A  yfinance+FRED+SEC+finviz  $0", 5, 10, cost_from_usd(0), "covers every required metric"),
    ("B19 A + FMP Starter    $19/mo", 7, 9, cost_from_usd(19), "estimates VERIFIED at Starter (us-flag)"),
    ("B49 A + FMP Premium    $49/mo", 7, 9, cost_from_usd(49), "adds 30y history + UK/CA we do not need"),
    ("C   A + FMP Ultimate   $99/mo", 7, 9, cost_from_usd(99), "adds 13F + 3000rpm"),
    ("E   A + EODHD all-in  $100/mo", 6, 8, cost_from_usd(99.99), "removes no dependency"),
    ("D   Finnhub all-in   $3500/mo", 9, 10, cost_from_usd(3500), ""),

    ("-- Decision: metrics library --", None, None, None, ""),
    ("financetoolkit", 8, 8, 10, "EXECUTED: max_dd+beta agree w/ empyrical; Sharpe is PER-PERIOD"),
    ("quantstats", 8, 7, 10, ""),
    ("empyrical-reloaded", 4, 9.5, 10, "248d idle, 0 releases/12mo, upstream dead 753d"),

    ("-- Gated / rejected --", None, None, None, ""),
    ("OpenBB + mcp-server", 8, econ_from_net_new(86), 10, "86 net-new pkgs"),
    ("Kronos", 4, econ_from_net_new(14), 10, "+987MB (not in the econ rubric; see note)"),
    ("QuantMind", 7, econ_from_net_new(69), 10, "69 net-new pkgs"),
    ("nautilus_trader", 9, econ_from_net_new(7), 10, "REJECTED ON FIT: live-execution platform vs D5"),
    ("vectorbt", 7, econ_from_net_new(40), 10, "Commons Clause, non-OSI"),
]

if __name__ == "__main__":
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
