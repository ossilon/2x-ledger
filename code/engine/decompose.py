"""The return decomposition: what the stock did, what frictionless 2x would have done, what the fund did.

Numbers only: no tickers, no files. Inputs are pandas Series on one DatetimeIndex whose first row is the baseline
(value 1.0, return 0). All returns are TOTAL returns (dividends and distributions reinvested); the caller builds
them (domain/total_return.py) and labels them.

Layers, as value indices starting at 1.0 on the first row:
    L0  stock:            prod(1 + r_t)
    L1  frictionless:     prod((1 - d_t)(1 + L_t r_t) + d_t)                 (daily reset, no costs)
    L2  fed funds:        prod((1 - d_t)(1 + L_t r_t - (L_t - 1) rate_t a_t) + d_t)
    B   buy-and-hold:     borrow (L - 1) once at the reference rate, hold the stock, never rebalance; re-levered to
                          the new target at each change of L (the investor re-borrows once per regime); wiped out
                          (0, absorbing) if the position's value reaches zero. The Bessembinder / Wang benchmark.
    L3  fund:             the real fund's total-return index
where L_t is the fund's target leverage on day t (from the register timeline, applied from the effective date
inclusive), rate_t the annual reference rate known before day t (decimal), a_t the calendar-day accrual (days since
the previous row / 365), and d_t the fund's payout on day t as a fraction of its prior close (its distributions).
The payout leaves the levered base on the ex-date and earns nothing that day, which is how the fund itself works:
MSTX paid 27% of its price on 2024-12-31 and applied 2x to the remaining NAV. Without d_t the frictionless layers
would lever the cash that was paid out, and the difference would land in the residual as a false gain.

Differences at the end of a window, in percentage points of the starting value:
    compounding_pp = L1 - L_0 * L0          (the compounding effect of daily reset; Hsieh et al.'s CE)
    financing_pp   = L2 - L1                 (fed funds on the borrowed turn)
    rebalance_pp   = L2 - B                  (daily rebalancing vs buy-and-hold; negative = rebalancing cost)
    residual_pp    = L3 - L2                 (everything the fund adds or loses beyond fed funds: fees, swap spread,
                                              options, tracking, premium changes; Bessembinder's frictions, sign reversed)
    levered_bh_pp  = L3 - B
A layer whose daily gross return reaches zero or below is wiped out: it stays at 0 and `wiped` names the day.

Sources: Bessembinder (2026) "Rebalancing, Frictional Costs, and Returns to Levered Single-Stock ETFs", equations
1-5; Avellaneda and Zhang (2010) for the daily-reset identity; Leung and Santoli (2016) section 2.1.
"""
import numpy as np
import pandas as pd

TRADING_DAYS = 252


def _series(x, index, name):
    if isinstance(x, pd.Series):
        s = x.reindex(index)
        if s.isna().any():
            raise ValueError(f"{name}: missing values on {s.index[s.isna()][0].date()}")
        return s.astype(float)
    return pd.Series(float(x), index=index)


def compound(gross):
    """Cumulative product of gross daily returns with wipe-out: once a value reaches <= 0 the index stays 0."""
    out = np.empty(len(gross))
    level, wiped = 1.0, None
    for i, g in enumerate(np.asarray(gross, dtype=float)):
        if level > 0:
            level = level * g
            if level <= 0 or not np.isfinite(level):
                level, wiped = 0.0, gross.index[i]
        out[i] = level
    s = pd.Series(out, index=gross.index)
    s.attrs["wiped"] = wiped
    return s


def returns_from_index(index_series):
    """Daily simple returns of a value index; the first row is 0 (baseline)."""
    r = index_series.astype(float).pct_change()
    r.iloc[0] = 0.0
    return r


