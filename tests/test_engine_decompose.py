"""Decomposition engine: planted paths with closed-form answers."""
import numpy as np
import pandas as pd

from _harness import check, raises
from _synthetic import bdays, gbm_prices, constant_rate
import decompose as dc
import port as letf   # synth, accrual_fraction ported from the LETF kit (code/port.py)
import port as data_io
import rates

# 1. round trip +10% then -9.0909%: the 2x daily reset ends at 0.98182, the stock at 1.0
idx = bdays(3)
stock = pd.Series([100.0, 110.0, 100.0], index=idx)
zero_a = pd.Series(0.0, index=idx)
lay = dc.layers(stock, 2.0, 0.0, zero_a)
check("round trip: stock back to 1.0", abs(lay["L0"].iloc[-1] - 1.0) < 1e-12)
check("round trip: frictionless 2x ends at 0.98182", abs(lay["L1"].iloc[-1] - 0.981818181818) < 1e-9, lay["L1"].iloc[-1])
s = dc.window_summary(lay)
check("round trip: compounding effect is -1.818 points", abs(s["compounding_pp"] - (-1.8181818)) < 1e-5, s["compounding_pp"])
check("round trip: buy-and-hold with no rate equals the stock, so rebalance_pp = L1 - 1 in points", abs(s["rebalance_pp"] - (-1.8181818)) < 1e-5, s["rebalance_pp"])

# 2. constant daily growth g: ideal 2x = (1+2g)^N, compounding effect positive and exact
g, N = 0.01, 40
idx = bdays(N + 1)
stock = pd.Series(100.0 * (1 + g) ** np.arange(N + 1), index=idx)
lay = dc.layers(stock, 2.0, 0.0, pd.Series(0.0, index=idx))
check("constant growth: L1 = (1+2g)^N", abs(lay["L1"].iloc[-1] - (1 + 2 * g) ** N) < 1e-10)
s = dc.window_summary(lay)
expected_ce = 100 * ((1 + 2 * g) ** N - 1 - 2 * ((1 + g) ** N - 1))
check("constant growth: compounding effect positive and exact", s["compounding_pp"] > 0 and abs(s["compounding_pp"] - expected_ce) < 1e-8, (s["compounding_pp"], expected_ce))

# 3. flat stock, 5% rate: L2 decays by one turn of accrued interest; the rate wrapper has no look-ahead
idx = bdays(253)
stock = pd.Series(100.0, index=idx)
a = data_io.accrual_fraction(idx)
lay = dc.layers(stock, 2.0, 0.05, a)
expected = np.prod(1 - 0.05 * a.values)
check("flat stock: L2 ends at prod(1 - 0.05 a) (one borrowed turn)", abs(lay["L2"].iloc[-1] - expected) < 1e-12, (lay["L2"].iloc[-1], expected))
check("flat stock: L1 and L0 stay at 1", abs(lay["L1"].iloc[-1] - 1) < 1e-12 and abs(lay["L0"].iloc[-1] - 1) < 1e-12)
s = dc.window_summary(lay)
b_expected = 2.0 - np.prod(1 + 0.05 * a.values)     # fixed loan: B = 1 - (C - 1) with C the compound cash index
check("flat stock: B keeps the loan fixed, 2 - prod(1 + r a)", abs(s["b_pct"] - 100 * (b_expected - 1)) < 1e-8, (s["b_pct"], b_expected))
check("flat stock: the reset fund de-levers as it pays interest, a small positive rebalance_pp", 0 < s["rebalance_pp"] < 0.5 and abs(s["rebalance_pp"] - 100 * (expected - b_expected)) < 1e-8, s["rebalance_pp"])
check("flat stock: financing_pp equals the whole L2 shortfall", abs(s["financing_pp"] - 100 * (expected - 1)) < 1e-8)
check("financing_annual_pct is about 5% a year", abs(dc.financing_annual_pct(lay) - 5.0) < 0.05, dc.financing_annual_pct(lay))
check("financing_annual_pct is the log rate ln(L1/L2) per calendar year", abs(dc.financing_annual_pct(lay) - 100 * np.log(lay["L1"].iloc[-1] / lay["L2"].iloc[-1]) / dc.years_in(idx)) < 1e-12)
# day count: the reference rate accrues on days / 360 (money-market convention), the fee on days / 365
check("rates.accrual charges one calendar day as 1/360", abs(rates.accrual(idx).iloc[1] - 1 / 360) < 1e-15 and abs(rates.accrual(idx)[idx[idx.dayofweek == 0][1]] - 3 / 360) < 1e-15)
check("rates.fee_accrual charges one calendar day as expense / 365", abs(rates.fee_accrual(idx, 1.0).iloc[1] - 0.01 / 365) < 1e-15)
# no look-ahead: a rate that jumps on day k is used from day k+1
rate_hist = pd.Series(0.02, index=pd.date_range("2019-12-01", "2021-12-31"))
k = idx[100]
rate_hist[rate_hist.index >= k] = 0.06
r_used = rates.fed_funds_daily(idx, rate_series=rate_hist)
check("rate wrapper: the day of the jump still uses the old rate", abs(r_used[k] - 0.02) < 1e-12, r_used[k])
check("rate wrapper: the next session uses the new rate", abs(r_used[idx[101]] - 0.06) < 1e-12)
check("rate wrapper: the first row is filled from the value before it", abs(r_used.iloc[0] - 0.02) < 1e-12)

