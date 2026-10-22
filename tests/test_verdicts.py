"""Verdict rules for H1-H4 with protocol P1 and P2 eligibility on planted review tables: closure, new listing,
change-and-revert of the leverage target, missing data, and the plain pass / fail / inconclusive / void cases."""
import numpy as np
import pandas as pd

from _harness import check
import verdicts as vd

ASOF = "2027-09-30"


def review(costs, vol=None, stock_pct=None, fund_pct=None, ranked=None, closed=(), lev_events=(), drop_window=(), drop_row=()):
    """A review dict for the universe: `costs` maps ticker -> T12M window cost (percent a year, fedfunds 0, 365 days).
    closed: {ticker: close_date}; lev_events: [(ticker, effective_from)]; drop_window / drop_row: tickers without data."""
    tickers = list(costs)
    n = len(tickers)
    L = pd.DataFrame({"ticker": tickers, "asof": ASOF, "run_date_utc": "2027-10-02",
                      "ranked": [True] * n if ranked is None else ranked,
                      "vol_under_annual_pct": [50.0] * n if vol is None else vol})
    L = L[~L["ticker"].isin(drop_row)]
    fund = np.array(fund_pct, float) if fund_pct is not None else (np.exp(-np.array([costs[t] for t in tickers]) / 100) - 1) * 100
    T = pd.DataFrame({"asof": ASOF, "ticker": tickers, "window": "T12M", "start": "2026-09-30", "end": ASOF,
                      "fund_pct": fund, "fedfunds_pct": 0.0, "stock_pct": 10.0 if stock_pct is None else stock_pct})
    T = T[~T["ticker"].isin(drop_window)]
    T["days"] = 365
    T["cost_pct"] = vd.window_cost_pct(T["fund_pct"], T["fedfunds_pct"], T["days"])
    R = pd.DataFrame({"ticker": tickers, "status": ["closed" if t in closed else "live" for t in tickers],
                      "close_date": [closed.get(t, "") if isinstance(closed, dict) else "" for t in tickers]})
    E = pd.DataFrame(lev_events, columns=["ticker", "effective_from"]) if lev_events else pd.DataFrame(columns=["ticker", "effective_from"])
    return {"asof": ASOF, "L": L, "T": T, "R": R, "E": E}


def run(rev):
    el = vd.eligibility(rev)
    return {h: fn(rev, el) for h, fn in (("H1", vd.h1), ("H2", vd.h2), ("H3", vd.h3), ("H4", vd.h4))}


check("window cost: a fund at -10% against fed funds at +5% over 365 days costs 100 ln(1.05/0.90) a year",
      abs(vd.window_cost_pct(-10, 5, 365) - 100 * np.log(1.05 / 0.90)) < 1e-9)

# a plain universe: costs rise with volatility, T-Rex gaps 4 and 2, the expensive three above 20
base = {t: 6.0 for t in vd.UNIVERSE}
base.update({"NVDX": 12.0, "NVDL": 7.0, "NVDU": 7.5, "NVDG": 8.0, "TSLT": 11.0, "TSLL": 9.0, "TSLG": 8.5, "MSTU": 25.0, "MSTX": 26.0, "SMCX": 27.0})
vol = [base[t] * 4 for t in vd.UNIVERSE]
r = run(review(base, vol=vol))
check("plain universe: H1 pass, H2 pass, H4 pass", r["H1"][0] == "pass" and r["H2"][0] == "pass" and r["H4"][0] == "pass", r)
check("evidence names no exclusion on the plain universe", all("excluded: none" in r[h][1] for h in r), r["H2"][1])

# a new listing outside the frozen universe is ignored
extra = dict(base); extra["NEWFUND"] = 1.0
r = run(review(extra, vol=vol + [4.0]))
check("a ticker outside the frozen universe does not enter H1", "over 21 funds" in r["H1"][1], r["H1"][1])

# a closure with its price history retained: the fund leaves every test and is named
r = run(review(base, vol=vol, closed={"MSTU": "2027-03-01"}))
check("a closed fund is excluded from H4 by name, and the test continues on the rest", r["H4"][0] == "pass" and "MSTU closed 2027-03-01" in r["H4"][1], r["H4"])
check("a closed fund is excluded from H1 by name", "MSTU closed 2027-03-01" in r["H1"][1] and "over 20 funds" in r["H1"][1], r["H1"][1])
# a closure dated after the as-of does not count yet
r = run(review(base, vol=vol, closed={"MSTU": "2027-10-15"}))
check("a closure after the as-of date is not an exclusion", "excluded: none" in r["H4"][1])

