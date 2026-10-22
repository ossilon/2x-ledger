# Findings

What the pilot run showed. Run as of 2026-09-30 with the cutoff 2026-10-21; 21 funds on 13 stocks from six
issuers. Every number below comes from `ledger.csv`, `results/2026-09/windows.csv` or the scripts named. The README
holds the full tables. One regime, short histories: read these as measurements, not as laws.

## F1. Costs run from 5 to 33 percent a year beyond fed funds

The all-in cost since launch, in percent a year beyond fed funds on the borrowed turn, by issuer:

| Issuer | Funds | Cost range |
|---|---|---|
| Direxion | AAPU, MSFU, GGLL, AMZU, NVDU, PLTU, METU, TSLL | 4.7 to 6.9 |
| GraniteShares | AAPB, PTIR, NVDL, AMDL, CONL | 4.9 to 11.2 |
| Leverage Shares | NVDG, TSLG | 7.9 to 8.3 |
| T-Rex | NVDX, TSLT, MSTU | 11.1 to 30.2 |
| Tradr | ASTX | 13.8 |
| Defiance | SMCX, MSTX | 30.4 to 32.6 |

The stated expense ratios run from 0.75 to 1.49 percent. The fee is a small part of the cost. The rest is the
price of the exposure: the spread above fed funds that the swap bank charges, the trading, and missed targets.

## F2. Cost rises with the volatility of the stock

The Spearman rank correlation between a fund's cost since launch and its stock's realized volatility was 0.81 over
the 21 funds. On the 12-month window to 2026-09-30 it was 0.76. The correlation of cost with the stated expense
ratio was 0.44. The three funds on the most volatile stocks (MSTR at 82 percent, SMCI at 93 percent) cost about
30 percent a year. Hypothesis H1 tests whether this holds over the next year.

## F3. The issuer sets a gap in cost on the same stock

On NVDA, the T-Rex fund (NVDX) cost 3.4 points a year more than the next fund since launch. On the 12-month window
the gap was 4.5 points. On TSLA, TSLT cost 2.8 points more on both measures. The Direxion, GraniteShares and Leverage
Shares funds on the same stock sat within about 1.5 points of each other. Hypothesis H2 tests the gap.

## F4. Few funds returned twice their stock over a year

On the 12-month window to 2026-09-30, 12 stocks rose. One fund of those 12 (AMDL) returned more than twice its
stock. Over all 21 funds, 4 returned more than twice the stock's return. For 3 of those (CONL, MSTU, MSTX) the
stock fell, and twice the fall went below -100 percent. Calendar years: 0 of 11 funds in 2023, 5 of 20 in 2024,
2 of 21 in 2025. Hypothesis H3 tests this.

Funds that beat their own stock: 11 of 11 in 2023, 13 of 20 in 2024, 4 of 21 in 2025. On the window to 2026-09-30:
4 of 21.

## F5. The daily tracking is exact; the cost is not in the daily slope

The daily slope of fund return on stock return ran from 1.98 to 2.03 across the 21 funds. Day by day, every fund
did what it says. The cost shows up over months, in the residual against the frictionless fund, not in the slope.

## F6. The engine reproduces an earlier audited result

A private cross-check script (`scripts/continuity_pin_local.py`, not in the repository) recomputes the LETF kit's
all-in costs for MSTU and MSTX by half-year. It uses the same definition on this project's data. Every closed window
agrees to 0.00 points. The exception is MSTX late 2024, where the earlier figure carries Yahoo's ex-date
approximation on a large distribution (`ASSUMPTIONS.md`, section 1).

## What this does not show

- One regime. Every fund's history sits inside 2022 to 2026. A long bear market is not in the data.
- Short histories. Most funds have under three years of data. The intervals in `ledger.csv` are wide for a reason.
- A pilot. 21 funds out of about 200 live and 63 closed in 2026. The averages here carry survivor bias until v0.2
  adds the census with closed funds.
- No strategies. v0.1 measures buy-and-hold only. Rules, delays and costs of trading come in v0.2.
