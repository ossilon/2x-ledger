"""Realized leverage: OLS, stale-price attenuation, capture ratios, the Leung-Santoli cubic estimator."""
import numpy as np
import pandas as pd

from _harness import check
from _synthetic import gbm_prices, constant_rate
import leverage as lv
import port as letf
import port as data_io

# exact 2x: slope 2, R2 1, zero tracking error, capture 2 both ways
px = gbm_prices(800, mu=0.1, sigma=0.4, seed=21)
r_s = px.pct_change().dropna()
r_f = 2.0 * r_s
b = lv.ols_beta(r_f, r_s)
check("exact 2x: slope 2 and R2 1", abs(b["beta"] - 2.0) < 1e-12 and abs(b["r2"] - 1.0) < 1e-12, b)
check("exact 2x: tracking error 0", lv.tracking_error_annual(r_f, r_s, 2.0) < 1e-9)
cu, cd = lv.capture_ratios(r_f, r_s)
check("exact 2x: capture 2.0 on up and down days", abs(cu - 2.0) < 1e-12 and abs(cd - 2.0) < 1e-12, (cu, cd))

# planted asymmetry: 1.9x on up days, 2.1x on down days
r_f2 = np.where(r_s > 0, 1.9, 2.1) * r_s
cu, cd = lv.capture_ratios(pd.Series(r_f2, index=r_s.index), r_s)
check("capture ratios recover a planted up/down asymmetry", abs(cu - 1.9) < 1e-9 and abs(cd - 2.1) < 1e-9, (cu, cd))

# 10. stale-price attenuation: fund return = 2 (0.9 r_t + 0.1 r_{t-1}) + noise -> 1-day slope ~1.8, 5-day windows ~2
rng = np.random.default_rng(5)
theta = 0.1
lagged = 0.9 * r_s + 0.1 * r_s.shift(1).fillna(0.0)
noise = pd.Series(rng.normal(0, 0.002, len(r_s)), index=r_s.index)
r_f3 = 2.0 * lagged + noise
b1 = lv.ols_beta(r_f3, r_s)
check("stale prices: 1-day slope sits near 2 (1 - theta) = 1.8", abs(b1["beta"] - 1.8) < 0.06, b1["beta"])
check("stale prices: R2 is below 1 but high", 0.9 < b1["r2"] < 1.0, b1["r2"])
w = lv.kday(r_f3, r_s, k=5)
beta5, rmse, n = lv.cubic_beta(w)
check("stale prices: the 5-day estimate is closer to 2 than the 1-day slope", abs(beta5 - 2.0) < abs(b1["beta"] - 2.0) and abs(beta5 - 2.0) < 0.08, (beta5, n))

