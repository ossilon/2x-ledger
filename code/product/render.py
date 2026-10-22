#!/usr/bin/env python3
"""Render the README's data blocks from ledger.csv: the ten questions, the cost table and the hurdle table.

    py -I code\\product\\render.py            rewrites the blocks between the markers in README.md
    py -I code\\product\\render.py --check    exit 1 if README.md differs from a fresh rendering

Every number comes from the latest as-of rows of ledger.csv (ranked funds). The one-line readings are templates
chosen by the numbers, so the text never says more than the data. Markers in README.md:

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


def latest(root=ROOT):
    """(asof, ranked rows of the latest as-of date, latest run per ticker)."""
    L = pd.read_csv(Path(root) / "ledger.csv")
    asof = L["asof"].max()
    R = L[L["asof"] == asof].sort_values("run_date_utc").drop_duplicates("ticker", keep="last")
    R = R[R["ranked"].astype(str).str.lower() == "true"].copy()
    return asof, R


def names(R, mask):
    return ", ".join(sorted(R.loc[mask, "ticker"]))


def questions(R, asof):
    n = len(R)
    rows = []
    # 1 realized leverage
    off = (R["beta_1d"] - R["target_leverage"]).abs() > 0.05
    v = f"daily slope {R['beta_1d'].median():.2f} (range {R['beta_1d'].min():.2f} to {R['beta_1d'].max():.2f})"
    r = "Day by day, every fund tracks its target." if not off.any() else f"Day by day, {int(off.sum())} funds sit more than 0.05 from target: {names(R, off)}."
    rows.append(("1", "Does it give me 2x each day?", "Realized leverage: the slope of the fund's daily return on the stock's", v, r))
    # 2 cost
    c = R["cost_annual_pct"].dropna()
    mult = (R["cost_annual_pct"] / R["expense_ratio_pct"]).median()
    v = f"{c.min():.1f} to {c.max():.1f} percent a year; median {c.median():.1f}"
    r = f"The median fund costs {mult:.0f} times its stated expense ratio. The fee is a small part of the cost."
    rows.append(("2", "What does it cost me?", "All-in cost beyond fed funds on the borrowed turn, since launch", v, r))
    # 3 volatility
    vol, dr = R["vol_under_annual_pct"], R["vol_drag_annual_pct"].abs()
    v = f"stock volatility {vol.median():.0f} percent (range {vol.min():.0f} to {vol.max():.0f}); compounding penalty {dr.min():.0f} to {dr.max():.0f} percent a year"
    r = ("For the median fund, the compounding penalty exceeds the product cost." if dr.median() > c.median()
         else "For the median fund, the product cost exceeds the compounding penalty.")
    rows.append(("3", "How much does volatility cost?", "Realized volatility of the stock and the exact compounding penalty of a 2x reset", v, r))
    # 4 trend or chop
    S = R.drop_duplicates("underlying")
    k = int((S["vr_q10_under"] < 1).sum())
    v = f"{k} of {len(S)} stocks below 1 (reversal); median {S['vr_q10_under'].median():.2f}"
    r = ("Most stocks reversed over the last year. Reversal costs a daily-reset fund against buy-and-hold." if k > len(S) / 2
         else "Most stocks trended over the last year. Trend helps a daily-reset fund against buy-and-hold.")
    rows.append(("4", "Does this stock trend or chop?", "Variance ratio of the stock's returns (10 days), trailing 252 sessions", v, r))
    # 5 the reset
    helped, hurt, wiped = int((R["rebalance_pp"] > 0).sum()), int((R["rebalance_pp"] < 0).sum()), int(R["b_wiped"].astype(str).str.lower().eq("true").sum())
    v = f"the reset helped {helped} funds and hurt {hurt} since launch; {wiped} buy-and-hold positions went to zero"
    r = (f"Without the daily reset, {wiped} levered positions would have lost everything." if wiped
         else "No buy-and-hold position went to zero in the pilot.")
    rows.append(("5", "Did the daily reset help or hurt?", "Rebalancing effect: the frictionless reset fund against levered buy-and-hold", v, r))
    # 6 hurdle
    growth = 100 * np.log1p(R["cagr_under_pct"] / 100)
    cleared = growth > R["hurdle_return_pct"]
    km = R["kelly_L_under"].median()
    v = f"{int(cleared.sum())} of {n} funds: the stock grew faster than the hurdle since launch; Kelly leverage median {km:.1f}"
    r = f"For {int((~cleared).sum())} of {n} funds, the stock did not grow fast enough to pay for 2x. "
    r += "The growth-optimal leverage sits below 2 for the median stock." if km < 2 else "The growth-optimal leverage sits above 2 for the median stock."
    rows.append(("6", "Is 2x too much for this stock?", "Hurdle return (volatility squared plus rate plus cost) and Kelly leverage", v, r))
    # 7 ruin
    w = R.loc[R["worst_day_under_hist_pct"].idxmin()]
    big = int((S["worst_day_under_hist_pct"] < -30).sum())
    v = f"worst stock day in the captured history {w['worst_day_under_hist_pct']:.0f} percent ({w['underlying'].split(':')[-1]}); {big} of {len(S)} stocks fell more than 30 percent in one day"
    r = ("A fall of 50 percent in one day ends a 2x fund. No pilot stock has done that." if w["worst_day_under_hist_pct"] > -50
         else f"A fall of 50 percent in one day ends a 2x fund. {w['underlying'].split(':')[-1]} has done that.")
    rows.append(("7", "Can it go to zero?", "Worst day of the stock, tail index, kurtosis, reverse splits", v, r))
    # 8 holding
    p = 100 * R["p_beat_stock_1y"].median()
    worst = R.loc[R["roll1y_min_pct"].idxmin()]
    v = f"the median fund beat its stock in {p:.0f} percent of one-year windows; worst one-year hold {worst['roll1y_min_pct']:.0f} percent ({worst['ticker']}); median maximum drawdown {R['max_dd_fund_pct'].median():.0f} percent"
    r = ("Over a random year, the typical fund lost to its own stock more often than it won." if p < 50
         else "Over a random year, the typical fund beat its own stock more often than it lost.")
    rows.append(("8", "What is a year of holding like?", "Rolling one-year returns, drawdowns, share of windows above the stock", v, r))
    # 9 liquidity
    a = R["aum_usd_m"]
    big = R.loc[R["aum_to_adv_under"].idxmax()]
    qd = R["quote_date"].dropna().iloc[0] if R["quote_date"].notna().any() else "n/a"
    v = f"assets {a.sum():,.0f} million USD across {int(a.notna().sum())} funds; largest fund-to-stock-volume ratio {big['aum_to_adv_under']:.2f} ({big['ticker']})"
    r = f"Issuer facts from the quote feed, dated {qd}. A high ratio means the fund's own trades can move its stock at the close."
    rows.append(("9", "Can I get in and out at a fair price?", "Assets, dollar volume of the stock, their ratio, distribution yield", v, r))
    # 10 flows
    fl = R["fund_flows_1m_usd_m"]
    v = f"net flow {fl.sum():+,.0f} million USD in the latest month ({int((fl > 0).sum())} of {int(fl.notna().sum())} funds took in money)"
    r = "Flows show what holders did, not what they earned. The dollar-weighted return comes in v0.2."
    rows.append(("10", "Did real holders make money?", "Net flows (v0.1); dollar-weighted return (v0.2)", v, r))
    out = [f"Latest run: as of {asof}, {n} ranked funds. `DATA_DICTIONARY.md` defines each column.", "",
           "| # | The question | The statistic | Latest value | Reading |", "|---|---|---|---|---|"]
    out += [f"| {a} | {q} | {s} | {v} | {r} |" for a, q, s, v, r in rows]
    return out


def costs(R):
    T = R.sort_values("cost_annual_pct")
    out = ["| Fund | Stock | Issuer | Since | Cost, percent a year | 95 percent interval | Fund return | Stock return |",
           "|---|---|---|---|---|---|---|---|"]
    for _, x in T.iterrows():
        out.append(f"| {x['ticker']} | {x['underlying'].split(':')[-1]} | {x['issuer']} | {x['inception_date']} | {x['cost_annual_pct']:.1f} | "
                   f"{-x['residual_ci_hi_pct']:.1f} to {-x['residual_ci_lo_pct']:.1f} | {x['tr_incep_fund_pct']:,.0f}% | {x['tr_incep_under_pct']:,.0f}% |")
    out += ["", "Cost: the all-in cost beyond fed funds on the borrowed turn, since the fund's launch, in log terms. "
            "Returns: total return since launch. Sorted from the lowest measured cost to the highest."]
    return out


def hurdle(R):
    T = R.assign(growth=100 * np.log1p(R["cagr_under_pct"] / 100))
    T = T.assign(cleared=T["growth"] > T["hurdle_return_pct"], beat=T["tr_incep_fund_pct"] > T["tr_incep_under_pct"]).sort_values("hurdle_return_pct")
    out = ["| Fund | Stock | Stock growth, percent a year (log) | Hurdle, percent a year | Stock cleared the hurdle | Fund beat the stock since launch |",
           "|---|---|---|---|---|---|"]
    for _, x in T.iterrows():
        out.append(f"| {x['ticker']} | {x['underlying'].split(':')[-1]} | {x['growth']:.1f} | {x['hurdle_return_pct']:.1f} | "
                   f"{'yes' if x['cleared'] else 'no'} | {'yes' if x['beat'] else 'no'} |")
    out += ["", "Hurdle: the stock's yearly log growth at which a 2x fund grows as fast as the stock. It equals the stock's variance plus "
            "the mean fed funds rate plus the fund's measured cost, all over the fund's life. The last column is the realized outcome."]
    return out


def render(readme, root=ROOT):
    asof, R = latest(root)
    text = Path(readme).read_text(encoding="utf-8")
    for key, lines in (("questions", questions(R, asof)), ("costs", costs(R)), ("hurdle", hurdle(R))):
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
