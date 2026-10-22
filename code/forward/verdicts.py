#!/usr/bin/env python3
"""Verdicts on the frozen hypotheses H1-H4, computed from the public files only, with protocol P1 and P2 enforced.

Rules: protocols P1 and P2 in HYPOTHESES.md. The script reads the review run (ledger.csv rows for the as-of date,
the T12M rows of results/<month>/windows.csv, register.csv and register_leverage.csv), decides each fund's
eligibility, applies each pass rule and prints pass / fail / inconclusive / void / unresolved with the evidence.
No judgment enters. With --record it appends verdict entries to the hash-chained ledger and renders HYPOTHESES.md.

Eligibility (P1 rules 1 and 9, P2 rule 4):
- universe: the 21 tickers frozen on 2026-10-22 (UNIVERSE below); any other ticker is ignored;
- closed: register.csv status "closed" with close_date on or before the review as-of: the fund leaves every test;
- leverage change: a period in register_leverage.csv that starts after 2026-09-30 and on or before the as-of: the
  fund leaves H2 and H4 (a change and a return to 2x inside the window both count, because the events are dated);
- a live, unchanged fund without its ledger row or its T12M window gives "unresolved": the verdict waits;
- every excluded fund and its reason appears in the evidence.
v0.1.0 took missing data as a closure and had no universe check (audit 2026-10-22, D01).

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
WINDOW_START = "2026-09-30"
UNIVERSE = ["AAPB", "AAPU", "AMDL", "AMZU", "ASTX", "CONL", "GGLL", "METU", "MSFU", "MSTU", "MSTX", "NVDG", "NVDL",
            "NVDU", "NVDX", "PLTU", "PTIR", "SMCX", "TSLG", "TSLL", "TSLT"]       # register.csv on 2026-10-22
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
    """The review tables for one as-of date: ledger rows (latest run per ticker), T12M windows with cost_pct,
    the public register and the public leverage periods."""
    root = Path(root)
    L = pd.read_csv(root / "ledger.csv", dtype=str).fillna("")
    L = L[L["asof"] == asof].sort_values("run_date_utc", kind="stable").drop_duplicates("ticker", keep="last").copy()
    L["ranked"] = L["ranked"].str.lower() == "true"
    L["vol_under_annual_pct"] = pd.to_numeric(L["vol_under_annual_pct"], errors="coerce")
    wpath = root / "results" / asof[:7] / "windows.csv"
    W = pd.read_csv(wpath) if wpath.exists() else pd.DataFrame(columns=["asof", "ticker", "window", "start", "end", "fund_pct", "stock_pct", "fedfunds_pct"])
    T = W[(W["asof"] == asof) & (W["window"] == "T12M")].copy()
    T["days"] = (pd.to_datetime(T["end"]) - pd.to_datetime(T["start"])).dt.days
    T["cost_pct"] = window_cost_pct(T["fund_pct"], T["fedfunds_pct"], T["days"]) if len(T) else []
    R = pd.read_csv(root / "register.csv", dtype=str).fillna("")
    epath = root / "register_leverage.csv"
    E = pd.read_csv(epath, dtype=str).fillna("") if epath.exists() else pd.DataFrame(columns=["ticker", "effective_from"])
    return {"asof": asof, "L": L, "T": T, "R": R, "E": E}


def eligibility(rev):
    """One row per universe ticker: closed, closed_note, lev_change, lev_note, ranked, has_window, has_row."""
    asof = pd.Timestamp(rev["asof"])
    R = rev["R"].set_index("ticker") if len(rev["R"]) else pd.DataFrame()
    L = rev["L"].set_index("ticker") if len(rev["L"]) else pd.DataFrame()
    T = rev["T"].set_index("ticker") if len(rev["T"]) else pd.DataFrame()
    E = rev["E"]
    rows = []
    for t in UNIVERSE:
        closed, closed_note = False, ""
        if t in R.index and R.at[t, "status"] == "closed" and R.at[t, "close_date"]:
            cd = pd.Timestamp(R.at[t, "close_date"])
            if cd <= asof:
                closed, closed_note = True, f"closed {cd.date()}"
        ev = E[(E["ticker"] == t) & (E["effective_from"] != "")] if len(E) else E
        changes = [pd.Timestamp(d) for d in ev["effective_from"]] if len(ev) else []
        changes = [d for d in changes if pd.Timestamp(WINDOW_START) < d <= asof]
        lev = bool(changes)
        rows.append({"ticker": t, "closed": closed, "closed_note": closed_note, "lev_change": lev,
                     "lev_note": f"leverage change {', '.join(str(d.date()) for d in changes)}" if lev else "",
                     "ranked": bool(L.at[t, "ranked"]) if t in L.index else False,
                     "has_row": t in L.index, "has_window": t in T.index})
    return pd.DataFrame(rows).set_index("ticker")


def _excluded(el, tickers, with_lev):
    """Names and reasons of excluded funds among `tickers`, and the unresolved ones."""
    out, unresolved = [], []
    for t in tickers:
        e = el.loc[t]
        if e["closed"]:
            out.append(f"{t} {e['closed_note']}")
        elif with_lev and e["lev_change"]:
            out.append(f"{t} {e['lev_note']}")
        elif not e["has_window"] or not e["has_row"]:
            unresolved.append(t)
    return out, unresolved


def _note(excluded):
    return ("; excluded: " + ", ".join(excluded)) if excluded else "; excluded: none"


def h1(rev, el):
    live = [t for t in UNIVERSE if not el.at[t, "closed"]]
    excluded, unresolved = _excluded(el, live, with_lev=False)
    if unresolved:
        return "unresolved", f"missing ledger row or T12M window for live funds: {', '.join(unresolved)}" + _note([f'{t} {el.at[t, "closed_note"]}' for t in UNIVERSE if el.at[t, "closed"]])
    use = [t for t in live if el.at[t, "ranked"]]
    T = rev["T"].set_index("ticker").loc[use]
    L = rev["L"].set_index("ticker").loc[use]
    m = pd.DataFrame({"cost": T["cost_pct"], "vol": L["vol_under_annual_pct"]}).dropna()
    n = len(m)
    closed_note = _note([f'{t} {el.at[t, "closed_note"]}' for t in UNIVERSE if el.at[t, "closed"]])
    if n < H1_MIN:
        return "inconclusive", f"{n} ranked funds with a T12M window, below the minimum of {H1_MIN}" + closed_note
    rho = float(m.corr(method="spearman").iloc[0, 1])
    return ("pass" if rho >= H1_RHO else "fail"), f"Spearman {rho:.2f} over {n} funds (pass at or above {H1_RHO})" + closed_note


def h2(rev, el):
    cost = rev["T"].set_index("ticker")["cost_pct"] if len(rev["T"]) else pd.Series(dtype=float)
    parts, gaps, void, excluded_all, unresolved_all = [], [], [], [], []
    for stock, (trex, others) in GROUPS.items():
        excluded, unresolved = _excluded(el, (trex,) + tuple(others), with_lev=True)
        excluded_all += excluded
        unresolved_all += unresolved
        ok = [t for t in (trex,) + tuple(others) if not el.at[t, "closed"] and not el.at[t, "lev_change"] and el.at[t, "has_window"]]
        if trex not in ok or not [t for t in others if t in ok]:
            if not unresolved:
                void.append(f"{stock}: {'the T-Rex fund ' + trex + ' is out' if trex not in ok else 'all other funds are out'}")
            continue
        present = [t for t in others if t in ok]
        top = cost[present].idxmax()
        gap = float(cost[trex] - cost[top])
        gaps.append(gap)
        parts.append(f"{stock}: {trex} {cost[trex]:.1f} against {top} {cost[top]:.1f}, gap {gap:.1f}")
    if unresolved_all:
        return "unresolved", f"missing T12M window for live, unchanged funds: {', '.join(unresolved_all)}" + _note(excluded_all)
    if void:
        return "void", "; ".join(void + parts) + _note(excluded_all)
    return ("pass" if all(g >= H2_GAP for g in gaps) else "fail"), "; ".join(parts) + f" (pass at or above {H2_GAP} in both groups)" + _note(excluded_all)


def h3(rev, el):
    live = [t for t in UNIVERSE if not el.at[t, "closed"]]
    excluded, unresolved = _excluded(el, live, with_lev=False)
    closed_note = _note([f'{t} {el.at[t, "closed_note"]}' for t in UNIVERSE if el.at[t, "closed"]])
    if unresolved:
        return "unresolved", f"missing ledger row or T12M window for live funds: {', '.join(unresolved)}" + closed_note
    use = [t for t in live if el.at[t, "ranked"]]
    T = rev["T"].set_index("ticker").loc[use]
    up = T[T["stock_pct"] > 0]
    n = len(up)
    if n < H3_MIN:
        return "inconclusive", f"{n} ranked funds on a stock that rose, below the minimum of {H3_MIN}" + closed_note
    beat = up[up["fund_pct"] > 2 * up["stock_pct"]]
    share = len(beat) / n
    names = ", ".join(sorted(beat.index)) or "none"
    return ("pass" if share <= H3_SHARE else "fail"), f"{len(beat)} of {n} funds returned more than twice their stock ({share:.2f}; pass at or below {H3_SHARE}): {names}" + closed_note


def h4(rev, el):
    cost = rev["T"].set_index("ticker")["cost_pct"] if len(rev["T"]) else pd.Series(dtype=float)
    excluded, unresolved = _excluded(el, EXPENSIVE, with_lev=True)
    if unresolved:
        return "unresolved", f"missing T12M window for live, unchanged funds: {', '.join(unresolved)}" + _note(excluded)
    present = [t for t in EXPENSIVE if not el.at[t, "closed"] and not el.at[t, "lev_change"] and el.at[t, "has_window"]]
    if not present:
        return "void", "no eligible fund left" + _note(excluded)
    parts = [f"{t} {cost[t]:.1f}" for t in present]
    ok = all(cost[t] > H4_COST for t in present)
    return ("pass" if ok else "fail"), ", ".join(parts) + f" percent a year (pass above {H4_COST} for each)" + _note(excluded)


def evaluate(asof=REVIEW_ASOF, root=ROOT):
    rev = load_review(asof, root)
    el = eligibility(rev)
    tag = f"review run as of {asof}: "
    out = []
    for hid, fn in (("H1", h1), ("H2", h2), ("H3", h3), ("H4", h4)):
        result, evidence = fn(rev, el)
        out.append({"id": hid, "result": result, "evidence": tag + evidence})
    return out


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
        if any(v["result"] == "unresolved" for v in out):
            sys.exit("refusing to record: at least one hypothesis is unresolved (an input is missing)")
        for v in out:
            ledger.append({"kind": "verdict", **v})
        (ROOT / "HYPOTHESES.md").write_text(ledger.render(), encoding="utf-8", newline="\n")
        print(ledger.verify())
    return 0


if __name__ == "__main__":
    sys.exit(main())
