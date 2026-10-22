# 2x Single-Stock ETF Ledger

A monthly research ledger on US-listed 2x long single-stock ETFs. Each month the engine measures every fund against
its stock on total return and writes one row per fund to `ledger.csv`. The method is open, the tests run on planted
answers, and the hypotheses went on record before the data that tests them. Research tooling, not investment advice.

## The ten questions

<!-- render:questions -->
Latest run: as of 2026-09-30, 21 ranked funds. `DATA_DICTIONARY.md` defines each column.

| # | The question | The statistic | Latest value | Reading |
|---|---|---|---|---|
| 1 | Does it give me 2x each day? | Realized leverage: the slope of the fund's daily return on the stock's | daily slope 1.99 (range 1.98 to 2.03) | Day by day, every fund tracks its target. |
| 2 | What does it cost me? | All-in cost beyond fed funds on the borrowed turn, since launch | 4.7 to 32.6 percent a year; median 7.7 | The median fund costs 8 times its stated expense ratio. The fee is a small part of the cost. |
| 3 | How much does volatility cost? | Realized volatility of the stock and the exact compounding penalty of a 2x reset | stock volatility 46 percent (range 25 to 110); compounding penalty 6 to 120 percent a year | For the median fund, the compounding penalty exceeds the product cost. |
| 4 | Does this stock trend or chop? | Variance ratio of the stock's returns (10 days), trailing 252 sessions | 9 of 13 stocks below 1 (reversal); median 0.91 | Most stocks reversed over the last year. Reversal costs a daily-reset fund against buy-and-hold. |
| 5 | Did the daily reset help or hurt? | Rebalancing effect: the frictionless reset fund against levered buy-and-hold | the reset helped 7 funds and hurt 14 since launch; 3 buy-and-hold positions went to zero | Without the daily reset, 3 levered positions would have lost everything. |
| 6 | Is 2x too much for this stock? | Hurdle return (volatility squared plus rate plus cost) and Kelly leverage | 8 of 21 funds: the stock grew faster than the hurdle since launch; Kelly leverage median 0.5 | For 13 of 21 funds, the stock did not grow fast enough to pay for 2x. The growth-optimal leverage sits below 2 for the median stock. |
| 7 | Can it go to zero? | Worst day of the stock, tail index, kurtosis, reverse splits | worst stock day in the captured history -41 percent (SMCI); 2 of 13 stocks fell more than 30 percent in one day | A fall of 50 percent in one day ends a 2x fund. No pilot stock has done that. |
| 8 | What is a year of holding like? | Rolling one-year returns, drawdowns, share of windows above the stock | the median fund beat its stock in 41 percent of one-year windows; worst one-year hold -98 percent (MSTX); median maximum drawdown -79 percent | Over a random year, the typical fund lost to its own stock more often than it won. |
| 9 | Can I get in and out at a fair price? | Assets, dollar volume of the stock, their ratio, distribution yield | assets 13,778 million USD across 21 funds; largest fund-to-stock-volume ratio 0.36 (CONL) | Issuer facts from the quote feed, dated 2026-10-21. A high ratio means the fund's own trades can move its stock at the close. |
| 10 | Did real holders make money? | Net flows (v0.1); dollar-weighted return (v0.2) | net flow -492 million USD in the latest month (10 of 21 funds took in money) | Flows show what holders did, not what they earned. The dollar-weighted return comes in v0.2. |
<!-- /render:questions -->

## Cost by fund