def bh_index(stock_index, cash_index, L):
    """Levered buy-and-hold path with re-levering at each change of target L and an absorbing wipe-out.

    Inside a regime that starts at row s (anchor), B_t = B_s [1 + L (S_t/S_s - 1) - (L - 1)(C_t/C_s - 1)]: the
    investor borrows (L - 1) B_s once at the anchor and holds. When L changes on day t the anchor moves to t - 1,
    so the new target applies to day t's return. All inputs are Series on one index; the first row is the baseline.
    """
    S = np.asarray(stock_index, dtype=float)
    C = np.asarray(cash_index, dtype=float)
    Ls = np.asarray(L, dtype=float) if not np.isscalar(L) else np.full(len(S), float(L))
    n = len(S)
    B = np.empty(n)
    B[0] = 1.0
    anchor, L_reg, wiped = 0, Ls[0], None
    for t in range(1, n):
        if Ls[t] != L_reg:
            anchor, L_reg = t - 1, Ls[t]
        if B[anchor] <= 0 or wiped is not None:
            B[t] = 0.0
            continue
        B[t] = B[anchor] * (1.0 + L_reg * (S[t] / S[anchor] - 1.0) - (L_reg - 1.0) * (C[t] / C[anchor] - 1.0))
        if B[t] <= 0:
            B[t], wiped = 0.0, stock_index.index[t]
    out = pd.Series(B, index=stock_index.index)
    out.attrs["wiped"] = wiped
    return out


def layers(stock_tr, L, rate, accrual, fund_tr=None, payout=None):
    """All layers as a DataFrame on the stock's index. See the module docstring for the definitions."""
    idx = stock_tr.index
    r = returns_from_index(stock_tr)
    Ls = _series(L, idx, "L")
    rt = _series(rate, idx, "rate")
    a = _series(accrual, idx, "accrual")
    d = _series(payout if payout is not None else 0.0, idx, "payout")
    if (d < 0).any() or (d >= 1).any():
        raise ValueError("payout must be a fraction of the prior close in [0, 1)")
    out = pd.DataFrame(index=idx)
    out["r_stock"] = r
    out["L"] = Ls
    out["payout"] = d
    l0 = compound(1.0 + r)
    l1 = compound((1.0 - d) * (1.0 + Ls * r) + d)
    l2 = compound((1.0 - d) * (1.0 + Ls * r - (Ls - 1.0) * rt * a) + d)
    cash = compound(1.0 + rt * a)
    b = bh_index(l0, cash, Ls)
    out["L0"], out["L1"], out["L2"], out["cash"], out["B"] = l0, l1, l2, cash, b
    out["rate_accrual"] = rt * a
    out.attrs["wiped"] = {"L0": l0.attrs["wiped"], "L1": l1.attrs["wiped"], "L2": l2.attrs["wiped"], "B": b.attrs["wiped"]}
    if fund_tr is not None:
        f = fund_tr.reindex(idx)
        if f.isna().any():
            raise ValueError(f"fund index missing on {f.index[f.isna()][0].date()}; align the series first")
        out["L3"] = f.astype(float) / float(f.iloc[0])
        out["r_fund"] = returns_from_index(out["L3"])
    return out


def window_summary(lay, start=None, end=None):
    """Percentage-point decomposition over [start, end] (inclusive; defaults to the whole frame).

    The row at `start` is the window's baseline: every layer is re-based to 1.0 there and B is rebuilt inside the
    window (re-levered at changes of L, absorbing wipe-out), so the return earned ON the start row is excluded. To
    include a session's return, start at the session before it (periods.calendar_years and trailing do this).
    """
    w = lay.loc[start:end]
    if len(w) < 2:
        raise ValueError("a window needs at least two rows")
    base = w.iloc[0]
    L_start = float(w["L"].iloc[1]) if len(w) > 1 else float(base["L"])

    def rebased(col):
        return w[col] / base[col] if base[col] > 0 else pd.Series(0.0, index=w.index)

    l0, l1, l2 = rebased("L0"), rebased("L1"), rebased("L2")
    cash = rebased("cash")
    b = bh_index(l0, cash, w["L"])
    e0, e1, e2, eb = float(l0.iloc[-1]), float(l1.iloc[-1]), float(l2.iloc[-1]), float(b.iloc[-1])
    out = {
        "start": w.index[0], "end": w.index[-1], "days": int(len(w) - 1), "L_start": L_start,
        "stock_pct": 100 * (e0 - 1.0), "naive_pct": 100 * L_start * (e0 - 1.0),
        "l1_pct": 100 * (e1 - 1.0), "l2_pct": 100 * (e2 - 1.0), "b_pct": 100 * (eb - 1.0),
        "compounding_pp": 100 * (e1 - 1.0 - L_start * (e0 - 1.0)),
        "financing_pp": 100 * (e2 - e1),
        "rebalance_pp": 100 * (e2 - eb),
        "b_wiped": b.attrs["wiped"] is not None,
    }
    if "L3" in w:
        e3 = float(rebased("L3").iloc[-1])
        out.update({"fund_pct": 100 * (e3 - 1.0), "residual_pp": 100 * (e3 - e2), "levered_bh_pp": 100 * (e3 - eb)})
    return out


