"""Volatility, the compounding penalty, and the statistics that set the sign of the rebalancing effect.

Numbers only. Inputs are daily simple returns (Series or arrays) unless stated.

- realized_vol: close-to-close annualized volatility in percent.
- garman_klass_vol: range-based annualized volatility from open, high, low, close (Garman and Klass 1980).
- exact_penalty: the daily compounding penalty of a daily-reset L-times fund against the L-power benchmark,
  log(1 + L r) - L log(1 + r), summed over the window (negative) and annualized. This is the exact discrete form
  of the "volatility drag" term; the textbook approximation is sigma2_law.
- sigma2_law: (L - L^2) / 2 times the realized variance (sum of squared demeaned daily returns), the
  Avellaneda-Zhang / Cheng-Madhavan approximation of the same quantity (for L = 2: minus the realized variance).
- variance_ratio: Lo and MacKinlay (1988) VR(q) with the small-sample corrections; 1 for a random walk, above 1
  for trending returns, below 1 for reversals. Bessembinder (2026) shows this statistic sets the sign of the
  expected rebalancing cost.
- ar1: lag-one autocorrelation of daily returns (Hsieh, Chang and Chen 2025 use its sign the same way).
"""
import numpy as np
import pandas as pd

TRADING_DAYS = 252


def _arr(x):
    v = np.asarray(x, dtype=float)
    return v[np.isfinite(v)]


def realized_vol(r, annualize=TRADING_DAYS):
    v = _arr(r)
    return float(100 * v.std(ddof=1) * np.sqrt(annualize)) if len(v) > 2 else float("nan")


def garman_klass_vol(o, h, l, c, annualize=TRADING_DAYS):
    """Garman-Klass daily variance: 0.5 ln(h/l)^2 - (2 ln 2 - 1) ln(c/o)^2, averaged, annualized; percent."""
    o, h, l, c = (np.asarray(x, dtype=float) for x in (o, h, l, c))
    ok = np.isfinite(o) & np.isfinite(h) & np.isfinite(l) & np.isfinite(c) & (o > 0) & (h > 0) & (l > 0) & (c > 0)
    if ok.sum() < 3:
        return float("nan")
    hl = np.log(h[ok] / l[ok])
    co = np.log(c[ok] / o[ok])
    var = np.mean(0.5 * hl ** 2 - (2 * np.log(2) - 1) * co ** 2)
    return float(100 * np.sqrt(max(var, 0.0) * annualize))


def exact_penalty(r, L):
    """(total penalty in log units, annualized penalty in percent). NaN if any day wipes the L-fund out."""
    v = _arr(r)
    Ls = float(L) if np.isscalar(L) else _arr(L)
    if np.any(1 + Ls * v <= 0):
        return float("nan"), float("nan")
    per_day = np.log1p(Ls * v) - Ls * np.log1p(v)
    total = float(per_day.sum())
    years = len(v) / TRADING_DAYS
    return total, float(100 * total / years) if years > 0 else float("nan")


def sigma2_law(r, L):
    """(total in log units, annualized percent) of (L - L^2)/2 * realized variance (sum of squared demeaned returns)."""
    v = _arr(r)
    Lf = float(L) if np.isscalar(L) else float(np.mean(_arr(L)))
    rv = float(((v - v.mean()) ** 2).sum())
    total = (Lf - Lf ** 2) / 2.0 * rv
    years = len(v) / TRADING_DAYS
    return total, float(100 * total / years) if years > 0 else float("nan")


def variance_ratio(r, q):
    """Lo-MacKinlay VR(q) on log returns from simple returns, with their unbiased variance estimators.

    sigma_a^2 = sum (x_t - mu)^2 / (n - 1);  sigma_c^2 = sum (x_t + ... + x_{t-q+1} - q mu)^2 / m,
    m = q (n - q + 1) (1 - q / n). VR = sigma_c^2 / sigma_a^2. Needs n > 2q.
    """
    v = _arr(r)
    if np.any(1 + v <= 0):
        return float("nan")
    x = np.log1p(v)
    n = len(x)
    if n <= 2 * q or q < 2:
        return float("nan")
    mu = x.mean()
    sa = ((x - mu) ** 2).sum() / (n - 1)
    sums = np.convolve(x, np.ones(q), mode="valid")           # overlapping q-period sums
    m = q * (n - q + 1) * (1 - q / n)
    sc = ((sums - q * mu) ** 2).sum() / m
    return float(sc / sa) if sa > 0 else float("nan")


def ar1(r):
    v = _arr(r)
    if len(v) < 10:
        return float("nan")
    x = v - v.mean()
    denom = (x ** 2).sum()
    return float((x[1:] * x[:-1]).sum() / denom) if denom > 0 else float("nan")