# 4. planted cost: a letf.synth fund with spread 30% and fee 1% shows a residual of about -31%/yr with a CI around it
px = gbm_prices(1500, mu=0.10, sigma=0.40, seed=3)
a = data_io.accrual_fraction(px.index)
rate = constant_rate(px.index, 0.05)
fund = letf.synth(px, 2.0, rate=0.05, spread=0.30, fee=0.01)
lay = dc.layers(px, 2.0, rate, a, fund_tr=fund)
res = dc.residual_annual(lay, block=21, reps=400, seed=5)
check("planted cost: residual about -31% a year", abs(res["annual_pct"] - (-31.0)) < 0.6, res["annual_pct"])
check("planted cost: the interval covers the planted value", res["ci_lo_pct"] <= -31.0 <= res["ci_hi_pct"], (res["ci_lo_pct"], res["ci_hi_pct"]))
check("planted cost: the interval is narrow for a constant cost", res["ci_hi_pct"] - res["ci_lo_pct"] < 1.0, res)
s = dc.window_summary(lay)
check("planted cost: the fund trails L2 (residual_pp negative) and L2 trails L1 (financing)", s["residual_pp"] < 0 and s["financing_pp"] < 0)
check("letf.synth itself silently defaults spread and fee to 0.91% (the trap the engine must never fall into)",
      abs(letf.synth(px, 2.0, rate=0.0).attrs["model"]["spread"] - 0.0091) < 1e-12 and abs(letf.synth(px, 2.0, rate=0.0).attrs["model"]["fee"] - 0.0091) < 1e-12)

# 5. leverage timeline 1.5x then 2x: the segment-aware residual is ~0; a constant-2x engine shows a large one
px = gbm_prices(500, mu=0.08, sigma=0.35, seed=4)
a = data_io.accrual_fraction(px.index)
rate = constant_rate(px.index, 0.04)
change, before = px.index[250], px.index[249]
L = pd.Series(1.5, index=px.index)
L[px.index >= change] = 2.0                     # the new target applies to the change day's return
seg1 = letf.synth(px.loc[:before], 1.5, rate=0.04, spread=0.0, fee=0.0)
seg2 = letf.synth(px.loc[before:], 2.0, rate=0.04, spread=0.0, fee=0.0)   # first row = `before`, return 0
fund = pd.concat([seg1, seg1.iloc[-1] * seg2.iloc[1:]])
lay_ok = dc.layers(px, L, rate, a, fund_tr=fund)
lay_bad = dc.layers(px, 2.0, rate, a, fund_tr=fund)
r_ok, r_bad = dc.residual_annual(lay_ok, reps=100), dc.residual_annual(lay_bad, reps=100)
check("leverage timeline: segment-aware residual is zero", abs(r_ok["annual_pct"]) < 1e-6, r_ok["annual_pct"])
check("leverage timeline: a constant-2x engine reports a large spurious residual", abs(r_bad["annual_pct"]) > 2.0, r_bad["annual_pct"])
check("leverage timeline: L column follows the timeline", lay_ok["L"].loc[change - pd.Timedelta(days=1):].iloc[0] == 1.5 and lay_ok["L"][change] == 2.0)

# 8. wipe-out: a -50% stock day sends the 2x layers to 0 and the frame stays finite
idx = bdays(6)
stock = pd.Series([100, 102, 51, 55, 60, 62.0], index=idx)
lay = dc.layers(stock, 2.0, 0.03, data_io.accrual_fraction(idx))
check("wipe-out: L1 is 0 from the -50% day on", lay["L1"].iloc[2] == 0.0 and lay["L1"].iloc[-1] == 0.0)
check("wipe-out: the frame records the day", lay.attrs["wiped"]["L1"] == idx[2], lay.attrs["wiped"])
check("wipe-out: every value is finite", np.isfinite(lay[["L0", "L1", "L2", "B"]].values).all())
s = dc.window_summary(lay)
check("wipe-out: summary gives -100% for the frictionless fund and stays finite", abs(s["l1_pct"] + 100.0) < 1e-12 and all(np.isfinite(v) for k, v in s.items() if k not in ("start", "end")))
fund0 = lay["L1"].copy()
lay2 = dc.layers(stock, 2.0, 0.03, data_io.accrual_fraction(idx), fund_tr=fund0)
res = dc.residual_annual(lay2, reps=50)
check("wipe-out: residual_annual reports wiped instead of a number", res["wiped"] is True and np.isnan(res["annual_pct"]))

