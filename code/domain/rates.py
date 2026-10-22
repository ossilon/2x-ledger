"""Reference rate and accrual for the engine.

- fed_funds_daily(index): effective federal funds (FRED DFF, decimal, from reference/DFF.csv) known BEFORE each
  day: the value dated on or before the previous row (port.rate_on, lag one row). The first row takes the last value
  dated before it. Days after the last DFF date carry the last value forward.
- accrual(index): calendar days since the previous row / 360 (first row 0). Fed funds, OBFR and SOFR are quoted on
  an actual/360 basis (the ISDA floating rate option USD-Federal Funds-H.15 is ACT/360; dealer disclosure read
  2026-10-22). v0.1.0 used 365 and understated the financing by 360/365 (about 0.05 points a year on the pilot).
- fee_accrual(index, expense_pct): annual expense ratio (percent, scalar or Series by date) times calendar days / 365:
  fund fees accrue on a 365-day year.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _paths  # noqa: E402,F401
import port as data_io  # noqa: E402  (load_fred, rate_on, accrual_fraction ported from the LETF kit's data_io.py)

RATE_BASIS = 360     # money-market convention for the reference rate
FEE_BASIS = 365      # expense ratios accrue on a 365-day year


def fed_funds_daily(index, rate_series=None):
    s = data_io.load_fred("DFF") if rate_series is None else rate_series.sort_index()
    out = data_io.rate_on(index, s, lag_rows=1)
    if pd.isna(out.iloc[0]):
        prev = s[s.index < index[0]]
        if prev.empty:
            raise ValueError(f"no reference rate dated before {index[0].date()}")
        out.iloc[0] = float(prev.iloc[-1])
    if out.isna().any():
        raise ValueError(f"reference rate missing on {out.index[out.isna()][0].date()}")
    out.name = "fed_funds"
    out.attrs.update(source="FRED DFF via reference/DFF.csv" if rate_series is None else "caller",
                     convention="value dated on or before the previous row (known before the day); accrues on days/360")
    return out


def accrual(index, basis=RATE_BASIS):
    a = data_io.accrual_fraction(index, basis)
    a.name = "accrual"
    return a


def fee_accrual(index, expense_pct):
    a = data_io.accrual_fraction(index, FEE_BASIS)
    if isinstance(expense_pct, pd.Series):
        e = expense_pct.reindex(index)
        if e.isna().any():
            raise ValueError(f"expense ratio missing on {e.index[e.isna()][0].date()}")
    else:
        e = pd.Series(float(expense_pct), index=index)
    return (e / 100.0) * a
