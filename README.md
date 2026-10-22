# 2x Single-Stock ETF Ledger

A monthly research ledger on US-listed 2x long single-stock ETFs. Each month the engine measures every fund against
its stock on total return and writes one row per fund to `ledger.csv`. The method is open, the tests run on planted
answers, and the hypotheses went on record before the data that tests them. Research tooling, not investment advice.

## The ten questions

<!-- render:questions -->
Latest run: as of 2026-09-30, 21 ranked funds. `DATA_DICTIONARY.md` defines each column.

| # | The question | The statistic | Latest value | Reading |
|---|---|---|---|---|
| 1 | Does it give me 2x each day? | Realized leverage: the slope of the fund's daily return on the stock's, with the tracking error | daily slope 1.99 (range 1.98 to 2.03); tracking error 1.7 to 6.8 percent a year | Every slope sits within 0.05 of its target. The tracking error shows the daily noise around it. |
| 2 | What does it cost me? | All-in cost beyond fed funds on the borrowed turn, since launch, with a 95 percent interval | 4.7 to 32.6 percent a year; median 7.6 | The median fund costs 8 times its stated expense ratio. The fee is a small part of the cost. |
| 3 | How much does volatility cost? | Realized volatility of the stock and the exact compounding penalty of a 2x reset | stock volatility 46 percent (range 25 to 110); compounding penalty 6 to 120 percent a year | For the median fund, the compounding penalty exceeds the product cost. |
| 4 | Does this stock trend or chop? | Variance ratio of the stock's returns (10 days) with its robust z, trailing 252 sessions | 9 of 13 stocks below 1; median 0.91; robust z from -1.6 to +1.1 | No stock's variance ratio differs from 1 at the 5 percent level. One year cannot tell trend from chop. |
| 5 | Did the daily reset help or hurt? | Rebalancing effect: the frictionless reset fund against levered buy-and-hold | the reset helped 7 funds and hurt 14 since launch; 3 buy-and-hold positions went to zero | Without the daily reset, 3 levered positions would have lost everything. |
| 6 | Is 2x too much for this stock? | Hurdle return (exact penalty plus rate plus cost) and Kelly leverage with its interval | 9 of 21 funds: the stock grew faster than the hurdle since launch; Kelly intervals that exclude 2: 3 below, 0 above | For 12 of 21 funds, the stock did not grow fast enough to pay for 2x. The Kelly interval includes 2 for 18 of 21 funds: one year of data cannot set the growth-optimal leverage. |
| 7 | Can it go to zero? | Worst day of the stock, tail index with its standard error, kurtosis, reverse splits | worst stock day in the captured history -41 percent (SMCI); 2 of 13 stocks fell more than 30 percent in one day | A fall of 50 percent in one day ends a 2x fund. No pilot stock has done that. |
| 8 | What is a year of holding like? | Rolling one-year returns, drawdowns, share of windows above the stock (overlapping windows) | the median fund beat its stock in 41 percent of one-year windows; worst one-year hold -98 percent (MSTX); median maximum drawdown -79 percent | Over a random year, the typical fund lost to its own stock more often than it won. |
| 9 | Can I get in and out at a fair price? | Assets, dollar volume of the stock, their ratio, distribution yield | assets 13,778 million USD across 21 funds; largest fund-to-stock-volume ratio 0.36 (CONL) | Issuer facts from the quote feed, dated 2026-10-21. The ratio compares the fund's size with its stock's daily trading; it is not a measure of spread or impact. |
| 10 | Did real holders make money? | Net flows (v0.1); dollar-weighted return (v0.2) | net flow -492 million USD in the latest month (10 of 21 funds took in money) | Flows show what holders did, not what they earned. The dollar-weighted return comes in v0.2. |
<!-- /render:questions -->

## Cost by fund

<!-- render:costs -->
| Fund | Stock | Issuer | Launch | Cost, percent a year | 95 percent interval | Fund return | Stock return |
|---|---|---|---|---|---|---|---|
| AAPU | AAPL | Direxion | 2022-08-09 | 4.7 | 4.1 to 5.3 | 133% | 106% |
| AAPB | AAPL | GraniteShares | 2022-08-09 | 4.8 | 3.9 to 5.7 | 115% | 106% |
| MSFU | MSFT | Direxion | 2022-09-07 | 4.9 | 4.3 to 5.6 | 85% | 105% |
| GGLL | GOOGL | Direxion | 2022-09-07 | 5.3 | 4.7 to 5.9 | 337% | 217% |
| PTIR | PLTR | GraniteShares | 2024-09-03 | 5.5 | 4.5 to 6.5 | 1,234% | 511% |
| AMZU | AMZN | Direxion | 2022-09-07 | 5.7 | 5.0 to 6.4 | 53% | 92% |
| NVDU | NVDA | Direxion | 2023-09-13 | 6.2 | 5.1 to 7.3 | 621% | 404% |
| PLTU | PLTR | Direxion | 2024-12-11 | 6.6 | 5.2 to 8.0 | 165% | 158% |
| METU | META | Direxion | 2024-06-05 | 6.8 | 5.9 to 7.6 | 21% | 48% |
| TSLL | TSLA | Direxion | 2022-08-09 | 6.8 | 6.1 to 7.6 | -56% | 25% |
| NVDL | NVDA | GraniteShares | 2022-12-13 | 7.6 | 6.4 to 8.9 | 2,712% | 1,168% |
| NVDG | NVDA | Leverage Shares | 2024-12-13 | 7.9 | 6.2 to 9.6 | 64% | 71% |
| AMDL | AMD | GraniteShares | 2024-03-04 | 8.1 | 5.8 to 10.5 | 210% | 221% |
| TSLG | TSLA | Leverage Shares | 2024-12-13 | 8.3 | 6.8 to 9.8 | -70% | -19% |
| NVDX | NVDA | T-Rex | 2023-10-19 | 11.0 | 9.4 to 12.6 | 877% | 444% |
| CONL | COIN | GraniteShares | 2022-08-09 | 11.1 | 9.7 to 12.5 | -73% | 113% |
| TSLT | TSLA | T-Rex | 2023-10-19 | 11.1 | 9.9 to 12.3 | -38% | 61% |
| ASTX | ASTS | Tradr | 2025-07-10 | 13.7 | 10.2 to 17.3 | -64% | 29% |
| MSTU | MSTR | T-Rex | 2024-09-18 | 30.1 | 23.4 to 36.9 | -84% | 15% |
| SMCX | SMCI | Defiance | 2024-08-21 | 30.3 | 27.0 to 33.6 | -98% | -32% |
| MSTX | MSTR | Defiance | 2024-08-14 | 32.6 | 25.5 to 39.6 | -87% | 16% |

