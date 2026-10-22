#!/usr/bin/env python3
"""Render the README's data blocks from ledger.csv: the ten questions, the cost table and the hurdle table.

    py -I code\\product\\render.py            rewrites the blocks between the markers in README.md
    py -I code\\product\\render.py --check    exit 1 if README.md differs from a fresh rendering

Every number comes from the latest as-of rows of ledger.csv (ranked funds, latest run per ticker). The one-line
readings are templates chosen by the numbers, so the text never says more than the data: each template has a
state for missing values, for a tie and for a margin too small to call (audit 2026-10-22, M02), and a reading
claims trend, reversal or an optimal leverage only when the statistic's uncertainty allows it. Markers in README.md:

    <!-- render:questions --> ... <!-- /render:questions -->
    <!-- render:costs -->     ... <!-- /render:costs -->
    <!-- render:hurdle -->    ... <!-- /render:hurdle -->
"""
import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _paths  # noqa: E402,F401

ROOT = _paths.ROOT
Z = 1.96              # two-sided 5 percent for the variance-ratio z
MARGIN_PCT = 2.0      # a share within this of 50 percent is "about even"


def latest(root=ROOT):
    """(asof, ranked rows of the latest as-of date, latest run per ticker: a restated row is appended after the row
    it supersedes, so the last occurrence wins)."""
    L = pd.read_csv(Path(root) / "ledger.csv")
    asof = L["asof"].max()
    R = L[L["asof"] == asof].drop_duplicates("ticker", keep="last")
    R = R[R["ranked"].astype(str).str.lower() == "true"].copy()
    return asof, R


def leverage_periods(root=ROOT):
    p = Path(root) / "register_leverage.csv"
    return pd.read_csv(p, dtype=str).fillna("") if p.exists() else pd.DataFrame(columns=["ticker", "target_leverage"])


def names(R, mask):
    return ", ".join(sorted(R.loc[mask, "ticker"]))


def fmt_range(s, d=1):
    s = s.dropna()
    return f"{s.min():.{d}f} to {s.max():.{d}f}" if len(s) else "not computed"


