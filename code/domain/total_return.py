"""Total-return series for funds and stocks: TradingView closes plus reinvested dividends and distributions.

Why: the TradingView feed is split-adjusted only. A 2x fund's swap pays the stock's total return and the fund pays
out its collateral interest, so both legs must carry their cash payments or every cost estimate is wrong by the
yield. Yahoo's event list (also split-adjusted) is the history of record for the amounts; for funds, a VERIFIED
distribution in the register overrides Yahoo on the same ex-date when the two differ by more than 1%, and a
VERIFIED register distribution that Yahoo lacks is added.

Convention: a dividend D with ex-date t is reinvested at the close of t:
    r_tr,t = (P_t + D_t) / P_{t-1} - 1,   tr_t = prod(1 + r_tr), tr_0 = 1.
An ex-date that is not a session in the price series is moved to the next session (recorded in attrs).

    stock_tr("NASDAQ:TSLA")            DataFrame close, dividend, ret_px, ret_tr, tr; attrs series_type total_return
    fund_tr("NASDAQ:TSLL")             same, with register overrides applied (attrs lists them)
    crosscheck("NASDAQ:TSLL")          our tr vs Yahoo adjclose: max drift in percent over common dates
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _paths  # noqa: E402,F401
import tv_capture as tc  # noqa: E402
import yahoo_events as ye  # noqa: E402
import register as rg  # noqa: E402

ROOT = _paths.ROOT
OVERRIDE_TOL = 0.01


def tr_index(close, dividends=None):
    """Build the total-return frame from a close Series and a Series of cash amounts indexed by ex-date."""
    c = close.astype(float).sort_index()
    if (c <= 0).any() or c.isna().any():
        raise ValueError("closes must be positive and complete")
    div = pd.Series(0.0, index=c.index)
    moved = []
    if dividends is not None and len(dividends):
        for d, amt in dividends.items():
            if d in c.index:
                div[d] += float(amt)
            else:
                pos = c.index.searchsorted(d)
                if pos < len(c.index):
                    div.iloc[pos] += float(amt)
                    moved.append((str(pd.Timestamp(d).date()), str(c.index[pos].date())))
                else:
                    moved.append((str(pd.Timestamp(d).date()), "after the series end: dropped"))
    ret_px = c.pct_change()
    ret_tr = ret_px + div / c.shift(1)
    ret_px.iloc[0] = 0.0
    ret_tr.iloc[0] = 0.0
    tr = (1.0 + ret_tr).cumprod()
    out = pd.DataFrame({"close": c, "dividend": div, "ret_px": ret_px, "ret_tr": ret_tr, "tr": tr})
    out.attrs.update(series_type="total_return", moved_ex_dates=moved,
                     dividends_total=float(div.sum()), dividend_days=int((div > 0).sum()))
    return out


def yahoo_dividends(symbol, root=ROOT, cutoff=None):
    div, _ = ye.events(symbol, root, cutoff)
    if div.empty:
        return pd.Series(dtype=float)
    return div.groupby("date")["amount"].sum()


def split_factor_after(date, splits):
    """Factor that puts a nominal per-share amount paid on `date` onto today's split-adjusted share basis.

    `splits` is the Yahoo split frame (date, numerator, denominator): a 10:1 forward split (10, 1) after the date
    divides earlier amounts by 10; a 1:10 reverse split (1, 10) multiplies them by 10. Same basis as the prices.
    """
    f = 1.0
    if splits is None or splits.empty:
        return f
    for _, s in splits.iterrows():
        if pd.Timestamp(s["date"]) > pd.Timestamp(date):
            f *= float(s["denominator"]) / float(s["numerator"])
    return f


def register_distributions(symbol, root=ROOT, splits=None):
    """VERIFIED register distributions (issuer nominal amounts) converted to the split-adjusted basis."""
    ev = rg.events(root, symbol, "distribution")
    ev = ev[ev["status"] == "VERIFIED"]
    if ev.empty:
        return pd.Series(dtype=float)
    dates = pd.DatetimeIndex(ev["date"])
    amounts = [float(v) * split_factor_after(d, splits) for v, d in zip(ev["value"], dates)]
    return pd.Series(amounts, index=dates).groupby(level=0).sum()


def merge_distributions(yahoo, register, tol=OVERRIDE_TOL):
    """Yahoo amounts with VERIFIED register amounts applied. Returns (merged Series, notes list)."""
    merged = yahoo.copy().astype(float)
    notes = []
    for d, amt in register.items():
        if d in merged.index:
            y = float(merged[d])
            if y == 0 or abs(amt / y - 1.0) > tol:
                notes.append(f"{d.date()}: register {amt} replaces Yahoo {y}")
                merged[d] = float(amt)
        else:
            notes.append(f"{d.date()}: register {amt} added (not in Yahoo)")
            merged[d] = float(amt)
    return merged.sort_index(), notes


def bars(symbol, root=ROOT, cutoff=None):
    """The symbol's daily bars rebuilt from raw under the cutoff (explicit, else the active captured_by cutoff).

    Rebuilding from raw, rather than reading data/series, is what makes a run point-in-time: a series file on disk
    may have been built from fetches made after the cutoff (audit finding 6, 2026-10-22).
    """
    return tc.build(symbol, root, cutoff=cutoff, write=False)


def stock_tr(symbol, root=ROOT, cutoff=None):
    close = bars(symbol, root, cutoff)["close"]
    div = yahoo_dividends(symbol, root, cutoff)
    out = tr_index(close, div)
    out.attrs.update(symbol=symbol, dividend_source="yahoo events", overrides=[])
    return out


def fund_tr(symbol, root=ROOT, cutoff=None):
    close = bars(symbol, root, cutoff)["close"]
    y = yahoo_dividends(symbol, root, cutoff)
    _, splits = ye.events(symbol, root, cutoff)
    r = register_distributions(symbol, root, splits)
    merged, notes = merge_distributions(y, r)
    out = tr_index(close, merged)
    out.attrs.update(symbol=symbol, dividend_source="yahoo events + VERIFIED register distributions (split-adjusted)",
                     overrides=notes)
    return out


def yahoo_tr(symbol, root=ROOT, cutoff=None):
    """Yahoo's own total-return index (adjclose normalized to its first common value)."""
    y = ye.closes(symbol, root, cutoff)["adjclose"].astype(float)
    return y / y.iloc[0]