<!-- render:costs -->
| Fund | Stock | Issuer | Since | Cost, percent a year | 95 percent interval | Fund return | Stock return |
|---|---|---|---|---|---|---|---|
| AAPU | AAPL | Direxion | 2022-08-09 | 4.7 | 4.2 to 5.3 | 133% | 106% |
| AAPB | AAPL | GraniteShares | 2022-08-09 | 4.9 | 4.0 to 5.7 | 115% | 106% |
| MSFU | MSFT | Direxion | 2022-09-07 | 5.0 | 4.3 to 5.7 | 85% | 105% |
| GGLL | GOOGL | Direxion | 2022-09-07 | 5.3 | 4.8 to 5.9 | 337% | 217% |
| PTIR | PLTR | GraniteShares | 2024-09-03 | 5.6 | 4.6 to 6.5 | 1,234% | 511% |
| AMZU | AMZN | Direxion | 2022-09-07 | 5.7 | 5.0 to 6.5 | 53% | 92% |
| NVDU | NVDA | Direxion | 2023-09-13 | 6.2 | 5.3 to 7.3 | 621% | 404% |
| PLTU | PLTR | Direxion | 2024-12-11 | 6.6 | 5.2 to 7.9 | 165% | 158% |
| METU | META | Direxion | 2024-06-05 | 6.8 | 6.0 to 7.6 | 21% | 48% |
| TSLL | TSLA | Direxion | 2022-08-09 | 6.9 | 6.2 to 7.6 | -56% | 25% |
| NVDL | NVDA | GraniteShares | 2022-12-13 | 7.7 | 6.3 to 9.2 | 2,712% | 1,168% |
| NVDG | NVDA | Leverage Shares | 2024-12-13 | 7.9 | 6.3 to 9.5 | 64% | 71% |
| AMDL | AMD | GraniteShares | 2024-03-04 | 8.2 | 6.4 to 10.7 | 210% | 221% |
| TSLG | TSLA | Leverage Shares | 2024-12-13 | 8.3 | 6.7 to 9.8 | -70% | -19% |
| NVDX | NVDA | T-Rex | 2023-10-19 | 11.1 | 9.5 to 12.7 | 877% | 444% |
| CONL | COIN | GraniteShares | 2022-08-09 | 11.2 | 9.8 to 12.4 | -73% | 113% |
| TSLT | TSLA | T-Rex | 2023-10-19 | 11.2 | 10.0 to 12.3 | -38% | 61% |
| ASTX | ASTS | Tradr | 2025-07-10 | 13.8 | 10.6 to 17.1 | -64% | 29% |
| MSTU | MSTR | T-Rex | 2024-09-18 | 30.2 | 24.4 to 37.3 | -84% | 15% |
| SMCX | SMCI | Defiance | 2024-08-21 | 30.4 | 27.3 to 33.6 | -98% | -32% |
| MSTX | MSTR | Defiance | 2024-08-14 | 32.6 | 27.6 to 40.6 | -87% | 16% |

Cost: the all-in cost beyond fed funds on the borrowed turn, since the fund's launch, in log terms. Returns: total return since launch. Sorted from the lowest measured cost to the highest.
<!-- /render:costs -->

## Growth against the hurdle

<!-- render:hurdle -->
| Fund | Stock | Stock growth, percent a year (log) | Hurdle, percent a year | Stock cleared the hurdle | Fund beat the stock since launch |
|---|---|---|---|---|---|
| AAPU | AAPL | 17.4 | 16.6 | yes | yes |
| AAPB | AAPL | 17.4 | 16.7 | yes | yes |
| MSFU | MSFT | 17.7 | 17.0 | yes | no |
| GGLL | GOOGL | 28.4 | 19.7 | yes | yes |
| AMZU | AMZN | 16.1 | 21.8 | no | no |
| METU | META | 16.8 | 25.8 | no | no |
| NVDG | NVDA | 29.7 | 31.9 | no | no |
| NVDU | NVDA | 53.1 | 32.5 | yes | yes |
| NVDL | NVDA | 66.9 | 35.5 | yes | yes |
| NVDX | NVDA | 57.4 | 37.6 | yes | yes |
| TSLG | TSLA | -11.5 | 44.9 | no | no |
| TSLL | TSLA | 5.4 | 45.3 | no | no |
| AMDL | AMD | 46.0 | 48.8 | no | no |
| TSLT | TSLA | 16.2 | 49.5 | no | no |
| PTIR | PLTR | 87.5 | 53.3 | yes | yes |
| PLTU | PLTR | 52.6 | 53.4 | no | yes |
| CONL | COIN | 18.2 | 84.7 | no | no |
| MSTU | MSTR | 7.0 | 108.6 | no | no |
| MSTX | MSTR | 7.0 | 110.6 | no | no |
| ASTX | ASTS | 20.9 | 126.9 | no | no |
| SMCX | SMCI | -18.4 | 136.6 | no | no |