# cubic estimator recovers 2.0 on a letf.synth fund with rate and fee (k = 5)
px = gbm_prices(1300, mu=0.08, sigma=0.5, seed=8)
a = data_io.accrual_fraction(px.index)
rate = constant_rate(px.index, 0.05)
fund = letf.synth(px, 2.0, rate=0.05, spread=0.0, fee=0.01)
r_s = px.pct_change().iloc[1:]
r_f = fund.pct_change().iloc[1:]
w = lv.kday(r_f, r_s, k=5, rate_accrual=(rate * a).iloc[1:], fee_accrual=(0.01 * a).iloc[1:])
beta5, rmse, n = lv.cubic_beta(w)
check("cubic estimator recovers 2.0 on a synthetic 2x fund with rate and fee", abs(beta5 - 2.0) < 0.03, (beta5, rmse, n))
check("cubic estimator fit error is tiny", rmse < 2e-3, rmse)
fund15 = letf.synth(px, 1.5, rate=0.05, spread=0.0, fee=0.01)
w15 = lv.kday(fund15.pct_change().iloc[1:], r_s, k=5, rate_accrual=(rate * a).iloc[1:], fee_accrual=(0.01 * a).iloc[1:])
beta15, _, _ = lv.cubic_beta(w15)
check("cubic estimator recovers 1.5 on a 1.5x fund", abs(beta15 - 1.5) < 0.03, beta15)
check("kday windows are non-overlapping k-day blocks", len(w) == len(r_s) // 5 and (w["v"] >= 0).all())

# exact_beta vs the book's approximation on a jumpy stock: an exactly-2x fund with rate and fee
rj = r_s.copy()
rj.iloc[::97] = -0.33                                   # jump days of -33%
rj.iloc[50::131] = 0.40                                 # and +40%
ra = (rate * a).iloc[1:]
fa = (0.01 * a).iloc[1:]
r_f_exact = 2.0 * rj - 1.0 * ra - fa                    # exactly 2x each day, paying the rate on one turn and the fee
b_exact, rmse_e, nw = lv.exact_beta(r_f_exact, rj, k=5, rate_accrual=ra, fee_accrual=fa)
b_cubic, _, _ = lv.cubic_beta(lv.kday(r_f_exact, rj, k=5, rate_accrual=ra, fee_accrual=fa))
check("exact_beta recovers 2.0000 on an exactly-2x fund with jumps", abs(b_exact - 2.0) < 1e-6 and rmse_e < 1e-9, (b_exact, rmse_e))
check("the book's small-move estimator is biased upward by the jumps (so the ledger uses exact_beta)", b_cubic - 2.0 > 0.03, b_cubic)
check("exact_beta recovers 1.5 as well", abs(lv.exact_beta(1.5 * rj - 0.5 * ra - fa, rj, k=5, rate_accrual=ra, fee_accrual=fa)[0] - 1.5) < 1e-6)
# payouts belong in the model: a fund that pays 20% out on one day and levers the rest is still exactly 2x
dpay = pd.Series(0.0, index=rj.index)
dpay.iloc[50] = 0.20                                    # a 20% payout on a +40% jump day (position 50)
r_f_pay = (1 - dpay) * (1 + 2.0 * rj - ra - fa) + dpay - 1
b_with, rmse_with, _ = lv.exact_beta(r_f_pay, rj, k=5, rate_accrual=ra, fee_accrual=fa, payout=dpay)
b_wo, rmse_wo, _ = lv.exact_beta(r_f_pay, rj, k=5, rate_accrual=ra, fee_accrual=fa)
check("exact_beta with the payout term recovers 2.0 exactly through a 20% payout day", abs(b_with - 2.0) < 1e-6 and rmse_with < 1e-9, (b_with, rmse_with))
check("without the payout term the model no longer fits the fund (the payout day is misread)", rmse_wo > 1e-3 and rmse_wo > 1000 * max(rmse_with, 1e-12), (b_wo, rmse_wo))
r_wiped = r_f_exact.copy()
r_wiped.iloc[300] = -1.0
check("a -100% fund day gives NaN, not a boundary value", np.isnan(lv.exact_beta(r_wiped, rj, k=5, rate_accrual=ra, fee_accrual=fa)[0]))

# capture ratios include costs by construction: a constant cost shows as under-capture on up days and over-capture on down days
r_cost = 2.0 * r_s - 0.30 / 252                         # exactly 2x minus a constant daily cost
cu_c, cd_c = lv.capture_ratios(r_cost, r_s)
check("a constant cost lowers up-day capture below 2 and raises down-day capture above 2", cu_c < 2.0 < cd_c, (cu_c, cd_c))
# and a leverage-return co-movement is the same observable as a cost: lambda = 2 + 5 r has mean gap 5 Var(r) = Cov(lambda, r)
lam = 2.0 + 5.0 * r_s
gap = (lam * r_s) - 2.0 * r_s
check("Cov(lambda, r) equals the mean daily gap (why no separate timing column exists)", abs(float(gap.mean()) - float(np.cov(lam, r_s, ddof=0)[0, 1]) - 5.0 * float(r_s.mean()) ** 2) < 1e-12)
check("ols on too few points is NaN, not an exception", np.isnan(lv.ols_beta([0.01, 0.02], [0.005, 0.01])["beta"]))
