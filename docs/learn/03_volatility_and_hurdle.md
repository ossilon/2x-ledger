# 3. Volatility, the hurdle, and when 2x is too much

## The exact penalty

Each day the stock returns r. A frictionless 2x fund returns 2r. In log terms, the fund's growth that day is
ln(1 + 2r) and two times the stock's growth is 2 ln(1 + r). The difference is the compounding penalty of that day:

    penalty = ln(1 + 2r) - 2 ln(1 + r)

The penalty is negative for every r other than zero. The engine sums it over the window and reports it as a yearly
rate in `vol_drag_annual_pct`. The sum over a year is close to minus the square of the yearly volatility.

At 46 percent volatility (TSLA, trailing 252 sessions to 2026-09-30) the exact penalty was 21.8 percent a year. At
82 percent (MSTR) it was 64.1. The square of the volatility gives 21 and 67. The exact sum differs from the formula
when the stock has large jumps, more for a fall than for a rise.

## The hurdle

Put the pieces together for a buy-and-hold holder. In log terms, over one year, the fund grows about:

    fund growth = 2 x stock growth - volatility squared - fed funds - all-in cost

The fund beats the stock when its growth is larger than the stock's growth. Solve for the stock:

    hurdle = compounding penalty + fed funds + all-in cost

The formula above writes the penalty as the volatility squared. The engine uses the exact penalty of the stock's
own daily returns instead, because jumps break the square law. The column `hurdle_return_pct` holds this hurdle
for each fund. The penalty and the mean rate come from the fund's life, and the cost is the fund's own measured
cost. A stock that grows faster than its hurdle, in log terms, rewards the 2x holder. A stock that grows more
slowly punishes the holder even when the stock rises.

Example as of 2026-09-30: NVDL's hurdle was 34.8 percent a year. NVDA grew 66.9 percent a year in log terms since
the fund's launch (a CAGR of 95.2 percent), far above it. NVDL returned 2,712 percent against 1,168 percent for
the stock. TSLL's hurdle was 45.0 percent a year. TSLA grew 5.4 percent a year in log terms since 2022-08-09 (a
CAGR of 5.6). TSLL returned -55.8 percent against +25.2 percent for the stock.

The hurdle is a statement about a 2x fund. Several pilot funds ran at 1.5x before 2024. Such a fund can clear the
hurdle and still trail its stock, or the reverse. The README's hurdle table marks those funds.

## Kelly leverage

A second view: the leverage that maximizes long-run growth of a position in the stock is about

    L* = (expected excess return) / (volatility squared)

The engine computes the exact version. It finds the leverage that maximizes the mean log growth of a daily-reset
position on the trailing 252 sessions, with a bootstrap interval. The column is `kelly_L_under`.

The estimate is noisy, because the expected return of a stock is hard to measure in one year. On the pilot, the
interval includes 2 for 18 of 21 funds. Read the interval, not the point. An interval entirely below 2 says that 2x
is more than the growth-optimal leverage for that stock, on that year's data.

## What this means for a holder

- Volatility is a cost for a 2x fund, paid every day the stock moves.
- The hurdle tells you how fast the stock must grow for the fund to beat the stock.
- In the pilot, few stocks cleared their hurdle. The README table shows which.
- The columns `vol_under_annual_pct`, `vol_drag_annual_pct`, `hurdle_return_pct` and `kelly_L_under` hold the numbers.
