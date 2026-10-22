"""Realized leverage: does the fund deliver its multiple each day, and over longer windows?

Numbers only. Inputs are aligned daily total-return Series (fund and stock) and, where needed, the daily rate
accrual and fee accrual.

- ols_beta: slope, intercept, R2 of fund daily returns on stock daily returns (1-day realized leverage).
- tracking_error_annual: std(r_fund - L r_stock) * sqrt(252).
- capture_ratios: sum(r_fund) / sum(r_stock) on days the stock rose, and on days it fell (Morningstar's
  "captured 1.91x on up days" is this number).
- kday: non-overlapping k-day windows: log returns of fund and stock, realized variance of the stock's daily
  returns inside the window, and the window's rate and fee accruals.
- cubic_beta: Leung and Santoli (2016) section 2.3. Fit one leverage ratio beta by least squares of the fund's
  k-day log return on f_i(beta) = beta (x_i - rdT_i) - beta (beta - 1) / 2 * v_i + (r - f) dT_i, where x_i is the
  stock's k-day log return and v_i the realized variance inside the window. The drag term is tied to beta, so the
  estimate is one consistent number and stays stable on short samples where a two-coefficient regression does
  not (their Tables 2.1 and 2.2). The first-order condition is a cubic in beta; we minimize the quartic directly.
  Kept as the book's method; the ledger uses exact_beta because single-stock jumps break the approximation.
- exact_beta: the same one-parameter idea with the exact discrete daily-reset model inside the window.

Not here, on purpose: Bianchi and Goldberg's timing covariance Cov(lambda_t, r_t) with lambda_t = r_fund / r_stock.
A constant daily cost c gives lambda_t = L - c / r_t and Cov(lambda, r) = -c, so from returns alone the term is
the fund's cost, not its timing; removing the mean daily gap first removes any genuine covariance as well, because
Cov(lambda, r) = E[(lambda - L) r] IS the mean gap. The two are one observable (audit 2026-10-22). The capture
ratios are kept as what a holder sees on up and down days, costs included: a fund with constant cost shows capture
below L on up days and above L on down days.
"""
import numpy as np
import pandas as pd

TRADING_DAYS = 252


