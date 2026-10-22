"""Outcome, ruin and growth statistics. Numbers only.

- cagr(index): compound annual growth, calendar years (365.25 days); -1 if the index ends at zero.
- max_drawdown, current_drawdown (percent), underwater_days (calendar days since the last peak; 0 at a peak).
- worst_day, best_day (percent) of a value index.
- hurdle_return(drag, rate, cost): the stock's log growth needed for a 2x fund to beat the stock in log growth:
  g* = drag + r + c, where drag is the yearly compounding penalty of the 2x reset (minus the exact penalty; under
  the diffusion law it equals sigma^2), r the reference rate and c the fund's all-in cost beyond r on one turn (all
  annual, decimal). From Leung and Santoli (2016) section 3: the LETF log growth is
  psi(beta) = beta (mu - r) + r - f - beta^2 sigma^2 / 2; with beta = 2 and the stock's log growth g = mu - sigma^2/2,
  psi(2) > g iff g > sigma^2 + r + f. Returns the hurdle as an annual percent, both log and simple.
- kelly_leverage(r, rate_daily): the exact discrete growth-optimal leverage (argmax of mean log growth) from daily
  simple returns, with a block-bootstrap 95% interval. Explains rather than predicts: fitted on the same history.
- hill_tail(r, frac): Hill estimator of the left-tail index of daily losses with its standard error (lower = fatter
  tail; 2-4 is typical for stocks); k = frac of the sample, at least 10. hill_tail_index returns alpha alone.
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


def hurdle_return(drag, rate, cost):
    """Hurdle g* = drag + r + c (annual, decimal): the stock's log growth at which a 2x fund grows as fast as the stock.

    `drag` is the yearly compounding penalty of the 2x reset as a positive number: minus the exact penalty
    (drag.exact_penalty, what the ledger uses since v0.1.1) or sigma^2 under the diffusion law (the explainer).
    The exact penalty keeps the hurdle consistent with the engine's own layers; the law understated SMCX's by 15
    points and overstated PLTR's by 3 (engine review 2026-10-22).
    """
    g = drag + rate + cost
    return {"hurdle_log_pct": 100 * g, "hurdle_simple_pct": 100 * (np.exp(g) - 1)}


def _kelly_exact(ex, rd, lo=-2.0, hi=6.0, iters=80):
    """argmax over L of mean ln(1 + rd + L ex): the exact discrete growth-optimal leverage on the sample path.

    Feasibility: 1 + rd + L ex > 0 on every day bounds L from below (days with ex > 0) and above (ex < 0). The
    objective is concave in L, so a golden-section search on the feasible part of [lo, hi] finds the maximum.
    """
    base = 1.0 + rd
    pos, neg = ex > 0, ex < 0
    if pos.any():
        lo = max(lo, float((-base[pos] / ex[pos]).max()) + 1e-9)
    if neg.any():
        hi = min(hi, float((-base[neg] / ex[neg]).min()) - 1e-9)
    if not hi > lo:
        return float("nan")

    def f(L):
        g = base + L * ex
        return float(np.log(g).mean()) if np.all(g > 0) else -np.inf

    phi = (np.sqrt(5) - 1) / 2
    a, b = lo, hi
    c, d = b - phi * (b - a), a + phi * (b - a)
    fc, fd = f(c), f(d)
    for _ in range(iters):
        if fc > fd:
            b, d, fd = d, c, fc
            c = b - phi * (b - a)
            fc = f(c)
        else:
            a, c, fc = c, d, fd
            d = a + phi * (b - a)
            fd = f(d)
    return float((a + b) / 2)


def kelly_leverage(r, rate_daily=0.0, block=21, reps=1000, seed=11):
    """(L*, lo, hi): the exact growth-optimal leverage on daily simple returns with a block-bootstrap 95% interval.

    L* maximizes the sample mean of ln(1 + rd_t + L (r_t - rd_t)), the discrete growth of a daily-reset position
    financed at rd_t. The textbook ratio mean(r - rd) / var(r) is its second-order approximation; on the pilot the
    two differ by under 0.2 (engine review 2026-10-22). The interval is the percentile range of the same maximizer
    on circular block resamples; it is wide on one year of a single stock (pilot: 18 of 21 include 2). Explains
    rather than predicts: fitted on the same history.
    """
    v = np.asarray(r, dtype=float)
    rd = np.asarray(rate_daily, dtype=float) if not np.isscalar(rate_daily) else np.full(len(v), float(rate_daily))
    ok = np.isfinite(v) & np.isfinite(rd)
    v, rd = v[ok], rd[ok]
    ex = v - rd
    n = len(ex)
    if n < 30 or v.var() == 0:
        return float("nan"), float("nan"), float("nan")
    point = _kelly_exact(ex, rd)
    if n < 2 * block:
        return point, float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    nblocks = int(np.ceil(n / block))
    starts = rng.integers(0, n, size=(reps, nblocks))
    offsets = np.arange(block)
    est = np.empty(reps)
    for k in range(reps):
        pos = (starts[k][:, None] + offsets[None, :]).ravel()[:n] % n
        est[k] = _kelly_exact(ex[pos], rd[pos])
    lo, hi = np.nanpercentile(est, [2.5, 97.5])
    return point, float(lo), float(hi)


def hill_tail(r, frac=0.05, min_k=10):
    """Hill estimator on the left tail (losses) of daily returns: dict(alpha, se, k).

    k = frac of the losses, at least min_k; se = alpha / sqrt(k) (asymptotic). On Student-t(3) data the estimator
    reads 2.7 to 2.8 with sd 0.34 (2,500 observations) to 0.69 (750): publish alpha with se, never alone.
    """
    v = np.asarray(r, dtype=float)
    losses = -v[np.isfinite(v)]
    losses = np.sort(losses[losses > 0])[::-1]
    k = max(min_k, int(frac * len(losses)))
    if len(losses) <= k + 1:
        return {"alpha": float("nan"), "se": float("nan"), "k": int(k)}
    top, xk = losses[:k], losses[k]
    alpha = float(k / np.log(top / xk).sum())
    return {"alpha": alpha, "se": alpha / np.sqrt(k), "k": int(k)}


def hill_tail_index(r, frac=0.05, min_k=10):
    return hill_tail(r, frac, min_k)["alpha"]


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