Hurdle: the stock's yearly log growth at which a 2x fund grows as fast as the stock. It equals the stock's variance plus the mean fed funds rate plus the fund's measured cost, all over the fund's life. The last column is the realized outcome.
<!-- /render:hurdle -->

## How the engine finds the cost

The engine builds four reference series from the stock and compares the real fund with them:

- L0: the stock, on total return.
- L1: a frictionless fund that resets to the target leverage each day. L1 minus 2x the stock is the compounding effect.
- L2: L1 charged the fed funds rate on the borrowed turn. L2 minus L1 is the financing effect.
- B: buy 2x the stock once with borrowed money, hold, pay fed funds, never rebalance. L2 minus B is the rebalancing effect.
- L3: the real fund. L3 minus L2 is the residual: fees, swap spreads, trading costs and missed targets.

The all-in cost is minus the residual as a yearly log rate. A block bootstrap gives its interval. `docs/learn/`
explains each step with worked numbers. `docs/CANON.md` lists the research the method rests on.

## Files

| File | Content |
|---|---|
| `ledger.csv` | One row per fund per month-end: 79 columns, append-only. The first rows hold the ten headline questions. |
| `register.csv` | One row per fund: issuer, stock, inception, status, target leverage, expense ratio, sources. |
| `results/<YYYY-MM>/windows.csv` | Returns by calendar year and trailing window, with the layers and effects. |
| `results/manifests/<YYYY-MM>.json` | The hashes of every input file a run read. Dates only. |
| `DATA_DICTIONARY.md` | Unit and definition of every column. |
| `HYPOTHESES.md` | The pre-registered hypotheses, rendered from the hash-chained ledger `forward/hypotheses.jsonl`. |
| `ASSUMPTIONS.md` | Every input, its status and its source. |
| `FINDINGS.md` | What the pilot run showed, with dates. |
| `CHANGELOG.md` | What changed, by step and version. |

## Load the CSV

```python
import pandas as pd
ledger = pd.read_csv("ledger.csv", parse_dates=["asof", "run_date_utc", "inception_date"])
latest = ledger[ledger["asof"] == ledger["asof"].max()]
print(latest[["ticker", "underlying", "cost_annual_pct", "beta_1d", "hurdle_return_pct"]])
```

All returns are total return. Percent columns end in `_pct`. Differences in percentage points end in `_pp`. An
empty cell means the run did not compute the value; the column `coverage` says why.

## Rules

- The engine computes every number. Nobody estimates or edits a result.
- Raw prices and issuer files stay private. The repository publishes aggregates only: no price level, no daily series.
- Point in time: a run as of a past date sees only the raw files that existed then.
- Each row names its inputs by hash (`inputs_sha256` and the manifest). A corrected row is a new row with `restates` set.
- Rankings use funds with at least 126 sessions of history (`ranked`).
- Public text follows `docs/STYLE.md`.

## Run it

```
py -I tests\run_tests.py                                  all tests; must end with "0 failure(s)"
py -I code\product\run_monthly.py --asof 2026-09-30       one monthly run (needs the private raw data)
py -I code\product\render.py                              refresh the tables above from ledger.csv
py -I scripts\ste_check.py                                style lint, must print "0 problem(s)"
py -I scripts\scan_identifiers.py                         privacy scan, must print "0 problem(s)"
```

The pilot covers 21 funds on 13 stocks from six issuers. The full census with closed funds is the first task of v0.2.

## Cite

> ossilon (2026). 2x Single-Stock ETF Ledger, version 0.1.0. https://github.com/ossilon/2x-ledger

License: MIT. See `CITATION.cff`.