def ols_beta(r_fund, r_stock):
    """Slope, intercept and R2 of r_fund on r_stock (both daily simple returns, aligned)."""
    x = np.asarray(r_stock, dtype=float)
    y = np.asarray(r_fund, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if len(x) < 3 or np.var(x) == 0:
        return {"beta": float("nan"), "alpha_daily": float("nan"), "r2": float("nan"), "n": int(len(x))}
    beta, alpha = np.polyfit(x, y, 1)
    resid = y - (alpha + beta * x)
    r2 = 1.0 - resid.var() / y.var() if y.var() > 0 else float("nan")
    return {"beta": float(beta), "alpha_daily": float(alpha), "r2": float(r2), "n": int(len(x))}


def tracking_error_annual(r_fund, r_stock, L):
    """Annualized standard deviation of the daily gap between the fund and L times the stock, in percent."""
    Ls = np.asarray(L, dtype=float) if not np.isscalar(L) else float(L)
    gap = np.asarray(r_fund, dtype=float) - Ls * np.asarray(r_stock, dtype=float)
    gap = gap[np.isfinite(gap)]
    return float(100 * gap.std(ddof=1) * np.sqrt(TRADING_DAYS)) if len(gap) > 2 else float("nan")


def capture_ratios(r_fund, r_stock):
    """(capture on up days, capture on down days): ratio of summed fund returns to summed stock returns."""
    x = np.asarray(r_stock, dtype=float)
    y = np.asarray(r_fund, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    up, down = x > 0, x < 0
    cu = float(y[up].sum() / x[up].sum()) if up.sum() > 0 and x[up].sum() != 0 else float("nan")
    cd = float(y[down].sum() / x[down].sum()) if down.sum() > 0 and x[down].sum() != 0 else float("nan")
    return cu, cd


def kday(r_fund, r_stock, k=5, rate_accrual=None, fee_accrual=None):
    """Non-overlapping k-day windows as a DataFrame: y (fund log return), x (stock log return), v (realized
    variance of the stock's daily returns inside the window), rdt (sum of rate*accrual), fdt (sum of fee*accrual)."""
    rf = pd.Series(np.asarray(r_fund, dtype=float), index=r_fund.index if isinstance(r_fund, pd.Series) else None)
    rs = pd.Series(np.asarray(r_stock, dtype=float), index=rf.index)
    n = len(rf) // k * k
    rf, rs = rf.iloc[:n], rs.iloc[:n]
    ra = pd.Series(0.0, index=rf.index) if rate_accrual is None else pd.Series(np.asarray(rate_accrual, dtype=float)[:n], index=rf.index)
    fa = pd.Series(0.0, index=rf.index) if fee_accrual is None else pd.Series(np.asarray(fee_accrual, dtype=float)[:n], index=rf.index)
    groups = np.repeat(np.arange(n // k), k)
    rows = []
    for g in range(n // k):
        m = groups == g
        xs, ys = rs.values[m], rf.values[m]
        if (1 + xs <= 0).any() or (1 + ys <= 0).any():
            continue
        rows.append({"end": rf.index[m][-1], "y": float(np.log1p(ys).sum()), "x": float(np.log1p(xs).sum()),
                     "v": float(((xs - xs.mean()) ** 2).sum()), "rdt": float(ra.values[m].sum()), "fdt": float(fa.values[m].sum())})
    return pd.DataFrame(rows).set_index("end") if rows else pd.DataFrame(columns=["y", "x", "v", "rdt", "fdt"])


def exact_beta(r_fund, r_stock, k=5, rate_accrual=None, fee_accrual=None, payout=None, lo=0.0, hi=4.0, iters=200):
    """One-parameter least squares with the EXACT discrete daily-reset model (no small-move approximation).

    Minimizes over beta:  sum_i ( y_i - sum_{t in window i} log((1 - d_t)(1 + beta r_t - (beta - 1) ra_t - fa_t) + d_t) )^2
    where y_i is the fund's k-day log return, r_t the stock's daily simple return, ra_t the daily rate accrual,
    fa_t the daily fee accrual and d_t the fund's payout fraction (as in decompose.layers). Leung and Santoli's
    model (cubic_beta) expands the log to second order, which is exact only for small daily moves; single stocks
    with 30% days bias it upward (SMCX 2.17 vs 2.006 on the same data, audit 2026-10-22). Golden-section search on
    [lo, hi]. Returns (beta, rmse, n_windows); NaN when a fund day is -100% or no beta keeps every day's gross
    return positive (the search would otherwise drift to a bound).
    """
    rf = np.asarray(r_fund, dtype=float)
    rs = np.asarray(r_stock, dtype=float)
    n = len(rf) // k * k
    rf, rs = rf[:n], rs[:n]
    ra = np.zeros(n) if rate_accrual is None else np.asarray(rate_accrual, dtype=float)[:n]
    fa = np.zeros(n) if fee_accrual is None else np.asarray(fee_accrual, dtype=float)[:n]
    pay = np.zeros(n) if payout is None else np.asarray(payout, dtype=float)[:n]
    if n < 3 * k or np.any(1.0 + rf <= 0) or not np.all(np.isfinite(rf)) or not np.all(np.isfinite(rs)):
        return float("nan"), float("nan"), int(n // k)
    groups = np.repeat(np.arange(n // k), k)
    y = np.array([np.log1p(rf[groups == g]).sum() for g in range(n // k)])

    def objective(beta):
        g = (1.0 - pay) * (1.0 + beta * rs - (beta - 1.0) * ra - fa) + pay
        if np.any(g <= 0):
            return np.inf
        fit = np.array([np.log(g[groups == i]).sum() for i in range(n // k)])
        return float(np.sum((y - fit) ** 2))

    if not np.isfinite(objective(lo)) and not np.isfinite(objective(hi)) and not np.isfinite(objective((lo + hi) / 2)):
        return float("nan"), float("nan"), int(n // k)

    phi = (np.sqrt(5) - 1) / 2
    a, b = lo, hi
    c, d = b - phi * (b - a), a + phi * (b - a)
    fc, fd = objective(c), objective(d)
    for _ in range(iters):
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - phi * (b - a)
            fc = objective(c)
        else:
            a, c, fc = c, d, fd
            d = a + phi * (b - a)
            fd = objective(d)
        if b - a < 1e-10:
            break
    beta = (a + b) / 2
    s = objective(beta)
    if not np.isfinite(s):
        return float("nan"), float("nan"), int(n // k)
    rmse = float(np.sqrt(s / (n // k)))
    return float(beta), rmse, int(n // k)


def cubic_beta(windows):
    """Leung-Santoli leverage estimate from kday() windows. Returns (beta, rmse, n)."""
    w = windows.dropna()
    if len(w) < 3:
        return float("nan"), float("nan"), int(len(w))
    # f_i(beta) = a_i beta + b_i beta^2 + c_i  with a = x - rdt + v/2, b = -v/2, c = (rdt - fdt)
    a = (w["x"] - w["rdt"] + w["v"] / 2.0).values
    b = (-w["v"] / 2.0).values
    c = (w["rdt"] - w["fdt"]).values
    y = w["y"].values
    # S(beta) = sum (y - c - a beta - b beta^2)^2 : quartic; minimize over real beta
    e0 = y - c
    # expand sum of squares into polynomial coefficients in beta (degree 4)
    p4 = np.sum(b * b)
    p3 = np.sum(2 * a * b)
    p2 = np.sum(a * a - 2 * e0 * b)
    p1 = np.sum(-2 * e0 * a)
    p0 = np.sum(e0 * e0)
    poly = np.polynomial.Polynomial([p0, p1, p2, p3, p4])
    crit = poly.deriv().roots()
    real = np.real(crit[np.abs(np.imag(crit)) < 1e-9])
    if len(real) == 0:
        return float("nan"), float("nan"), int(len(w))
    best = min(real, key=lambda z: poly(z))
    fit = a * best + b * best ** 2 + c
    rmse = float(np.sqrt(np.mean((y - fit) ** 2)))
    return float(best), rmse, int(len(w))