def questions(R, asof):
    n = len(R)
    rows = []
    # 1 realized leverage: slope and tracking error; never "exact"
    b, te = R["beta_1d"], R["te_annual_pct"]
    missing = int(b.isna().sum())
    off = (b - R["target_leverage"]).abs() > 0.05
    v = f"daily slope {b.median():.2f} (range {fmt_range(b, 2)}); tracking error {fmt_range(te)} percent a year"
    if missing:
        r = f"{missing} of {n} funds have no slope yet. For the rest, see the tracking error for the daily noise around the target."
    elif off.any():
        r = f"{int(off.sum())} of {n} funds sit more than 0.05 from target: {names(R, off)}. The tracking error shows the daily noise."
    else:
        r = "Every slope sits within 0.05 of its target. The tracking error shows the daily noise around it."
    rows.append(("1", "Does it give me 2x each day?", "Realized leverage: the slope of the fund's daily return on the stock's, with the tracking error", v, r))
    # 2 cost
    c = R["cost_annual_pct"].dropna()
    mult = (R["cost_annual_pct"] / R["expense_ratio_pct"]).median()
    v = f"{fmt_range(c)} percent a year; median {c.median():.1f}" if len(c) else "not computed"
    r = (f"The median fund costs {mult:.0f} times its stated expense ratio. The fee is a small part of the cost."
         if np.isfinite(mult) else "No cost computed.")
    rows.append(("2", "What does it cost me?", "All-in cost beyond fed funds on the borrowed turn, since launch, with a 95 percent interval", v, r))
    # 3 volatility
    vol, dr = R["vol_under_annual_pct"], R["vol_drag_annual_pct"].abs()
    v = f"stock volatility {vol.median():.0f} percent (range {fmt_range(vol, 0)}); compounding penalty {fmt_range(dr, 0)} percent a year"
    gap = dr.median() - c.median() if len(c) else np.nan
    if not np.isfinite(gap):
        r = "Not computed."
    elif abs(gap) < 0.5:
        r = "For the median fund, the compounding penalty and the product cost are about the same size."
    elif gap > 0:
        r = "For the median fund, the compounding penalty exceeds the product cost."
    else:
        r = "For the median fund, the product cost exceeds the compounding penalty."
    rows.append(("3", "How much does volatility cost?", "Realized volatility of the stock and the exact compounding penalty of a 2x reset", v, r))
    # 4 trend or reversal: only the robust z decides
    S = R.drop_duplicates("underlying")
    vr, z = S["vr_q10_under"], S["vr_q10_z_under"]
    below = int((vr < 1).sum())
    v = f"{below} of {len(S)} stocks below 1; median {vr.median():.2f}; robust z from {z.min():+.1f} to {z.max():+.1f}"
    sig = z.abs() > Z
    if z.isna().all():
        r = "Not computed."
    elif not sig.any():
        r = "No stock's variance ratio differs from 1 at the 5 percent level. One year cannot tell trend from chop."
    else:
        parts = [f"{u.split(':')[-1]} ({'trend' if zz > 0 else 'reversal'})" for u, zz in zip(S.loc[sig, 'underlying'], z[sig])]
        r = f"{int(sig.sum())} of {len(S)} stocks differ from 1 at the 5 percent level: {', '.join(parts)}. The rest are noise."
    rows.append(("4", "Does this stock trend or chop?", "Variance ratio of the stock's returns (10 days) with its robust z, trailing 252 sessions", v, r))
    # 5 the reset
    rb = R["rebalance_pp"]
    helped, hurt = int((rb > 0).sum()), int((rb < 0).sum())
    wiped = int(R["b_wiped"].astype(str).str.lower().eq("true").sum())
    v = f"the reset helped {helped} funds and hurt {hurt} since launch; {wiped} buy-and-hold positions went to zero"
    r = (f"Without the daily reset, {wiped} levered positions would have lost everything." if wiped
         else "No buy-and-hold position went to zero in the pilot.")
    rows.append(("5", "Did the daily reset help or hurt?", "Rebalancing effect: the frictionless reset fund against levered buy-and-hold", v, r))
    # 6 hurdle and Kelly: the interval, not the point, decides
    growth = 100 * np.log1p(R["cagr_under_pct"] / 100)
    cleared = growth > R["hurdle_return_pct"]
    nb, na = int((R["kelly_L_ci_hi"] < 2).sum()), int((R["kelly_L_ci_lo"] > 2).sum())
    inside = n - nb - na
    v = f"{int(cleared.sum())} of {n} funds: the stock grew faster than the hurdle since launch; Kelly intervals that exclude 2: {nb} below, {na} above"
    r = f"For {int((~cleared).sum())} of {n} funds, the stock did not grow fast enough to pay for 2x. "
    r += (f"The Kelly interval includes 2 for {inside} of {n} funds: one year of data cannot set the growth-optimal leverage."
          if inside > n / 2 else f"The Kelly interval excludes 2 for {nb + na} of {n} funds ({nb} below, {na} above).")
    rows.append(("6", "Is 2x too much for this stock?", "Hurdle return (exact penalty plus rate plus cost) and Kelly leverage with its interval", v, r))
    # 7 ruin
    w = R.loc[R["worst_day_under_hist_pct"].idxmin()]
    big = int((S["worst_day_under_hist_pct"] < -30).sum())
    v = f"worst stock day in the captured history {w['worst_day_under_hist_pct']:.0f} percent ({w['underlying'].split(':')[-1]}); {big} of {len(S)} stocks fell more than 30 percent in one day"
    r = ("A fall of 50 percent in one day ends a 2x fund. No pilot stock has done that." if w["worst_day_under_hist_pct"] > -50
         else f"A fall of 50 percent in one day ends a 2x fund. {w['underlying'].split(':')[-1]} has done that.")
    rows.append(("7", "Can it go to zero?", "Worst day of the stock, tail index with its standard error, kurtosis, reverse splits", v, r))
    # 8 holding
    p = 100 * R["p_beat_stock_1y"].median()
    worst = R.loc[R["roll1y_min_pct"].idxmin()]
    v = f"the median fund beat its stock in {p:.0f} percent of one-year windows; worst one-year hold {worst['roll1y_min_pct']:.0f} percent ({worst['ticker']}); median maximum drawdown {R['max_dd_fund_pct'].median():.0f} percent"
    if abs(p - 50) < MARGIN_PCT:
        r = "Over a random year, the typical fund beat its own stock about as often as it lost to it."
    elif p < 50:
        r = "Over a random year, the typical fund lost to its own stock more often than it won."
    else:
        r = "Over a random year, the typical fund beat its own stock more often than it lost."
    rows.append(("8", "What is a year of holding like?", "Rolling one-year returns, drawdowns, share of windows above the stock (overlapping windows)", v, r))
    # 9 liquidity
    a = R["aum_usd_m"]
    ratio = R["aum_to_adv_under"]
    big = R.loc[ratio.idxmax()] if ratio.notna().any() else None
    qd = R["quote_date"].dropna().iloc[0] if R["quote_date"].notna().any() else "n/a"
    v = f"assets {a.sum():,.0f} million USD across {int(a.notna().sum())} funds"
    v += f"; largest fund-to-stock-volume ratio {big['aum_to_adv_under']:.2f} ({big['ticker']})" if big is not None else ""
    r = f"Issuer facts from the quote feed, dated {qd}. The ratio compares the fund's size with its stock's daily trading; it is not a measure of spread or impact."
    rows.append(("9", "Can I get in and out at a fair price?", "Assets, dollar volume of the stock, their ratio, distribution yield", v, r))
    # 10 flows
    fl = R["fund_flows_1m_usd_m"]
    v = f"net flow {fl.sum():+,.0f} million USD in the latest month ({int((fl > 0).sum())} of {int(fl.notna().sum())} funds took in money)"
    r = "Flows show what holders did, not what they earned. The dollar-weighted return comes in v0.2."
    rows.append(("10", "Did real holders make money?", "Net flows (v0.1); dollar-weighted return (v0.2)", v, r))
    out = [f"Latest run: as of {asof}, {n} ranked funds. `DATA_DICTIONARY.md` defines each column.", "",
           "| # | The question | The statistic | Latest value | Reading |", "|---|---|---|---|---|"]
    out += [f"| {a_} | {q} | {s} | {v} | {r} |" for a_, q, s, v, r in rows]
    return out


