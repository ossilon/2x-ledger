# 2. The layers: how the engine finds the cost of a fund

The engine builds four reference series from the stock and compares the real fund with them. Every series uses
total return: the engine reinvests cash payments on the ex-date.

| Layer | What it is | What it isolates |
|---|---|---|
| L0 | The stock | Luck: how the stock did |
| L1 | A frictionless fund that resets to the target leverage each day | The daily reset (compounding) |
| L2 | L1 charged fed funds on the borrowed turn | The fair cost of money |
| B | Buy 2x the stock once with borrowed money, hold, pay fed funds, never rebalance | The alternative to a daily reset |
| L3 | The real fund | Everything the issuer adds: fees, swap spreads, trading costs, tracking |

## The effects, in percentage points

The engine reports differences between the layers over a window, in percentage points of the starting value:

- Compounding effect = L1 - 2 x L0. The daily reset against the naive "two times the stock".
- Financing effect = L2 - L1. The fed funds charge on the borrowed turn.
- Rebalancing effect = L2 - B. The daily reset against a hold with the same borrowing (Bessembinder 2026).
- Residual = L3 - L2. The real fund against the frictionless fund that pays fed funds.

The residual is the product. A negative residual is a cost. It holds fees, the spread the swap bank charges above
fed funds, trading costs, and missed targets.

## The all-in cost

The ledger turns the residual into a yearly rate: the log difference between L3 and L2, divided by the years in the
window. The ledger flips the sign, so a cost is positive. The column is `cost_annual_pct`. A block bootstrap
(blocks of 21 days, 1000 draws) gives the standard error, and a t interval on it gives `residual_ci_lo_pct` and
`residual_ci_hi_pct`.

Example as of 2026-09-30: TSLL cost 6.8 percent a year beyond fed funds since 2022-08-09, with an interval of 6.1
to 7.6. Its stated expense ratio is 0.83 percent. The rest is the price of the exposure: the swap spread and the
trading. MSTX cost 32.6 percent a year (interval 27.0 to 38.1). Costs differ by issuer and by stock. Page 3 shows
why the stock matters.

The cost is a realized measure. It includes any change in the fund's market premium between its first and last
close, which a fund's own NAV would not show.

## Why fed funds, and why one turn

A 2x fund holds two turns of stock and owns one turn of capital, so it borrows one turn. The engine charges the
effective federal funds rate on that turn, known before each day, on a 360-day year as the money market does. It is
the base rate of the money the fund borrows. What the fund pays above it is part of the product's cost and belongs
in the residual.

## What the engine does not do

It does not invent a number. Every column comes from the code in `code/engine/` on the captured prices, and
`tests/run_tests.py` checks the code on planted inputs with known answers. Slopes, intervals, the Kelly leverage
and the tail index are estimates, with their sampling error stated in `DATA_DICTIONARY.md`. A reader can rebuild
any row from the raw files listed in `results/manifests/`.
