# Data dictionary

Three public tables. `ledger.csv` has one row per fund per month-end. `register.csv` has one row per fund.
`results/<YYYY-MM>/windows.csv` has one row per fund per window.

Conventions:

- All returns are total return. The engine reinvests each cash payment at the close of its ex-date.
- Percent columns end in `_pct`. Differences in percentage points of the starting value end in `_pp`.
- "Since launch" means from the fund's first captured close to `asof`.
- "Trailing" means the last 252 sessions to `asof`, or all sessions when the fund has fewer.
- An empty cell means the run did not compute the value. The column `coverage` says why.
- The engine computes every column in `code/engine/` and `code/product/run_monthly.py`. `docs/learn/` explains the
  layers L0, L1, L2, B and L3 that several columns use.

## ledger.csv

### Identity

| Column | Unit | Definition |
|---|---|---|
| `schema_version` | integer | The version of this column set. The first release is 1. |
| `asof` | date | The last session the row covers. A month-end. |
| `run_date_utc` | date | The UTC date of the run. |
| `ticker` | text | The fund's ticker. |
| `symbol` | text | The fund in EXCHANGE:TICKER form. |
| `issuer` | text | The issuer's name, from the register. |
| `underlying` | text | The stock in EXCHANGE:TICKER form. |
| `status` | text | `live` or `closed`, from the register. |
| `target_leverage` | ratio | The register's target leverage on `asof`. Some funds ran at 1.5 or 1.75 before 2024. |
| `inception_date` | date | The fund's first trading day, from the register. |
| `expense_ratio_pct` | percent a year | The latest stated expense ratio, from the register. |
| `history_days` | count | Sessions with a return from launch to `asof`. |
| `coverage` | text | What the run computed: `full`, `short history: N sessions`, or the reason for an empty row. |
| `ranked` | true or false | True when `history_days` is at least 126. Rankings use ranked rows only. |

### Question 1: realized leverage (trailing)

| Column | Unit | Definition |
|---|---|---|
| `beta_1d` | ratio | The OLS slope of the fund's daily return on the stock's daily return. |
| `beta_5d` | ratio | The exact one-parameter leverage fit on non-overlapping 5-day windows. The fit includes the rate, the fee and the payout terms. Jumps do not bias it. |
| `r2_1d` | ratio | The R-squared of the 1-day regression. |
| `te_annual_pct` | percent a year | The standard deviation of (fund return minus target times stock return), times the square root of 252. |
| `capture_up_1d` | ratio | The sum of fund returns divided by the sum of stock returns on days the stock rose. Costs are inside this number. |
| `capture_down_1d` | ratio | The same ratio on days the stock fell. |

### Question 2: cost (since launch)

| Column | Unit | Definition |
|---|---|---|
| `cost_annual_pct` | percent a year | The all-in cost beyond fed funds on the borrowed turn: minus `residual_annual_pct`. Empty when the fund went to zero. |
| `residual_annual_pct` | percent a year | The log of (L3 / L2) at `asof`, divided by the years since launch, times 100. Negative means a cost. |
| `residual_ci_lo_pct` | percent a year | The lower end of the 95 percent block-bootstrap interval of `residual_annual_pct` (blocks of 21 days, 1000 draws). |
| `residual_ci_hi_pct` | percent a year | The upper end of that interval. |
| `cost_multiple` | ratio | `cost_annual_pct` divided by `expense_ratio_pct`. |

### Question 3: volatility (trailing)

| Column | Unit | Definition |
|---|---|---|
| `vol_under_annual_pct` | percent a year | The close-to-close realized volatility of the stock: standard deviation of daily returns times the square root of 252. |
| `vol_gk_under_annual_pct` | percent a year | The Garman-Klass volatility of the stock from open, high, low and close. |
| `vol_drag_annual_pct` | percent a year | The exact compounding penalty of a frictionless 2x reset on the stock's daily returns: the sum of ln(1 + 2r) minus 2 ln(1 + r), per year. Negative. |

