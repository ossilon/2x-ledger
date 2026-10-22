"""Windows and holding-period statistics. Numbers only; indices are value indices (not returns).

- calendar_years(index): {year: (baseline date, last date)}. The baseline is the LAST session of the previous
  year (so the first session's return belongs to the year), or the first session of the year when none exists (the
  launch year). Pass the pair to decompose.window_summary.
- trailing(index, months): (baseline, end) where the baseline is the last session on or before end minus `months`
  calendar months, so the window covers exactly those months of returns.
- episodes(bench_index, threshold): drawdown episodes of a benchmark deeper than `threshold`, as
  (peak_date, trough_date, recovery_date or None, depth), from port.underwater_spells (ported from the LETF kit's
  metrics.py). Used to define stress windows by rule rather than by hand.
- rolling_return(index, days): return over every window of `days` sessions (end-dated).
- rolling_stats(index, days): min, median, max of those returns in percent, and the count of windows.
- p_beat(fund_index, bench_index, days, multiple): share of windows where the fund's return exceeded `multiple`
  times the benchmark's return.
- oracle_bounds(index): best entry-to-exit gain and worst entry-to-exit loss inside the window (percent): the
  perfect-timing brackets. The worst equals the maximum drawdown; both are 0 when no gain (loss) exists.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _paths  # noqa: E402,F401
import port as letf_metrics  # noqa: E402  (underwater_spells ported from the LETF kit's metrics.py)


def calendar_years(index):
    out = {}
    for y in sorted(set(index.year)):
        d = index[index.year == y]
        prior = index[index < d[0]]
        base = prior[-1] if len(prior) else d[0]
        out[int(y)] = (base, d[-1])
    return out


def trailing(index, months, sessions=None):
    """(baseline, end) covering the last `months` calendar months of returns.

    When `end` is the last session of its month, the baseline is the last session of the month `months` earlier,
    so T1M on a month-end as-of date is exactly the calendar month (audit 2026-10-22: anchoring on end minus one
    month landed on a Sunday and pulled in an extra session). Otherwise the baseline is the last session on or
    before end minus `months` months.

    `sessions`: the full session calendar (an index that runs past `end`), used to decide whether `end` is the last
    session of its month. Without it, the next weekday decides, which is wrong when the month ends on an exchange
    holiday (Good Friday 2024-03-29; audit 2026-10-22, D06).
    """
    end = index[-1]
    later = sessions[sessions > end] if sessions is not None else None
    if later is not None and len(later):
        month_end = later[0].month != end.month           # no later session in the same month
    else:
        month_end = (end + pd.offsets.BDay(1)).month != end.month
    if month_end:
        target = (end.to_period("M") - months).to_timestamp(how="end").normalize()
    else:
        target = end - pd.DateOffset(months=months)
    before = index[index <= target]
    return (before[-1] if len(before) else index[0], end)


def episodes(bench_index, threshold=-0.10):
    """Drawdown episodes deeper than threshold: list of dicts peak_date, trough_date, recovery_date, depth."""
    spells = letf_metrics.underwater_spells(bench_index.astype(float))
    return [s for s in spells if s["depth"] <= threshold]


def rolling_return(index_series, days):
    s = index_series.astype(float)
    return (s / s.shift(days) - 1.0).dropna()


def rolling_stats(index_series, days):
    r = rolling_return(index_series, days)
    if r.empty:
        return {"min_pct": float("nan"), "med_pct": float("nan"), "max_pct": float("nan"), "windows": 0}
    return {"min_pct": float(100 * r.min()), "med_pct": float(100 * r.median()), "max_pct": float(100 * r.max()),
            "windows": int(len(r))}


def p_beat(fund_index, bench_index, days, multiple=1.0):
    f = rolling_return(fund_index, days)
    b = rolling_return(bench_index, days).reindex(f.index)
    ok = f.notna() & b.notna()
    if ok.sum() == 0:
        return float("nan")
    return float((f[ok] > multiple * b[ok]).mean())


def oracle_bounds(index_series):
    """(best_pct, worst_pct, best_entry, best_exit): the largest gain and the largest loss from any close to a later
    or the same close. Both include the zero-length hold, so best >= 0 and worst <= 0, and worst equals the maximum
    drawdown exactly (v0.1.0 excluded the same day and returned a positive "loss" on a rising path; audit
    2026-10-22, D09)."""
    s = index_series.astype(float)
    gains = s / s.cummin() - 1.0
    losses = s / s.cummax() - 1.0
    best_exit = gains.idxmax()
    best = float(gains.max())
    worst = float(losses.min())
    best_entry = s.loc[:best_exit].idxmin()
    return 100 * best, 100 * worst, best_entry, best_exit
