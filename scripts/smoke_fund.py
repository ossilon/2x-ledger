#!/usr/bin/env python3
"""One fund, the ten questions, from the captured data. A development check, not the public report.

    py -I scripts\\smoke_fund.py NASDAQ:TSLL [--cutoff 2026-10-31T23:59:59Z]

Prints the total-return cross-check against Yahoo, the decomposition since inception and by calendar year, realized
leverage, drag, cost, risk and holding statistics. Every number comes from the engine; nothing is typed in.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
import _paths  # noqa: E402,F401
import tv_capture as tc  # noqa: E402
import register as rg  # noqa: E402
import total_return as trm  # noqa: E402
import align as al  # noqa: E402
import rates  # noqa: E402
import decompose as dc  # noqa: E402
import leverage as lv  # noqa: E402
import drag  # noqa: E402
import periods as pr  # noqa: E402
import stats as st  # noqa: E402
from captured_by import captured_by  # noqa: E402


def run(symbol):
    funds = rg.load_funds()
    f = funds.loc[symbol]
    stock_sym = f["underlying"]
    print(f"\n{symbol}  {f['fund_name']}  ({f['issuer']}; underlying {stock_sym}; inception {f['inception_date'].date()})")
    print(tc.banner(symbol))
    print(tc.banner(stock_sym))

    fund = trm.fund_tr(symbol)
    stock = trm.stock_tr(stock_sym)
    for note in fund.attrs["overrides"]:
        print("  distribution override:", note)
    print("  TR cross-check vs Yahoo adjclose:", trm.crosscheck(symbol, fund=True))
    print("  TR cross-check vs Yahoo adjclose:", trm.crosscheck(stock_sym))

    fund_a, stock_a, info = al.align(fund, stock.loc[fund.index[0]:])      # stock sessions before inception are not gaps
    if info["fund_only"] or info["stock_only"]:
        print("  sessions in one series only:", info)
    idx = fund_a.index
    L = rg.target_leverage_series(symbol, idx)
    rate = rates.fed_funds_daily(idx)
    a = rates.accrual(idx)
    lay = dc.layers(stock_a["tr"], L, rate, a, fund_tr=fund_a["tr"])
    flags = al.relative_guard(lay["r_fund"].iloc[1:], lay["r_stock"].iloc[1:], L.iloc[1:], tol=0.25)
    if flags:
        print("  RELATIVE GUARD flags:", flags[:10])

    print("\n  Decomposition since inception (percent of start value):")
    s = dc.window_summary(lay)
    for k in ("stock_pct", "naive_pct", "l1_pct", "l2_pct", "b_pct", "fund_pct", "compounding_pp", "financing_pp", "rebalance_pp", "residual_pp", "levered_bh_pp"):
        print(f"    {k:16s} {s[k]:10.2f}")
    res = dc.residual_annual(lay)
    print(f"    residual annual  {res['annual_pct']:10.2f}  [{res['ci_lo_pct']:.2f}, {res['ci_hi_pct']:.2f}]  n={res['n_days']}  wiped={res['wiped']}")
    print(f"    financing annual {dc.financing_annual_pct(lay):10.2f}  (fed funds on the borrowed turns)")
    print(f"    expense ratio    {float(f['expense_ratio_pct']):10.2f}  cost multiple {(-res['annual_pct']) / float(f['expense_ratio_pct']):.1f}x")

    print("\n  By calendar year (fund / stock / naive L x stock / residual pp):")
    for y, (d0, d1) in pr.calendar_years(idx).items():
        if d0 == d1:
            continue
        ws = dc.window_summary(lay, d0, d1)
        print(f"    {y}: fund {ws['fund_pct']:8.1f}  stock {ws['stock_pct']:8.1f}  naive {ws['naive_pct']:8.1f}  rebalance {ws['rebalance_pp']:7.1f}  residual {ws['residual_pp']:7.1f}  (L at start {ws['L_start']})")

    rf, rs = lay["r_fund"].iloc[1:], lay["r_stock"].iloc[1:]
    fee_a = rates.fee_accrual(idx, float(f["expense_ratio_pct"])).iloc[1:]
    print("\n  Realized leverage (whole history, then trailing 252 sessions; the whole history mixes leverage regimes):")
    for label, sl in (("all", slice(None)), ("252", slice(-252, None))):
        rf_, rs_ = rf.iloc[sl], rs.iloc[sl]
        b = lv.ols_beta(rf_, rs_)
        cu, cd = lv.capture_ratios(rf_, rs_)
        w = lv.kday(rf_, rs_, k=5, rate_accrual=lay["rate_accrual"].iloc[1:].iloc[sl], fee_accrual=fee_a.iloc[sl])
        beta5, rmse, n5 = lv.cubic_beta(w)
        print(f"    [{label:>3s}] 1-day OLS slope {b['beta']:.3f}  R2 {b['r2']:.4f}  n {b['n']}  |  5-day Leung-Santoli {beta5:.3f} (rmse {rmse:.4f}, {n5} windows)"
              f"  |  capture up {cu:.3f} down {cd:.3f}  |  tracking error {lv.tracking_error_annual(rf_, rs_, L.iloc[1:].iloc[sl]):.2f}%/yr")

    print("\n  Volatility and drag (stock):")
    tot, ann = drag.exact_penalty(rs, 2.0)
    tl, annl = drag.sigma2_law(rs, 2.0)
    print(f"    realized vol {drag.realized_vol(rs):.1f}%  Garman-Klass {drag.garman_klass_vol(*(tc.load_series(stock_sym).loc[idx][c] for c in ('open','high','low','close'))):.1f}%")
    print(f"    exact 2x penalty {ann:.1f}%/yr  sigma^2 law {annl:.1f}%/yr  |  VR(10) {drag.variance_ratio(rs, 10):.3f}  AR(1) {drag.ar1(rs):.3f}")
    sigma2 = (drag.realized_vol(rs) / 100) ** 2
    r_ann = float(rate.mean())
    h = st.hurdle_return(sigma2, r_ann, max(-res["annual_pct"], 0) / 100 - r_ann if not np.isnan(res["annual_pct"]) else 0.0)
    k_l, k_lo, k_hi = st.kelly_leverage(rs, rate.iloc[1:] * a.iloc[1:])
    print(f"    hurdle stock log growth {h['hurdle_log_pct']:.1f}%/yr (simple {h['hurdle_simple_pct']:.1f}%)  |  Kelly L* {k_l:.2f} [{k_lo:.2f}, {k_hi:.2f}]")

    print("\n  Risk and holding:")
    print(f"    fund max DD {st.max_drawdown(lay['L3']):.1f}%  current DD {st.current_drawdown(lay['L3']):.1f}%  underwater {st.underwater_days(lay['L3'])} days  worst day {st.worst_day(lay['L3']):.1f}%")
    print(f"    stock worst day {st.worst_day(stock_a['tr']):.1f}%  tail index {st.hill_tail_index(rs):.2f}  excess kurtosis {st.excess_kurtosis(rs):.1f}  Bowley skew {st.bowley_skew(rs):.3f}")
    rs1 = pr.rolling_stats(lay["L3"], 252)
    print(f"    rolling 1y fund return min/med/max {rs1['min_pct']:.1f} / {rs1['med_pct']:.1f} / {rs1['max_pct']:.1f}%  ({rs1['windows']} windows)")
    print(f"    P(fund beats stock, 1y) {pr.p_beat(lay['L3'], lay['L0'], 252):.2f}   P(fund beats 2x stock, 1y) {pr.p_beat(lay['L3'], lay['L0'], 252, 2.0):.2f}")
    best, worst, e_in, e_out = pr.oracle_bounds(lay["L3"])
    print(f"    oracle best {best:.0f}% ({e_in.date() if e_in is not None else '-'} -> {e_out.date() if e_out is not None else '-'})  worst {worst:.1f}%")
    print(f"    fund CAGR {100 * st.cagr(lay['L3']):.1f}%  stock CAGR {100 * st.cagr(lay['L0']):.1f}%")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="+")
    ap.add_argument("--cutoff", default=None)
    args = ap.parse_args()
    if args.cutoff:
        with captured_by(args.cutoff):
            for s in args.symbols:
                run(s)
    else:
        for s in args.symbols:
            run(s)