Cost: the all-in cost beyond fed funds on the borrowed turn, since the fund's launch, in log terms. The interval is a t interval on a block bootstrap. Returns: total return since launch. Launch: the register's inception date; the first captured close can be the next session. Sorted from the lowest measured cost to the highest.
<!-- /render:costs -->

## Growth against the hurdle

<!-- render:hurdle -->
| Fund | Stock | Stock growth, percent a year (log) | Hurdle, percent a year | Stock cleared the hurdle | Fund beat the stock since launch | Target below 2x for part of its life |
|---|---|---|---|---|---|---|
| AAPU | AAPL | 17.4 | 16.5 | yes | yes | yes |
| AAPB | AAPL | 17.4 | 16.6 | yes | yes | yes |
| MSFU | MSFT | 17.7 | 16.8 | yes | no | yes |
| GGLL | GOOGL | 28.4 | 19.7 | yes | yes | yes |
| AMZU | AMZN | 16.1 | 21.5 | no | no | yes |
| METU | META | 16.8 | 25.4 | no | no | no |
| NVDG | NVDA | 29.7 | 32.1 | no | no | no |
| NVDU | NVDA | 53.1 | 32.5 | yes | yes | yes |
| NVDL | NVDA | 66.9 | 34.8 | yes | yes | yes |
| NVDX | NVDA | 57.4 | 37.6 | yes | yes | no |
| TSLG | TSLA | -11.5 | 44.9 | no | no | no |
| TSLL | TSLA | 5.4 | 45.0 | no | no | yes |
| AMDL | AMD | 46.0 | 47.4 | no | no | no |
| TSLT | TSLA | 16.2 | 48.8 | no | no | no |
| PTIR | PLTR | 87.5 | 49.9 | yes | yes | no |
| PLTU | PLTR | 52.6 | 50.6 | yes | yes | no |
| CONL | COIN | 18.2 | 81.3 | no | no | yes |
| MSTU | MSTR | 7.0 | 105.1 | no | no | no |
| MSTX | MSTR | 7.0 | 107.0 | no | no | yes |
| ASTX | ASTS | 20.9 | 126.1 | no | no | no |
| SMCX | SMCI | -18.4 | 151.6 | no | no | no |

Hurdle: the stock's yearly log growth at which a 2x fund grows as fast as the stock. It has three parts, all over the fund's life. The first is the exact compounding penalty of a 2x reset on the stock's daily returns. The others are the mean fed funds rate and the fund's measured cost.

The hurdle is a statement about a 2x fund. A fund that ran below 2x for part of its life can clear the hurdle and still trail its stock, or the reverse. The last two columns show the realized outcome and that caveat.
<!-- /render:hurdle -->

## How the engine finds the cost

The engine builds four reference series from the stock and compares the real fund with them:

- L0: the stock, on total return.
- L1: a frictionless fund that resets to the target leverage each day. L1 minus 2x the stock is the compounding effect.
- L2: L1 charged the fed funds rate on the borrowed turn. L2 minus L1 is the financing effect.
- B: buy 2x the stock once with borrowed money, hold, pay fed funds, never rebalance. L2 minus B is the rebalancing effect.
- L3: the real fund. L3 minus L2 is the residual: fees, swap spreads, trading costs and missed targets.

The all-in cost is minus the residual as a yearly log rate. A t interval on a block bootstrap gives its uncertainty.
`docs/learn/` explains each step with worked numbers. `docs/CANON.md` lists the research the method rests on.

## Files

| File | Content |
|---|---|
| `ledger.csv` | One row per fund per month-end: 79 columns, append-only. The first rows hold the ten headline questions. |
| `register.csv` | One row per fund: issuer, stock, inception, status, target leverage, expense ratio, sources. |
| `register_leverage.csv` | One row per fund per target-leverage period, with dates and sources. |
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

- The engine computes every number. Nobody edits a result by hand. Estimates carry their sampling error in the
  data dictionary.
- Raw prices and issuer files stay private. The repository publishes aggregates only: no price level, no daily series.
- Capture cutoff: a run sees only the raw price, event and quote files fetched by its cutoff. The register and the
  rate file are current knowledge, not versioned by date. A run is a report on its month, not the information set
  of that month-end.
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

The code needs Python 3.12 or later with numpy, pandas and scipy (`requirements.txt`). The pilot covers 21 funds
on 13 stocks from six issuers. The full census with closed funds is the first task of v0.2. The v0.1.0 tag's
public test suite showed one failure (a test that needed a private file); v0.1.1 is the first release whose public
suite passes.

## Cite

> ossilon (2026). 2x Single-Stock ETF Ledger, version 0.1.1. https://github.com/ossilon/2x-ledger

License: MIT. See `CITATION.cff`.