### Question 4: trend or reversal (trailing)

| Column | Unit | Definition |
|---|---|---|
| `vr_q10_under` | ratio | The Lo-MacKinlay variance ratio of the stock's log returns at 10 days. Above 1 means trend, below 1 means reversal. |
| `ar1_under` | ratio | The lag-one autocorrelation of the stock's daily returns. |

### Question 5: the daily reset (since launch)

| Column | Unit | Definition |
|---|---|---|
| `rebalance_pp` | points | L2 minus B. Positive means the daily reset beat a hold with the same borrowing. |
| `compounding_pp` | points | L1 minus the target leverage times the stock's return. The compounding effect of the daily reset. |

### Question 6: is 2x too much?

| Column | Unit | Definition |
|---|---|---|
| `hurdle_return_pct` | percent a year, log | The stock's yearly log growth at which a 2x fund grows as fast as the stock. It equals variance plus mean rate plus cost, all over the fund's life. |
| `kelly_L_under` | ratio | The growth-optimal leverage on the stock: mean daily excess return over fed funds divided by the variance of daily returns (trailing). |
| `kelly_L_ci_lo` | ratio | The lower end of its 95 percent block-bootstrap interval. |
| `kelly_L_ci_hi` | ratio | The upper end of that interval. |

### Question 7: ruin risk

| Column | Unit | Definition |
|---|---|---|
| `worst_day_under_pct` | percent | The stock's worst daily return since the fund's launch. |
| `worst_day_under_hist_pct` | percent | The stock's worst daily return over its captured history (its listing or the 5000-bar window). |
| `tail_index_under` | ratio | The Hill estimate of the stock's left-tail index on its captured history (the largest 5 percent of losses). Lower means fatter. |
| `kurtosis_under` | ratio | The excess kurtosis of the stock's daily returns (trailing). |
| `reverse_splits` | count | Reverse splits of the fund to `asof`, from the register. |

### Question 8: a year of holding (since launch)

| Column | Unit | Definition |
|---|---|---|
| `max_dd_fund_pct` | percent | The fund's deepest fall from a peak. |
| `current_dd_fund_pct` | percent | The fund's value at `asof` against its highest value, minus 1. |
| `underwater_days` | calendar days | Days since the fund was last at a peak. Zero at a peak. |
| `roll1y_min_pct` | percent | The lowest return over any 252-session window. |
| `roll1y_med_pct` | percent | The median return over all 252-session windows. |
| `roll1y_max_pct` | percent | The highest return over any 252-session window. |
| `p_beat_stock_1y` | share | The share of 252-session windows in which the fund's return exceeded the stock's. |
| `p_beat_2x_stock_1y` | share | The share of 252-session windows in which the fund's return exceeded two times the stock's. |

### Question 9: trading the fund

| Column | Unit | Definition |
|---|---|---|
| `aum_usd_m` | million USD | The fund's assets on `quote_date`, from the quote feed. An issuer fact, not an engine result. |
| `adv_20d_usd_m` | million USD | The stock's mean daily dollar volume over the 20 sessions to `quote_date`. |
| `aum_to_adv_under` | ratio | `aum_usd_m` divided by `adv_20d_usd_m`. |
| `dist_12m_pct` | percent | The fund's cash distributions over the 12 months to `asof`, divided by the price on `asof`. |

### Question 10: holders

| Column | Unit | Definition |
|---|---|---|
| `fund_flows_1m_usd_m` | million USD | The fund's net flow over one month, from the quote feed on `quote_date`. An issuer fact. |

### Detail

