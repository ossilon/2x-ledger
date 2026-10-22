"""Windows, rolling returns, oracle bounds, probability of beating a benchmark."""
import numpy as np
import pandas as pd

from _harness import check
from _synthetic import bdays, gbm_prices
import periods as pr

# 9. oracle bounds on a sawtooth: best = trough to later peak, worst = max drawdown; entry precedes exit
idx = bdays(7, "2024-01-01")
p = pd.Series([100, 80, 120, 60, 90, 150, 140.0], index=idx)
best, worst, entry, exit_ = pr.oracle_bounds(p)
check("oracle best gain is 60 -> 150 = +150%", abs(best - 150.0) < 1e-9, best)
check("oracle worst loss is 120 -> 60 = -50%", abs(worst + 50.0) < 1e-9, worst)
check("oracle entry precedes exit", entry == idx[3] and exit_ == idx[5] and entry < exit_, (entry, exit_))

# calendar years and trailing windows: the baseline is the last session BEFORE the window so the first session counts
idx = pd.bdate_range("2022-11-01", "2024-03-15")
cy = pr.calendar_years(idx)
check("calendar years cover partial first and last years", set(cy) == {2022, 2023, 2024})
check("a calendar year's baseline is the last session of the prior year", cy[2023][0] == pd.Timestamp("2022-12-30") and cy[2024][0] == pd.Timestamp("2023-12-29"))
check("the launch year starts at the first session", cy[2022][0] == idx[0])
s, e = pr.trailing(idx, 3)
check("trailing 3 months from a mid-month date: baseline is the last session on or before 3 months back", e == idx[-1] and s == pd.Timestamp("2023-12-15"), s)
# month-end as-of: T1M is exactly the calendar month even when end minus one month is a weekend (2026-08-30 is a Sunday)
idx_me = pd.bdate_range("2025-06-02", "2026-09-30")
s1, e1 = pr.trailing(idx_me, 1)
s3, _ = pr.trailing(idx_me, 3)
s12, _ = pr.trailing(idx_me, 12)
check("T1M on 2026-09-30 is anchored at 2026-08-31, not 2026-08-28", s1 == pd.Timestamp("2026-08-31") and e1 == pd.Timestamp("2026-09-30"), s1)
check("T3M and T12M on a month-end are anchored at month-ends", s3 == pd.Timestamp("2026-06-30") and s12 == pd.Timestamp("2025-09-30"), (s3, s12))
# a mid-month as-of date three sessions before the month-end is NOT treated as a month-end
idx_mid = pd.bdate_range("2025-06-02", "2026-09-25")
s_mid, e_mid = pr.trailing(idx_mid, 1)
check("2026-09-25 is not a month-end: T1M anchors at the last session on or before 2026-08-25", e_mid == pd.Timestamp("2026-09-25") and s_mid == pd.Timestamp("2026-08-25"), s_mid)
# a month whose last weekday is the 30th (November 2026 ends on a Monday) is still a month-end
idx_nov = pd.bdate_range("2025-06-02", "2026-11-30")
check("2026-11-30 (a Monday) is a month-end: T1M anchors at 2026-10-30", pr.trailing(idx_nov, 1)[0] == pd.Timestamp("2026-10-30"), pr.trailing(idx_nov, 1)[0])
# a year's return with that baseline equals the product of the year's daily returns
import decompose as dc
px = pd.Series(100.0 * (1.01) ** np.arange(len(idx)), index=idx)
lay = dc.layers(px, 2.0, 0.0, pd.Series(0.0, index=idx))
b0, b1 = cy[2023]
n_sessions_2023 = int((idx.year == 2023).sum())
check("a calendar-year window includes every session of the year", abs(dc.window_summary(lay, b0, b1)["stock_pct"] - 100 * (1.01 ** n_sessions_2023 - 1)) < 1e-9)

# rolling returns and p_beat on planted paths
px = gbm_prices(600, mu=0.1, sigma=0.2, seed=44)
roll = pr.rolling_return(px, 252)
check("rolling 252-day returns has n - 252 windows", len(roll) == len(px) - 252)
rs = pr.rolling_stats(px, 252)
check("rolling stats in percent with window count", rs["windows"] == len(roll) and abs(rs["min_pct"] - 100 * roll.min()) < 1e-9)
# 15. fund beats the stock in exactly the windows we plant: fund = stock * step up on one date
fund = px.copy()
fund.loc[px.index[400]:] *= 1.5          # every window that straddles day 400 shows the fund ahead
pb = pr.p_beat(fund, px, 252)
ends = np.arange(252, len(px))                    # window end positions; the window starts 252 sessions earlier
straddle = int(((ends >= 400) & (ends - 252 < 400)).sum())
check("p_beat equals the planted share of windows", abs(pb - straddle / len(ends)) < 1e-12, (pb, straddle / len(ends)))
check("p_beat against 2x the stock is lower than against 1x", pr.p_beat(fund, px, 252, multiple=2.0) <= pb)

# episodes: a planted 12% drawdown is found, a 5% one is not
idx = bdays(60, "2024-01-01")
path = np.concatenate([np.linspace(100, 110, 20), np.linspace(110, 96.8, 10), np.linspace(96.8, 112, 15), np.linspace(112, 106.4, 5), np.linspace(106.4, 115, 10)])
bench = pd.Series(path, index=idx)
ep = pr.episodes(bench, threshold=-0.10)
check("episodes finds the one drawdown deeper than 10% and skips the 5% one", len(ep) == 1 and ep[0]["depth"] <= -0.10 and ep[0]["recovery_date"] is not None, ep)
