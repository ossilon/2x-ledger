# 3. Volatility, the hurdle, and when 2x is too much

## The exact penalty

Each day the stock returns r. A frictionless 2x fund returns 2r. In log terms, the fund's growth that day is
ln(1 + 2r) and two times the stock's growth is 2 ln(1 + r). The difference is the compounding penalty of that day:

    penalty = ln(1 + 2r) - 2 ln(1 + r)

The penalty is negative for every r other than zero. The engine sums it over the window and reports it as a yearly
rate in `vol_drag_annual_pct`. The sum over a year is close to minus the square of the yearly volatility. At 46
percent volatility (TSLA, trailing 252 sessions to 2026-09-30) that is about 21 percent a year. At 82 percent
(MSTR) it is about 67 percent a year. The exact sum differs from the formula when the stock has large jumps.

## The hurdle

Put the pieces together for a buy-and-hold holder. In log terms, over one year, the fund grows about:

    fund growth = 2 x stock growth - volatility squared - fed funds - all-in cost

The fund beats the stock when its growth is larger than the stock's growth. Solve for the stock:

    hurdle = volatility squared + fed funds + all-in cost

The column `hurdle_return_pct` holds this hurdle for each fund. The volatility and the mean rate come from the fund's
life, and the cost is the fund's own measured cost. A stock that grows faster than its hurdle, in log terms, rewards
the 2x holder. A stock that grows more slowly punishes the holder even when the stock rises.

Example as of 2026-09-30: NVDL's hurdle was 35.5 percent a year. NVDA grew 95.2 percent a year (CAGR) since the
fund's launch, far above it, and NVDL returned 2,712 percent against 1,168 percent for the stock. TSLL's hurdle was
45.3 percent a year. TSLA grew 5.6 percent a year since 2022-08-09, and TSLL returned -55.8 percent against +25.2
percent for the stock.

## Kelly leverage

A second view: the leverage that maximizes long-run growth of a position in the stock is about

    L* = (expected excess return) / (volatility squared)

The column `kelly_L_under` estimates it from the trailing 252 sessions with a bootstrap interval. The estimate is
noisy because the expected return of a stock is hard to measure in one year. Read the interval, not the point. A
value below 2 says that 2x is more than the growth-optimal leverage for that stock, on that year's data.

## What this means for a holder

- Volatility is a cost for a 2x fund, paid every day the stock moves.
- The hurdle tells you how fast the stock must grow for the fund to beat the stock.
- In the pilot, few stocks cleared their hurdle. The README table shows which.
- The columns `vol_under_annual_pct`, `vol_drag_annual_pct`, `hurdle_return_pct` and `kelly_L_under` hold the numbers.
