"""Total-return construction and alignment: planted distributions, overrides, split guard."""
import numpy as np
import pandas as pd

from _harness import check, raises
from _synthetic import bdays, gbm_prices
import total_return as trm
import align as al

# 7. a $1 distribution on an ex-date: the price path drops, the total-return index does not
tr_planted = gbm_prices(100, mu=0.1, sigma=0.3, seed=71) / 100.0 * 50.0     # a planted total-return path
k = tr_planted.index[40]
D = 1.0
price = tr_planted.copy()
# price returns after k are lower by D / P_{k-1} on day k, then follow the TR returns again
ret_tr = tr_planted.pct_change().fillna(0.0)
ret_px = ret_tr.copy()
ret_px[k] = ret_tr[k] - D / tr_planted.shift(1)[k]
price = tr_planted.iloc[0] * (1 + ret_px).cumprod()
out = trm.tr_index(price, pd.Series([D], index=[k]))
check("tr_index rebuilds the planted total-return path through a distribution", np.allclose(out["tr"].values * tr_planted.iloc[0], tr_planted.values, rtol=1e-12), out["tr"].iloc[-1] * tr_planted.iloc[0] / tr_planted.iloc[-1])
check("the price path is below the TR path after the ex-date", (out["close"].iloc[41:] < tr_planted.iloc[41:]).all())
check("the frame is labeled total_return and counts one dividend day", out.attrs["series_type"] == "total_return" and out.attrs["dividend_days"] == 1)
# an ex-date on a weekend moves to the next session and is recorded
sat = k + pd.Timedelta(days=(5 - k.dayofweek))
out2 = trm.tr_index(price, pd.Series([D], index=[sat]))
check("a weekend ex-date is moved to the next session", out2.attrs["moved_ex_dates"] and out2["dividend"][out2.index[out2.index > sat][0]] == D)
raises("non-positive closes are refused", lambda: trm.tr_index(pd.Series([1.0, 0.0, 2.0], index=bdays(3))), "positive")

# merge: register overrides a different Yahoo amount and adds a missing one; equal amounts pass through
dates = bdays(5)
yahoo = pd.Series([0.10, 0.288, 0.05], index=[dates[0], dates[2], dates[4]])
reg = pd.Series([0.0279, 0.07, 0.05], index=[dates[2], dates[3], dates[4]])
merged, notes = trm.merge_distributions(yahoo, reg)
check("register amount replaces Yahoo when they differ by more than 1%", abs(merged[dates[2]] - 0.0279) < 1e-12)
check("register amount missing from Yahoo is added", abs(merged[dates[3]] - 0.07) < 1e-12)
check("equal amounts are left alone and Yahoo-only amounts stay", abs(merged[dates[4]] - 0.05) < 1e-12 and abs(merged[dates[0]] - 0.10) < 1e-12)
check("the overrides are listed", len(notes) == 2 and "replaces" in notes[0] and "added" in notes[1], notes)

# the convention on a big payout day: reinvest at the ex-date close, (P + D) / P_prev - 1, not Yahoo's P / (P_prev - D) - 1
days = bdays(3)
px3 = pd.Series([530.2, 351.8, 377.3], index=days)
out3 = trm.tr_index(px3, pd.Series([144.28], index=[days[1]]))
check("ex-date return is (P + D) / P_prev - 1 (MSTX 2024-12-31: -6.44%, not Yahoo's -8.84%)", abs(out3["ret_tr"].iloc[1] - ((351.8 + 144.28) / 530.2 - 1)) < 1e-12 and out3["ret_tr"].iloc[1] > 351.8 / (530.2 - 144.28) - 1)

# register amounts are nominal; later splits move them onto the adjusted basis of the prices
splits = pd.DataFrame({"date": [pd.Timestamp("2025-01-10"), pd.Timestamp("2026-03-19")], "numerator": [10, 1], "denominator": [1, 10]})
check("a 1:10 reverse split after the ex-date multiplies a nominal amount by 10", abs(trm.split_factor_after("2025-06-30", splits) - 10.0) < 1e-12)
check("a 10:1 forward split and a 1:10 reverse split after the ex-date cancel", abs(trm.split_factor_after("2024-12-31", splits) - 1.0) < 1e-12)
check("no split after the ex-date leaves the amount unchanged", abs(trm.split_factor_after("2026-08-25", splits) - 1.0) < 1e-12 and trm.split_factor_after("2024-01-01", None) == 1.0)

# 6. relative split guard: a legitimate -45% stock / -90% fund day passes; unadjusted splits are flagged
px = gbm_prices(300, seed=6)
r_s = px.pct_change().dropna()
r_f = 2.0 * r_s
d1, d2, d3 = r_s.index[50], r_s.index[150], r_s.index[250]
r_s[d1], r_f[d1] = -0.45, -0.90                 # crash day, consistent
r_f[d2] = (1 + r_f[d2]) * 10 - 1                # unadjusted 1:10 reverse split: fund x10
r_f[d3] = (1 + r_f[d3]) / 10 - 1                # unadjusted 10:1 forward split: fund /10
flags = al.relative_guard(r_f, r_s, 2.0, tol=0.25)
dates_flagged = [d for d, _ in flags]
check("split guard flags both unadjusted split days", str(d2.date()) in dates_flagged and str(d3.date()) in dates_flagged, flags)
check("split guard does not flag the legitimate -45%/-90% day", str(d1.date()) not in dates_flagged)
check("split guard flags nothing else", len(flags) == 2, flags)
L = pd.Series(2.0, index=r_s.index)
check("split guard accepts a leverage Series", len(al.relative_guard(r_f, r_s, L)) == 2)

# 12b. align drops a session missing on one side without inventing a zero return
fund_df = pd.DataFrame({"tr": px.values}, index=px.index).drop(px.index[10])
stock_df = pd.DataFrame({"tr": px.values}, index=px.index)
f, s, info = al.align(fund_df, stock_df)
check("align keeps the common sessions only and reports the odd one", len(f) == len(px) - 1 and info["stock_only"] == [str(px.index[10].date())] and info["fund_only"] == [])
