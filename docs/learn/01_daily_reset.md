# 1. What a daily reset does to your money

A 2x single-stock ETF promises two times the daily return of one stock, before costs. The promise is for one day.
Over more than one day, the fund's return is the product of its daily returns, not two times the stock's return.

## One round trip

Take a stock at 100. On day 1 it rises 10 percent to 110. On day 2 it falls 9.0909 percent back to 100.

| | Day 1 | Day 2 | Two days |
|---|---|---|---|
| Stock | +10.00% | -9.09% | 0.00% |
| 2x fund | +20.00% | -18.18% | -1.82% |

The stock ends where it started. The fund ends 1.82 percent lower. The fund held 2x at 110 after day 1, so the
fall hit a larger position than the rise had built. `tests/test_engine_decompose.py` checks this number.

## The same effect, both ways

The daily reset does not always cost money. When the stock moves in one direction day after day, the fund
compounds its gains and returns more than two times the stock. The engine calls this the compounding effect:
the return of a frictionless daily-reset fund (layer L1) minus two times the stock's return.

Example from the ledger as of 2026-09-30, TSLL in 2022 (target 1.5x at that time). The stock fell 56.5 percent, and
1.5 times that is -84.8 percent. The frictionless fund fell 73.0 percent. The compounding effect was +11.8 points. In a
steady fall, the daily reset cuts the position each day, so the fund loses less than the naive multiple.

## When the effect is negative

The effect is negative when the stock moves back and forth. The size depends on how much the stock bounces: the
volatility. For a 2x fund, the yearly drag in log terms is close to the square of the yearly volatility. A stock with
60 percent volatility costs a 2x fund about 36 percent a year in compounding. Page 3 shows the exact formula and the
engine's measured values.

## What this means for a holder

- Over one day, the fund does what it says.
- Over months, the fund's return depends on the path of the stock, not only on where it ends.
- A stock that trends helps the fund. A stock that chops hurts it.
- Column `compounding_pp` in `ledger.csv` holds the measured effect for each fund since its launch.