# B re-levers at a target change: chained closed form, and wipes out absorbingly
idx = bdays(6)
stock = pd.Series([100, 110, 121, 133.1, 146.41, 161.051], index=idx)      # +10% a day
Lser = pd.Series([1.5, 1.5, 1.5, 2.0, 2.0, 2.0], index=idx)                 # target changes on day 3
lay = dc.layers(stock, Lser, 0.0, pd.Series(0.0, index=idx))
b_day2 = 1 + 1.5 * (121 / 100 - 1)                                           # 1.5x from day 0 to day 2
b_day5 = b_day2 * (1 + 2.0 * (161.051 / 121 - 1))                            # re-levered to 2x at day 2's close
check("B re-levers at the change: chained closed form", abs(lay["B"].iloc[2] - b_day2) < 1e-12 and abs(lay["B"].iloc[-1] - b_day5) < 1e-9, (lay["B"].iloc[-1], b_day5))
check("B with a constant target is the plain formula", abs(dc.layers(stock, 2.0, 0.0, pd.Series(0.0, index=idx))["B"].iloc[-1] - (1 + 2 * (161.051 / 100 - 1))) < 1e-9)
idx = bdays(5)
stock = pd.Series([100, 60, 40, 80, 120.0], index=idx)                       # -60% over two days, then a full recovery
lay = dc.layers(stock, 2.0, 0.0, pd.Series(0.0, index=idx))
check("B is wiped out when the 2x buy-and-hold position reaches zero (-50% in the stock)", lay["B"].iloc[2] == 0.0 and lay.attrs["wiped"]["B"] == idx[2])
check("B stays at zero after the wipe-out even though the stock recovers", lay["B"].iloc[-1] == 0.0)
s = dc.window_summary(lay)
check("window summary reports the wiped benchmark", s["b_wiped"] is True and abs(s["b_pct"] + 100.0) < 1e-12)

# payouts: a fund that pays out d and levers the rest matches L2 exactly when the model does the same
px = gbm_prices(120, mu=0.1, sigma=0.5, seed=12)
a = data_io.accrual_fraction(px.index)
rate = constant_rate(px.index, 0.04)
k = px.index[60]
d = pd.Series(0.0, index=px.index)
d[k] = 0.25                                                                 # 25% of the prior close paid out
r_s = px.pct_change().fillna(0.0)
g = (1 - d) * (1 + 2.0 * r_s - 1.0 * 0.04 * a) + d                          # the fund's gross TR return each day
fund = g.cumprod()
lay_pay = dc.layers(px, 2.0, rate, a, fund_tr=fund, payout=d)
lay_nopay = dc.layers(px, 2.0, rate, a, fund_tr=fund)
check("with the payout modeled the residual is zero", abs(dc.residual_annual(lay_pay, reps=50)["annual_pct"]) < 1e-9, dc.residual_annual(lay_pay, reps=50)["annual_pct"])
check("without it the payout day lands in the residual as a false gain or loss", abs(dc.residual_annual(lay_nopay, reps=50)["annual_pct"]) > 0.5, dc.residual_annual(lay_nopay, reps=50)["annual_pct"])
raises("a payout of 100% or more is refused", lambda: dc.layers(px, 2.0, rate, a, payout=d.where(d == 0, 1.0)), "payout")

# sub-window summary re-bases every layer at the window start
px = gbm_prices(300, seed=9)
lay = dc.layers(px, 2.0, constant_rate(px.index, 0.05), data_io.accrual_fraction(px.index))
full = dc.window_summary(lay)
sub = dc.window_summary(lay, start=px.index[100], end=px.index[200])
direct = dc.layers(px.loc[px.index[100]:px.index[200]], 2.0, 0.05, data_io.accrual_fraction(px.loc[px.index[100]:px.index[200]].index))
ds = dc.window_summary(direct)
check("sub-window summary equals a direct computation on the sub-window (stock, L1, L2)", all(abs(sub[k] - ds[k]) < 1e-9 for k in ("stock_pct", "l1_pct", "l2_pct")), (sub, ds))
check("sub-window summary equals a direct computation (B, rebalance)", abs(sub["b_pct"] - ds["b_pct"]) < 1e-9 and abs(sub["rebalance_pp"] - ds["rebalance_pp"]) < 1e-9, (sub["b_pct"], ds["b_pct"]))
raises("a one-row window is refused", lambda: dc.window_summary(lay, start=px.index[5], end=px.index[5]), "two rows")
raises("a fund index with gaps is refused", lambda: dc.layers(px, 2.0, 0.05, data_io.accrual_fraction(px.index), fund_tr=px.iloc[10:] * 1.0), "align")
