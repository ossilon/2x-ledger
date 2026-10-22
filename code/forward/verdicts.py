#!/usr/bin/env python3
"""Verdicts on the frozen hypotheses H1-H4, computed from the public files only.

Rules: protocol P1 in HYPOTHESES.md. The script reads the review run (ledger.csv rows for the as-of date and the
T12M rows of results/<month>/windows.csv), applies each pass rule and prints pass / fail / inconclusive / void
with the evidence. No judgment enters. With --record it appends verdict entries to the hash-chained ledger and
renders HYPOTHESES.md again.

    py -I code\\forward\\verdicts.py --asof 2026-09-30            the exploratory run (shaped the bands; tests nothing)
    py -I code\\forward\\verdicts.py --asof 2027-09-30            the review run
    py -I code\\forward\\verdicts.py --asof 2027-09-30 --record   append the verdicts (once)
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _paths  # noqa: E402,F401
import ledger  # noqa: E402

ROOT = _paths.ROOT
REVIEW_ASOF = "2027-09-30"
GROUPS = {"NVDA": ("NVDX", ("NVDL", "NVDU", "NVDG")), "TSLA": ("TSLT", ("TSLL", "TSLG"))}
EXPENSIVE = ("MSTU", "MSTX", "SMCX")
H1_MIN, H1_RHO = 15, 0.5
H2_GAP = 1.5
H3_MIN, H3_SHARE = 8, 0.5
H4_COST = 20.0


def window_cost_pct(fund_pct, fedfunds_pct, days):
    """P1 rule 3: the all-in cost beyond fed funds over a window, percent a year, calendar time."""
    return -np.log((1 + np.asarray(fund_pct, float) / 100) / (1 + np.asarray(fedfunds_pct, float) / 100)) * 365 / np.asarray(days, float) * 100


def load_review(asof, root=ROOT):
    """(ledger rows, T12M window rows with cost_pct) for one as-of date; the latest run per ticker when restated."""
    L = pd.read_csv(Path(root) / "ledger.csv", dtype=str).fillna("")
    L = L[L["asof"] == asof].sort_values("run_date_utc").drop_duplicates("ticker", keep="last").copy()
    L["ranked"] = L["ranked"].str.lower() == "true"
    L["vol_under_annual_pct"] = pd.to_numeric(L["vol_under_annual_pct"], errors="coerce")
    W = pd.read_csv(Path(root) / "results" / asof[:7] / "windows.csv")
    T = W[(W["asof"] == asof) & (W["window"] == "T12M")].copy()
    T["days"] = (pd.to_datetime(T["end"]) - pd.to_datetime(T["start"])).dt.days
    T["cost_pct"] = window_cost_pct(T["fund_pct"], T["fedfunds_pct"], T["days"])
    return L, T


def h1(L, T):
    m = T.merge(L[L["ranked"]][["ticker", "vol_under_annual_pct"]], on="ticker").dropna(subset=["cost_pct", "vol_under_annual_pct"])
    n = len(m)
    if n < H1_MIN:
        return "inconclusive", f"{n} ranked funds with a T12M window, below the minimum of {H1_MIN}"
    rho = float(m[["cost_pct", "vol_under_annual_pct"]].corr(method="spearman").iloc[0, 1])
    return ("pass" if rho >= H1_RHO else "fail"), f"Spearman {rho:.2f} over {n} funds (pass at or above {H1_RHO})"


def h2(T):
    cost = T.set_index("ticker")["cost_pct"]
    parts, gaps, void = [], [], []
    for stock, (trex, others) in GROUPS.items():
        present = [t for t in others if t in cost.index]
        if trex not in cost.index or not present:
            void.append(f"{stock}: {'the T-Rex fund ' + trex if trex not in cost.index else 'all other funds'} closed")
            continue
        top = cost[present].idxmax()
        gap = float(cost[trex] - cost[top])
        gaps.append(gap)
        parts.append(f"{stock}: {trex} {cost[trex]:.1f} against {top} {cost[top]:.1f}, gap {gap:.1f}")
    if void:
        return "void", "; ".join(void + parts)
    return ("pass" if all(g >= H2_GAP for g in gaps) else "fail"), "; ".join(parts) + f" (pass at or above {H2_GAP} in both groups)"


def h3(L, T):
    m = T.merge(L[L["ranked"]][["ticker"]], on="ticker")
    up = m[m["stock_pct"] > 0]
    n = len(up)
    if n < H3_MIN:
        return "inconclusive", f"{n} ranked funds on a stock that rose, below the minimum of {H3_MIN}"
    beat = up[up["fund_pct"] > 2 * up["stock_pct"]]
    share = len(beat) / n
    names = ", ".join(sorted(beat["ticker"])) or "none"
    return ("pass" if share <= H3_SHARE else "fail"), f"{len(beat)} of {n} funds returned more than twice their stock ({share:.2f}; pass at or below {H3_SHARE}): {names}"


def h4(T):
    cost = T.set_index("ticker")["cost_pct"]
    present = [t for t in EXPENSIVE if t in cost.index]
    closed = [t for t in EXPENSIVE if t not in cost.index]
    if not present:
        return "void", "all three funds closed: " + ", ".join(closed)
    parts = [f"{t} {cost[t]:.1f}" for t in present]
    note = f"; closed and out of the test: {', '.join(closed)}" if closed else ""
    ok = all(cost[t] > H4_COST for t in present)
    return ("pass" if ok else "fail"), ", ".join(parts) + f" percent a year (pass above {H4_COST} for each){note}"


def evaluate(asof=REVIEW_ASOF, root=ROOT):
    L, T = load_review(asof, root)
    r1, e1 = h1(L, T)
    r2, e2 = h2(T)
    r3, e3 = h3(L, T)
    r4, e4 = h4(T)
    tag = f"review run as of {asof}: "
    return [{"id": "H1", "result": r1, "evidence": tag + e1}, {"id": "H2", "result": r2, "evidence": tag + e2},
            {"id": "H3", "result": r3, "evidence": tag + e3}, {"id": "H4", "result": r4, "evidence": tag + e4}]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--asof", default=REVIEW_ASOF)
    ap.add_argument("--record", action="store_true")
    a = ap.parse_args(argv)
    out = evaluate(a.asof)
    label = "" if a.asof == REVIEW_ASOF else "  [not the review run: this tests nothing]"
    for v in out:
        print(f"{v['id']} {v['result']:12s} {v['evidence']}{label}")
    if a.record:
        if a.asof != REVIEW_ASOF:
            sys.exit(f"refusing to record verdicts from {a.asof}; protocol P1 names {REVIEW_ASOF}")
        for v in out:
            ledger.append({"kind": "verdict", **v})
        (ROOT / "HYPOTHESES.md").write_text(ledger.render(), encoding="utf-8", newline="\n")
        print(ledger.verify())
    return 0


if __name__ == "__main__":
    sys.exit(main())