def daily_log_residual(lay):
    """log(1 + r_fund) - log(1 + r_L2) per day; -inf on a wipe-out day. Needs L3."""
    r2 = returns_from_index(lay["L2"])
    rf = lay["r_fund"]
    with np.errstate(divide="ignore", invalid="ignore"):
        d = np.log1p(rf.values) - np.log1p(r2.values)
    d = pd.Series(d, index=lay.index)
    d.iloc[0] = 0.0
    return d


def block_bootstrap_mean(x, block=21, reps=1000, seed=7, scale=1.0):
    """Mean of x and a 95% block-bootstrap interval (circular blocks), all times `scale`.

    Returns (mean, lo, hi). With fewer than 2 blocks the interval is (nan, nan).
    """
    v = np.asarray(x, dtype=float)
    v = v[np.isfinite(v)]
    n = len(v)
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    m = float(v.mean()) * scale
    if n < 2 * block:
        return m, float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    nblocks = int(np.ceil(n / block))
    starts = rng.integers(0, n, size=(reps, nblocks))
    offsets = np.arange(block)
    means = np.empty(reps)
    for k in range(reps):
        pos = (starts[k][:, None] + offsets[None, :]).ravel()[:n] % n
        means[k] = v[pos].mean()
    lo, hi = np.percentile(means, [2.5, 97.5]) * scale
    return m, float(lo), float(hi)


def years_in(index):
    """Calendar years spanned by a DatetimeIndex (365.25-day years)."""
    return (index[-1] - index[0]).days / 365.25


def residual_annual(lay, block=21, reps=1000, seed=7):
    """Annualized log residual of the fund over L2 (negative = cost) with a block-bootstrap 95% interval.

    Annualized on calendar time (total log residual / years), not on a fixed 252 sessions, so holidays and the
    calendar-day accrual of financing come out right. Returns dict(annual_pct, ci_lo_pct, ci_hi_pct, n_days,
    wiped). If the fund or L2 was wiped out inside the window the estimate is NaN and `wiped` is True: a -100% day
    has no finite log return.
    """
    d = daily_log_residual(lay).iloc[1:]
    wiped = bool((~np.isfinite(d.values)).any())
    if wiped:
        return {"annual_pct": float("nan"), "ci_lo_pct": float("nan"), "ci_hi_pct": float("nan"),
                "n_days": int(len(d)), "wiped": True}
    years = years_in(lay.index)
    scale = (len(d) / years) * 100 if years > 0 else float("nan")   # mean per session * sessions per year
    m, lo, hi = block_bootstrap_mean(d.values, block=block, reps=reps, seed=seed, scale=scale)
    return {"annual_pct": m, "ci_lo_pct": lo, "ci_hi_pct": hi, "n_days": int(len(d)), "wiped": False}


def financing_annual_pct(lay):
    """Fed funds on the borrowed turns over the frame, annualized (percent of NAV a year, positive)."""
    cost = ((lay["L"] - 1.0) * lay["rate_accrual"]).iloc[1:]
    years = years_in(lay.index)
    return float(100 * cost.sum() / years) if years > 0 else float("nan")