# a leverage change inside the window, even one reverted before the as-of, excludes the fund from H2 and H4
r = run(review(base, vol=vol, lev_events=[("NVDX", "2027-01-10"), ("NVDX", "2027-04-10")]))
check("the T-Rex NVDA fund with a change-and-revert leaves H2: the NVDA group is void", r["H2"][0] == "void" and "NVDX leverage change 2027-01-10, 2027-04-10" in r["H2"][1], r["H2"])
r = run(review(base, vol=vol, lev_events=[("MSTX", "2027-02-01")]))
check("a changed fund leaves H4 by name; the rest decide", r["H4"][0] == "pass" and "MSTX leverage change 2027-02-01" in r["H4"][1] and "MSTX 26.0" not in r["H4"][1], r["H4"])
check("a leverage change does not remove a fund from H1", "over 21 funds" in r["H1"][1])
# an event dated before the window start is not a change in the window
r = run(review(base, vol=vol, lev_events=[("NVDX", "2026-09-30")]))
check("an event on the window's start date is not inside the window", "excluded: none" in r["H2"][1])

# missing data for a live, unchanged fund is unresolved, never a closure
r = run(review(base, vol=vol, drop_window=["MSTU"]))
check("a missing window for a live fund makes H4 unresolved", r["H4"][0] == "unresolved" and "MSTU" in r["H4"][1], r["H4"])
check("and H1 unresolved too", r["H1"][0] == "unresolved")
r = run(review(base, vol=vol, drop_window=["MSTU"], closed={"MSTU": "2027-03-01"}))
check("a missing window for a closed fund is not unresolved", r["H4"][0] == "pass")

# plain rule outcomes
r = run(review(base, vol=vol[::-1]))
check("H1 fails when cost ranks against volatility", r["H1"][0] == "fail")
few = dict(base); rk = [t in list(base)[:10] for t in vd.UNIVERSE]
check("H1 is inconclusive below 15 ranked funds", run(review(few, vol=vol, ranked=rk))["H1"][0] == "inconclusive")
low = dict(base); low["TSLT"] = 10.0
check("H2 fails when one group's gap is 1.0", run(review(low, vol=vol))["H2"][0] == "fail")
r = run(review(base, vol=vol, closed={"NVDX": "2027-01-01"}))
check("H2 is void when a T-Rex fund has closed, and says which", r["H2"][0] == "void" and "NVDX closed 2027-01-01" in r["H2"][1], r["H2"])
stock = [10.0] * 9 + [-5.0] * 12
fund = [25.0, 30.0] + [15.0] * 7 + [-20.0] * 12
r = run(review(base, vol=vol, stock_pct=stock, fund_pct=fund))
check("H3 passes when 2 of 9 rising-stock funds beat twice the stock (falling stocks ignored)", r["H3"][0] == "pass" and "2 of 9" in r["H3"][1], r["H3"])
fund = [25.0] * 6 + [15.0] * 3 + [-20.0] * 12
check("H3 fails when 6 of 9 beat twice the stock", run(review(base, vol=vol, stock_pct=stock, fund_pct=fund))["H3"][0] == "fail")
check("H3 is inconclusive below 8 rising-stock funds", run(review(base, vol=vol, stock_pct=[10.0] * 5 + [-1.0] * 16))["H3"][0] == "inconclusive")
cheap = dict(base); cheap["MSTX"] = 15.0
check("H4 fails when one is at 15", run(review(cheap, vol=vol))["H4"][0] == "fail")
check("H4 is void when all three have closed", run(review(base, vol=vol, closed={"MSTU": "2027-01-01", "MSTX": "2027-01-01", "SMCX": "2027-01-01"}))["H4"][0] == "void")

# the exploratory run on the real pilot files, when present (private data; tests nothing about the hypotheses)
if (vd.ROOT / "ledger.csv").exists() and (vd.ROOT / "results" / "2026-09" / "windows.csv").exists():
    out = vd.evaluate("2026-09-30")
    check("the exploratory run evaluates all four hypotheses without error", [v["id"] for v in out] == ["H1", "H2", "H3", "H4"], out)
    check("the exploratory run excludes nobody", all("excluded: none" in v["evidence"] for v in out), out)
