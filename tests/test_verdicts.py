"""Verdict rules for H1-H4 on planted review tables: pass, fail, inconclusive and void each come out as written."""
import numpy as np
import pandas as pd

from _harness import check
import verdicts as vd


def tables(tickers, cost, vol, stock_pct=None, fund_pct=None, ranked=None):
    """A ledger frame and a T12M window frame whose window cost equals `cost` (fedfunds_pct 0, 365 days)."""
    n = len(tickers)
    L = pd.DataFrame({"ticker": tickers, "ranked": [True] * n if ranked is None else ranked,
                      "vol_under_annual_pct": vol})
    fund = np.array(fund_pct, float) if fund_pct is not None else (np.exp(-np.asarray(cost, float) / 100) - 1) * 100
    T = pd.DataFrame({"ticker": tickers, "fund_pct": fund, "fedfunds_pct": 0.0,
                      "stock_pct": stock_pct if stock_pct is not None else 10.0, "days": 365})
    T["cost_pct"] = vd.window_cost_pct(T["fund_pct"], T["fedfunds_pct"], T["days"])
    return L, T


check("window cost: a fund at -10% against fed funds at +5% over 365 days costs 100 ln(1.05/0.90) a year",
      abs(vd.window_cost_pct(-10, 5, 365) - 100 * np.log(1.05 / 0.90)) < 1e-9)
check("window cost scales with calendar time", abs(vd.window_cost_pct(-10, 5, 730) - 50 * np.log(1.05 / 0.90)) < 1e-9)

# H1: cost rises with volatility
tk = [f"F{i:02d}" for i in range(16)]
vol = np.linspace(20, 100, 16)
L, T = tables(tk, cost=vol / 4, vol=vol)
check("H1 passes when cost ranks with volatility", vd.h1(L, T)[0] == "pass", vd.h1(L, T))
L, T = tables(tk, cost=vol[::-1] / 4, vol=vol)
check("H1 fails when cost ranks against volatility", vd.h1(L, T)[0] == "fail", vd.h1(L, T))
L, T = tables(tk[:10], cost=vol[:10] / 4, vol=vol[:10])
check("H1 is inconclusive below 15 funds", vd.h1(L, T)[0] == "inconclusive", vd.h1(L, T))
L, T = tables(tk, cost=vol / 4, vol=vol, ranked=[True] * 10 + [False] * 6)
check("H1 counts ranked funds only", vd.h1(L, T)[0] == "inconclusive")

# H2: the T-Rex gap in both groups
def group_tables(costs):
    tk = list(costs)
    return tables(tk, cost=[costs[t] for t in tk], vol=50.0)

_, T = group_tables({"NVDX": 12.0, "NVDL": 7.0, "NVDU": 7.5, "NVDG": 8.0, "TSLT": 11.0, "TSLL": 9.0, "TSLG": 8.5})
check("H2 passes with gaps of 4.0 and 2.0", vd.h2(T)[0] == "pass", vd.h2(T))
_, T = group_tables({"NVDX": 12.0, "NVDL": 7.0, "NVDU": 7.5, "NVDG": 8.0, "TSLT": 10.0, "TSLL": 9.0, "TSLG": 8.5})
check("H2 fails when one group's gap is 1.0", vd.h2(T)[0] == "fail", vd.h2(T))
_, T = group_tables({"NVDL": 7.0, "NVDU": 7.5, "NVDG": 8.0, "TSLT": 11.0, "TSLL": 9.0, "TSLG": 8.5})
r = vd.h2(T)
check("H2 is void when a T-Rex fund has closed, and says which", r[0] == "void" and "NVDX" in r[1], r)

# H3: share of funds above twice their stock, among rising stocks
tk = [f"F{i:02d}" for i in range(12)]
stock = [10.0] * 9 + [-5.0] * 3
fund = [25.0, 30.0] + [15.0] * 7 + [-20.0] * 3
L, T = tables(tk, cost=5.0, vol=50.0, stock_pct=stock, fund_pct=fund)
r = vd.h3(L, T)
check("H3 passes when 2 of 9 rising-stock funds beat twice the stock (falling stocks ignored)", r[0] == "pass" and "2 of 9" in r[1], r)
fund = [25.0] * 6 + [15.0] * 3 + [-20.0] * 3
L, T = tables(tk, cost=5.0, vol=50.0, stock_pct=stock, fund_pct=fund)
check("H3 fails when 6 of 9 beat twice the stock", vd.h3(L, T)[0] == "fail")
L, T = tables(tk[:7], cost=5.0, vol=50.0, stock_pct=[10.0] * 7, fund_pct=[15.0] * 7)
check("H3 is inconclusive below 8 rising-stock funds", vd.h3(L, T)[0] == "inconclusive")

# H4: the three expensive funds stay above 20
_, T = tables(["MSTU", "MSTX", "SMCX", "AAPU"], cost=[25.0, 26.0, 27.0, 5.0], vol=50.0)
check("H4 passes with all three above 20", vd.h4(T)[0] == "pass")
_, T = tables(["MSTU", "MSTX", "SMCX"], cost=[25.0, 15.0, 27.0], vol=50.0)
check("H4 fails when one is at 15", vd.h4(T)[0] == "fail")
_, T = tables(["MSTU", "SMCX"], cost=[25.0, 27.0], vol=50.0)
r = vd.h4(T)
check("H4 drops a closed fund and names it", r[0] == "pass" and "MSTX" in r[1], r)
_, T = tables(["AAPU"], cost=[5.0], vol=50.0)
check("H4 is void when all three have closed", vd.h4(T)[0] == "void")

# the exploratory run on the real pilot files, when present (private data; tests nothing about the hypotheses)
if (vd.ROOT / "ledger.csv").exists() and (vd.ROOT / "results" / "2026-09" / "windows.csv").exists():
    out = vd.evaluate("2026-09-30")
    check("the exploratory run evaluates all four hypotheses without error", [v["id"] for v in out] == ["H1", "H2", "H3", "H4"], out)