def costs(R):
    T = R.sort_values("cost_annual_pct")
    out = ["| Fund | Stock | Issuer | Launch | Cost, percent a year | 95 percent interval | Fund return | Stock return |",
           "|---|---|---|---|---|---|---|---|"]
    for _, x in T.iterrows():
        out.append(f"| {x['ticker']} | {x['underlying'].split(':')[-1]} | {x['issuer']} | {x['inception_date']} | {x['cost_annual_pct']:.1f} | "
                   f"{-x['residual_ci_hi_pct']:.1f} to {-x['residual_ci_lo_pct']:.1f} | {x['tr_incep_fund_pct']:,.0f}% | {x['tr_incep_under_pct']:,.0f}% |")
    out += ["", "Cost: the all-in cost beyond fed funds on the borrowed turn, since the fund's launch, in log terms. "
            "The interval is a t interval on a block bootstrap. Returns: total return since launch. Launch: the register's "
            "inception date; the first captured close can be the next session. Sorted from the lowest measured cost to the highest."]
    return out


def hurdle(R, periods):
    below = set(periods.loc[pd.to_numeric(periods["target_leverage"], errors="coerce") < 2, "ticker"]) if len(periods) else set()
    T = R.assign(growth=100 * np.log1p(R["cagr_under_pct"] / 100))
    T = T.assign(cleared=T["growth"] > T["hurdle_return_pct"], beat=T["tr_incep_fund_pct"] > T["tr_incep_under_pct"]).sort_values("hurdle_return_pct")
    out = ["| Fund | Stock | Stock growth, percent a year (log) | Hurdle, percent a year | Stock cleared the hurdle | Fund beat the stock since launch | Target below 2x for part of its life |",
           "|---|---|---|---|---|---|---|"]
    for _, x in T.iterrows():
        out.append(f"| {x['ticker']} | {x['underlying'].split(':')[-1]} | {x['growth']:.1f} | {x['hurdle_return_pct']:.1f} | "
                   f"{'yes' if x['cleared'] else 'no'} | {'yes' if x['beat'] else 'no'} | {'yes' if x['ticker'] in below else 'no'} |")
    out += ["", "Hurdle: the stock's yearly log growth at which a 2x fund grows as fast as the stock. It has three parts, all over "
            "the fund's life. The first is the exact compounding penalty of a 2x reset on the stock's daily returns. The others are "
            "the mean fed funds rate and the fund's measured cost.", "",
            "The hurdle is a statement about a 2x fund. A fund that ran below 2x for part of its life can clear the hurdle and still "
            "trail its stock, or the reverse. The last two columns show the realized outcome and that caveat."]
    return out


def render(readme, root=ROOT):
    asof, R = latest(root)
    periods = leverage_periods(root)
    text = Path(readme).read_text(encoding="utf-8")
    for key, lines in (("questions", questions(R, asof)), ("costs", costs(R)), ("hurdle", hurdle(R, periods))):
        pat = re.compile(rf"(<!-- render:{key} -->\n)(.*?)(<!-- /render:{key} -->)", re.S)
        if not pat.search(text):
            raise ValueError(f"README.md has no render:{key} markers")
        text = pat.sub(lambda m: m.group(1) + "\n".join(lines) + "\n" + m.group(3), text)
    return text


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    readme = ROOT / "README.md"
    new = render(readme)
    if a.check:
        same = new == readme.read_text(encoding="utf-8")
        print("README.md is current" if same else "README.md differs from a fresh rendering; run render.py")
        return 0 if same else 1
    readme.write_text(new, encoding="utf-8", newline="\n")
    print("README.md rendered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
