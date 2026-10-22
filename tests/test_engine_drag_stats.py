"""Volatility, drag, variance ratio, autocorrelation, hurdle, Kelly, tail index, drawdowns."""
import numpy as np
import pandas as pd

from _harness import check
from _synthetic import bdays, gbm_prices
import drag
import stats as st

# exact penalty: constant growth g gives N (log(1+2g) - 2 log(1+g))
g, N = 0.01, 100
r = pd.Series([g] * N)
total, annual = drag.exact_penalty(r, 2.0)
check("exact penalty on constant growth matches the closed form", abs(total - N * (np.log(1 + 2 * g) - 2 * np.log(1 + g))) < 1e-12, total)
check("exact penalty is negative and annualized", total < 0 and abs(annual - 100 * total / (N / 252)) < 1e-9)
# sigma^2 law approximates the exact penalty for small daily moves
px = gbm_prices(3000, mu=0.0, sigma=0.20, seed=2)
rs = px.pct_change().dropna()
tot_exact, _ = drag.exact_penalty(rs, 2.0)
tot_law, _ = drag.sigma2_law(rs, 2.0)
check("sigma^2 law is within 5% of the exact penalty at 20% vol", abs(tot_law / tot_exact - 1) < 0.05, (tot_exact, tot_law))
px_hi = gbm_prices(3000, mu=0.0, sigma=1.0, seed=2)
rh = px_hi.pct_change().dropna()
te, _ = drag.exact_penalty(rh, 2.0)
tl, _ = drag.sigma2_law(rh, 2.0)
check("sigma^2 law still within 5% of the exact penalty at 100% vol without jumps", abs(tl / te - 1) < 0.05, (te, tl))
rj = rs.copy()
rj.iloc[::300] = -0.35                      # ten jump days of -35%: the law understates the exact penalty
tej, _ = drag.exact_penalty(rj, 2.0)
tlj, _ = drag.sigma2_law(rj, 2.0)
check("sigma^2 law understates the exact penalty by more than 10% once jumps are present", tej < tlj and abs(tlj / tej - 1) > 0.10, (tej, tlj))
check("exact penalty is NaN after a wipe-out day", np.isnan(drag.exact_penalty(pd.Series([0.01, -0.6, 0.02]), 2.0)[0]))

# realized vol and Garman-Klass on planted bars
check("realized vol of a 20% GBM is near 20%", abs(drag.realized_vol(rs) - 20.0) < 1.5, drag.realized_vol(rs))
rng = np.random.default_rng(12)
sigma, days, steps = 0.30, 3000, 390
o, h, l, c = [], [], [], []
level = 100.0
for _ in range(days):
    path = level * np.exp(np.cumsum(sigma * np.sqrt(1 / 252 / steps) * rng.standard_normal(steps)))
    o.append(level); h.append(max(level, path.max())); l.append(min(level, path.min())); c.append(path[-1])
    level = path[-1]
gk = drag.garman_klass_vol(o, h, l, c)
cc = drag.realized_vol(pd.Series(c).pct_change().dropna())
# discrete intraday sampling clips the true high-low range, so Garman-Klass reads a few percent low: compare with
# the close-to-close estimate on the same bars and with the planted 30%
check("Garman-Klass vol on planted 1-minute bars is within 3.5 points of 30% and of close-to-close", abs(gk - 30.0) < 3.5 and abs(gk - cc) < 3.5, (gk, cc))

# variance ratio and AR(1): iid ~1 / 0, trending > 1 / > 0, reverting < 1 / < 0
n = 6000
z = rng.standard_normal(n) * 0.02
check("VR(5) of iid returns is near 1", abs(drag.variance_ratio(z, 5) - 1.0) < 0.1, drag.variance_ratio(z, 5))
check("AR(1) of iid returns is near 0", abs(drag.ar1(z)) < 0.05, drag.ar1(z))
phi = 0.3
ar = np.zeros(n)
for t in range(1, n):
    ar[t] = phi * ar[t - 1] + z[t]
check("VR(5) of trending returns is above 1.2", drag.variance_ratio(ar, 5) > 1.2, drag.variance_ratio(ar, 5))
check("AR(1) recovers the planted 0.3 within 0.05", abs(drag.ar1(ar) - 0.3) < 0.05, drag.ar1(ar))
mr = np.zeros(n)
for t in range(1, n):
    mr[t] = -phi * mr[t - 1] + z[t]
check("VR(5) of reverting returns is below 0.8", drag.variance_ratio(mr, 5) < 0.8, drag.variance_ratio(mr, 5))
check("VR needs more than 2q observations", np.isnan(drag.variance_ratio(z[:8], 5)))
# small-sample closed form, written out by hand for q = 2 on five log returns
x = np.array([0.01, -0.02, 0.03, 0.00, -0.01])
mu = x.mean()
sa = ((x - mu) ** 2).sum() / 4
pairs = np.array([x[0] + x[1], x[1] + x[2], x[2] + x[3], x[3] + x[4]])
m = 2 * (5 - 2 + 1) * (1 - 2 / 5)
sc = ((pairs - 2 * mu) ** 2).sum() / m
check("VR(2) on five returns matches the hand-computed Lo-MacKinlay value", abs(drag.variance_ratio(np.expm1(x), 2) - sc / sa) < 1e-12, (drag.variance_ratio(np.expm1(x), 2), sc / sa))