| Column | Unit | Definition |
|---|---|---|
| `ret_1m_fund_pct` | percent | The fund's return from the previous month-end to `asof`. |
| `ret_1m_under_pct` | percent | The stock's return over the same month. |
| `tr_incep_fund_pct` | percent | The fund's return since launch (L3). |
| `tr_incep_under_pct` | percent | The stock's return since launch (L0). |
| `tr_incep_ideal_pct` | percent | L1's return since launch. |
| `tr_incep_fedfunds_pct` | percent | L2's return since launch. |
| `tr_incep_bh_pct` | percent | B's return since launch. |
| `cagr_fund_pct` | percent a year | The fund's compound annual growth, on calendar years of 365.25 days. |
| `cagr_under_pct` | percent a year | The stock's compound annual growth. |
| `financing_pp` | points | L2 minus L1 since launch. |
| `residual_pp` | points | L3 minus L2 since launch. |
| `levered_bh_pp` | points | L3 minus B since launch. |
| `financing_annual_pct` | percent a year | The fed funds charge on the borrowed turn, as a yearly log rate. |
| `max_dd_under_pct` | percent | The stock's deepest fall from a peak since the fund's launch. |
| `worst_day_fund_pct` | percent | The fund's worst daily return. |
| `best_day_fund_pct` | percent | The fund's best daily return. |
| `oracle_best_pct` | percent | The largest gain from any earlier close to a later close. The bound of perfect timing. |
| `oracle_worst_pct` | percent | The largest loss from any earlier close to a later close. Equal to `max_dd_fund_pct`. |
| `beta_5d_ls` | ratio | The Leung-Santoli (2016) small-move leverage estimator on 5-day windows. Jumps bias it; shown next to `beta_5d`. |
| `b_wiped` | true or false | True when B reached zero. |
| `beta_spx_under` | ratio | The OLS slope of the stock's daily return on the S&P 500's daily return (trailing). |
| `guard_flags` | count | Days when the fund's return and the target times the stock's return differed by more than 0.25. |
| `quote_date` | date | The date of the quote snapshot behind the issuer facts. |
| `restates` | date | Empty, or the `run_date_utc` of the rows this row supersedes. |
| `inputs_sha256` | hash | The SHA-256 of all input hashes of the run. The manifest lists them. |

## register.csv

| Column | Definition |
|---|---|
| `symbol` | The fund in EXCHANGE:TICKER form. |
| `ticker` | The fund's ticker. |
| `exchange` | The listing exchange. |
| `issuer` | The issuer's name. |
| `fund_name` | The fund's full name. |
| `underlying` | The stock in EXCHANGE:TICKER form. |
| `inception_date` | The fund's first trading day. |
| `status` | `live` or `closed`. |
| `close_date` | The last trading day of a closed fund. |
| `target_leverage_now` | The target leverage on the capture date. |
| `expense_ratio_pct` | The stated expense ratio, percent a year. |
| `expense_asof` | The date of the document that states it. |
| `distributions_url` | The issuer page with the distribution history. |
| `inception_source` | The source of the inception date. |
| `captured_date` | The date on which the author read the register row from its sources. |

## results/<YYYY-MM>/windows.csv

| Column | Unit | Definition |
|---|---|---|
| `asof` | date | The as-of date of the run. |
| `ticker` | text | The fund's ticker. |
| `window` | text | `Y2024` for a calendar year; `T1M`, `T3M`, `T12M` for the trailing 1, 3 and 12 months. |
| `start` | date | The baseline session. The first return in the window is the next session's. |
| `end` | date | The last session in the window. |
| `fund_pct` | percent | The fund's return over the window (L3). |
| `stock_pct` | percent | The stock's return (L0). |
| `naive_pct` | percent | The target leverage at the start times the stock's return. |
| `ideal_pct` | percent | L1's return. |
| `fedfunds_pct` | percent | L2's return. |
| `bh_pct` | percent | B's return, re-based at the window's start. |
| `compounding_pp` | points | `ideal_pct` minus `naive_pct`. |
| `rebalance_pp` | points | `fedfunds_pct` minus `bh_pct`. |
| `residual_pp` | points | `fund_pct` minus `fedfunds_pct`. |
| `L_start` | ratio | The target leverage at the start of the window. |
