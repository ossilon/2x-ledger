"""Align a fund with its stock on common sessions and flag days the two cannot both be right.

- align(fund_df, stock_df): inner join on dates; returns (fund, stock, info) where info lists sessions present in
  only one series. A missing session is dropped from both, never filled with a zero return.
- relative_guard(r_fund, r_stock, L, tol): dates where |r_fund - L r_stock| exceeds `tol` (absolute, e.g. 0.25).
  A legitimate -45% stock day with a -90% fund day passes; an unadjusted 1:10 split (+900% or -90% with the stock
  flat) fails. Flagged days are reported to the register, not corrected silently.
"""
import numpy as np
import pandas as pd


def align(fund_df, stock_df):
    common = fund_df.index.intersection(stock_df.index)
    info = {"fund_only": [str(d.date()) for d in fund_df.index.difference(stock_df.index)],
            "stock_only": [str(d.date()) for d in stock_df.index.difference(fund_df.index)],
            "common_days": int(len(common))}
    return fund_df.loc[common], stock_df.loc[common], info


def relative_guard(r_fund, r_stock, L, tol=0.25):
    Ls = L.reindex(r_fund.index).astype(float) if isinstance(L, pd.Series) else float(L)
    gap = (r_fund.astype(float) - Ls * r_stock.astype(float)).abs()
    bad = gap[gap > tol]
    return [(str(d.date()), round(float(v), 4)) for d, v in bad.items()]