# 14. hurdle and Kelly
h = st.hurdle_return(0.09, 0.04, 0.12)
check("hurdle: sigma^2 + r + c in log terms", abs(h["hurdle_log_pct"] - 25.0) < 1e-9 and abs(h["hurdle_simple_pct"] - 100 * (np.exp(0.25) - 1)) < 1e-9, h)
# deterministic planted Kelly: alternating returns m +/- s. The exact discrete optimum solves
# (m+s)/(1+L(m+s)) + (m-s)/(1+L(m-s)) = 0, so L* = m / (s^2 - m^2); the textbook ratio m / s^2 is its approximation.
m_, s_ = 0.001, 0.02
alt = np.array([m_ + s_, m_ - s_] * 2000)
L_hat, lo, hi = st.kelly_leverage(alt, 0.0, block=20, reps=200, seed=2)
check("Kelly leverage on alternating returns is the exact closed form m / (s^2 - m^2)", abs(L_hat - m_ / (s_ ** 2 - m_ ** 2)) < 1e-6, (L_hat, m_ / (s_ ** 2 - m_ ** 2)))
check("the exact optimum differs from the ratio approximation by the second-order term", abs(L_hat - m_ / s_ ** 2) > 1e-4)
# feasibility: a -60% day caps the leverage below 1/0.6
cap = np.array([0.01] * 100 + [-0.6])
L_cap, _, _ = st.kelly_leverage(cap, 0.0)
check("Kelly stays inside the feasible interval set by the worst day", L_cap < 1 / 0.6 and np.isfinite(L_cap), L_cap)
# on a long GBM the point estimate is noisy (its standard error scales with sigma / sqrt(years) / sigma^2), so the
# interval, not the point, is tested: the planted (mu - r) / sigma^2 must lie inside it. A GBM's arithmetic drift is mu.
mu, sig = 0.12, 0.20
px = gbm_prices(60000, mu=mu, sigma=sig, seed=31)
rk = px.pct_change().dropna()
true_L = (mu - 0.03) / sig ** 2
L_hat, lo, hi = st.kelly_leverage(rk, 0.03 / 252, block=21, reps=300, seed=2)
check("Kelly interval on a long GBM covers the planted (mu - r)/sigma^2", lo <= true_L <= hi and abs(L_hat - true_L) < 1.0, (lo, L_hat, true_L, hi))

# Hill tail index on Student-t(3) losses, with its standard error alpha / sqrt(k)
t3 = rng.standard_t(3, size=40000) * 0.02
alpha = st.hill_tail_index(t3, frac=0.05)
check("Hill estimator on t(3) returns gives a tail index near 3", 2.3 < alpha < 3.8, alpha)
ht = st.hill_tail(t3, frac=0.05)
check("hill_tail reports k and se = alpha / sqrt(k)", ht["alpha"] == alpha and abs(ht["se"] - alpha / np.sqrt(ht["k"])) < 1e-12 and ht["k"] == max(10, int(0.05 * (t3 < 0).sum())), ht)
# variance-ratio z: a random walk gives |z| small, a trend gives z large; the robust variance shrinks the z of a
# volatility-clustered walk relative to the homoskedastic formula
z_rw = drag.variance_ratio_z(z, 10)
check("robust VR z of iid returns is within 3", abs(z_rw) < 3, z_rw)
check("robust VR z of trending returns is above 3", drag.variance_ratio_z(ar, 5) > 3, drag.variance_ratio_z(ar, 5))
check("VR z is NaN where VR is NaN", np.isnan(drag.variance_ratio_z(z[:8], 5)))
check("excess kurtosis of t(3) is large and of normal is near 0", st.excess_kurtosis(t3) > 3 and abs(st.excess_kurtosis(z)) < 0.3, (st.excess_kurtosis(t3), st.excess_kurtosis(z)))
check("Bowley skew of a symmetric sample is near 0", abs(st.bowley_skew(z)) < 0.05, st.bowley_skew(z))

# 12. drawdown path 100-50-100-80
idx = bdays(4, "2024-01-01")
p = pd.Series([100.0, 50.0, 100.0, 80.0], index=idx)
check("max drawdown of 100-50-100-80 is -50%", abs(st.max_drawdown(p) + 50.0) < 1e-12)
check("current drawdown is -20%", abs(st.current_drawdown(p) + 20.0) < 1e-12)
check("underwater days counts from the last peak", st.underwater_days(p) == (idx[3] - idx[2]).days and st.underwater_days(p.iloc[:3]) == 0)
check("worst and best day", abs(st.worst_day(p) + 50.0) < 1e-12 and abs(st.best_day(p) - 100.0) < 1e-12)
check("CAGR of an index ending at zero is -100%", st.cagr(pd.Series([1.0, 0.5, 0.0], index=bdays(3))) == -1.0)
check("CAGR of a doubling over 365.25 days is 100%", abs(st.cagr(pd.Series([1.0, 2.0], index=pd.DatetimeIndex(["2020-01-01", "2021-01-01"]))) - (2 ** (365.25 / 366) - 1)) < 1e-9)
