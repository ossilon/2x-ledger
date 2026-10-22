"""Outcome, ruin and growth statistics. Numbers only.

- cagr(index): compound annual growth, calendar years (365.25 days); -1 if the index ends at zero.
- max_drawdown, current_drawdown (percent), underwater_days (calendar days since the last peak; 0 at a peak).
- worst_day, best_day (percent) of a value index.
- hurdle_return(sigma2, rate, cost): the stock's log growth needed for a 2x fund to beat the stock in log growth:
  g* = sigma^2 + r + c, where sigma^2 is the stock's annual variance, r the reference rate and c the fund's all-in
  cost beyond r on one turn (all annual, decimal). From Leung and Santoli (2016) section 3: the LETF log growth is
  psi(beta) = beta (mu - r) + r - f - beta^2 sigma^2 / 2; with beta = 2 and the stock's log growth g = mu - sigma^2/2,
  psi(2) > g iff g > sigma^2 + r + f. Returns the hurdle as an annual percent, both log and simple.
- kelly_leverage(r, rate_daily): growth-optimal leverage (mu_excess / sigma^2) from daily simple returns, with a
  block-bootstrap 95% interval. Explains rather than predicts: fitted on the same history.
- hill_tail_index(r, frac): Hill estimator of the left-tail index of daily losses (lower = fatter tail; 2-4 is
  typical for stocks); k = frac of the sample, at least 10.
- excess_kurtosis, bowley_skew (robust skewness with the 99th and 1st percentiles, Bessembinder 2026).
"""
import numpy as np
import pandas as pd

TRADING_DAYS = 252


def cagr(index_series):
    s = index_series.astype(float)
    years = (s.index[-1] - s.index[0]).days / 365.25
    if years <= 0 or s.iloc[0] <= 0:
        return float("nan")
    return float((s.iloc[-1] / s.iloc[0]) ** (1 / years) - 1) if s.iloc[-1] > 0 else -1.0


def max_drawdown(index_series):
    s = index_series.astype(float)
    return float(100 * (s / s.cummax() - 1.0).min())


def current_drawdown(index_series):
    s = index_series.astype(float)
    return float(100 * (s.iloc[-1] / s.max() - 1.0))


def underwater_days(index_series):
    """Calendar days since the series was last at its running peak; 0 when it ends at a peak."""
    s = index_series.astype(float)
    at_peak = s[s >= s.cummax()]
    last_peak = at_peak.index[-1]
    return int((s.index[-1] - last_peak).days)


def worst_day(index_series):
    r = index_series.astype(float).pct_change().dropna()
    return float(100 * r.min()) if len(r) else float("nan")


def best_day(index_series):
    r = index_series.astype(float).pct_change().dropna()
    return float(100 * r.max()) if len(r) else float("nan")


def hurdle_return(sigma2, rate, cost):
    g = sigma2 + rate + cost
    return {"hurdle_log_pct": 100 * g, "hurdle_simple_pct": 100 * (np.exp(g) - 1)}


def kelly_leverage(r, rate_daily=0.0, block=21, reps=1000, seed=11):
    """(L*, lo, hi) with L* = mean(r - rate_daily) / var(r) on daily simple returns."""
    v = np.asarray(r, dtype=float)
    rd = np.asarray(rate_daily, dtype=float) if not np.isscalar(rate_daily) else float(rate_daily)
    ex = v - rd
    ok = np.isfinite(ex)
    ex, v = ex[ok], v[ok]
    n = len(ex)
    if n < 30 or v.var() == 0:
        return float("nan"), float("nan"), float("nan")
    point = float(ex.mean() / v.var(ddof=1))
    if n < 2 * block:
        return point, float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    nblocks = int(np.ceil(n / block))
    starts = rng.integers(0, n, size=(reps, nblocks))
    offsets = np.arange(block)
    est = np.empty(reps)
    for k in range(reps):
        pos = (starts[k][:, None] + offsets[None, :]).ravel()[:n] % n
        e, x = ex[pos], v[pos]
        est[k] = e.mean() / x.var(ddof=1) if x.var() > 0 else np.nan
    lo, hi = np.nanpercentile(est, [2.5, 97.5])
    return point, float(lo), float(hi)


def hill_tail_index(r, frac=0.05, min_k=10):
    """Hill estimator on the left tail (losses) of daily returns."""
    v = np.asarray(r, dtype=float)
    losses = -v[np.isfinite(v)]
    losses = np.sort(losses[losses > 0])[::-1]
    k = max(min_k, int(frac * len(losses)))
    if len(losses) <= k + 1:
        return float("nan")
    top, xk = losses[:k], losses[k]
    return float(k / np.log(top / xk).sum())


def excess_kurtosis(r):
    v = np.asarray(r, dtype=float)
    v = v[np.isfinite(v)]
    if len(v) < 10:
        return float("nan")
    z = (v - v.mean()) / v.std(ddof=0)
    return float((z ** 4).mean() - 3.0)


def bowley_skew(r, hi=99, lo=1):
    v = np.asarray(r, dtype=float)
    v = v[np.isfinite(v)]
    if len(v) < 10:
        return float("nan")
    p_hi, p_lo, p_50 = np.percentile(v, [hi, lo, 50])
    return float((p_hi + p_lo - 2 * p_50) / (p_hi - p_lo)) if p_hi > p_lo else float("nan")