def crosscheck(symbol, root=ROOT, cutoff=None, fund=False):
    """Max drift between our TR index and Yahoo's adjclose index on common dates, in percent.

    Both are normalized on the first common date; the drift is max |log(ours / yahoo) - median|. A dividend missing
    or mis-sized on one side shows as a step in the ratio.
    """
    ours = (fund_tr if fund else stock_tr)(symbol, root, cutoff)["tr"]
    theirs = ye.closes(symbol, root, cutoff)["adjclose"].astype(float)
    # note: Yahoo's adjusted close implies an ex-date return of P_t / (P_{t-1} - D) - 1, ours (P_t + D) / P_{t-1} - 1;
    # the two differ by -(D / P_{t-1}) * r_yahoo on the ex-date, so a step appears here on large payout days by design
    both = pd.concat([ours.rename("ours"), theirs.rename("yahoo")], axis=1, join="inner", sort=True).dropna()
    if len(both) < 2:
        return {"symbol": symbol, "common_days": int(len(both)), "max_drift_pct": float("nan")}
    both = both / both.iloc[0]
    lr = np.log(both["ours"] / both["yahoo"])
    drift = (lr - lr.median()).abs()
    return {"symbol": symbol, "common_days": int(len(both)), "max_drift_pct": float(100 * drift.max()),
            "worst_date": str(drift.idxmax().date()), "end_gap_pct": float(100 * (both["ours"].iloc[-1] / both["yahoo"].iloc[-1] - 1))}
