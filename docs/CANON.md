# Canon: the sources behind the method

This page lists the research the Ledger rests on, what each source gives the method, and how much of it we read.
The status words: PRIMARY means the full paper or the sections that define the method. ABSTRACT means the abstract
and the table of contents only. SECONDARY means a summary by someone else. We read the PRIMARY items again before
each engine freeze.

## 1. The benchmark and the decomposition (Bessembinder)

**Bessembinder, H. (2026). "Rebalancing, Frictional Costs, and Returns to Levered Single-Stock ETFs."**
SSRN 7383378, draft of 2026-08-31, 39 pages. Status: PRIMARY for sections II and III (benchmark, decomposition,
sample). We have not read the tables in full.

Definitions, in the paper's notation, with S the stock, beta the target leverage, r_t the benchmark interest rate:

- Daily frictionless rebalanced return (equation 1): `R_RB,t = beta * R_S,t + (1 - beta) * r_t`.
- Compound stock return (2a): `R_S,T = prod(1 + R_S,t) - 1`.
- Levered buy-and-hold benchmark (3): `R_BH,T = beta * R_S,T + (1 - beta) * r_T`, where r_T is the compound
  interest over the window. An investor earns this with one loan and no later trade.
- Compound frictionless rebalanced return (4): `R_RB,T = prod(1 + beta * R_S,t + (1 - beta) * r_t) - 1`.
- Decomposition (5): `R_BH,T - R_Act,T = [R_BH,T - R_RB,T] + [R_RB,T - R_Act,T]`. The first bracket is the
  rebalancing cost. He rejects the name "volatility drag" for it. The second bracket is the frictional cost: fees,
  trading costs, premium and discount changes, and swap interest above the benchmark rate. Deviations of actual
  leverage from target (Bianchi and Goldberg) land in the second bracket.
- Benchmark rate: the federal funds rate from FRED, the monthly rate divided by the trading days in the month.
- Data: CRSP daily returns (total return) for 35 funds launched before 2024-03-31, from inception to 2025-12-31.
  The fund list comes from Morningstar. A supplemental sample holds 235 funds launched April 2024 to December
  2025. Two sample funds delisted (PYPT in August 2023, AMDS in June 2025). Some funds changed leverage targets
  inside the sample.
- Results: long funds in the main sample trail the benchmark by 0.75 percent a month, 0.20 from rebalancing and
  0.55 from frictions. The supplemental sample trails by 1.47 percent a month, 0.42 and 1.04. Rebalancing costs fall
  with return serial correlation (variance ratios) and rise with daily volatility.
- Skewness: Bowley's robust measure with the 99th and 1st percentiles, `(P99 + P1 - 2 P50) / (P99 - P1)`.

How the Ledger maps to it: our layer B is his R_BH. Our L2 (frictionless 2x on total return, charged fed funds on the
borrowed turn) is his R_RB. Our L3 is his R_Act. Our `rebalance_pp` = L2 - B is his first bracket with the sign
reversed. Our residual = L3 - L2 is his second bracket with the sign reversed. In both, positive means the fund
side did better.

We use the daily effective federal funds rate (DFF) known before the day, not the monthly average. Our prices are
market closes plus distributions, so premium and discount changes sit in the residual, as in his data.

**Bessembinder, H. (2026). "Volatility and Returns to Leveraged ETFs."** SSRN 7376118, 2026-08-31, 21 pages.
Status: PRIMARY for sections I and II.A (pages 1 to 8).

- The Avellaneda-Zhang approximation (his equation 3): `1 + R_RB,T ~ (1 + R_S,T)^beta * exp((beta - beta^2)/2 * RV_T)`
  with RV_T the realized variance. It holds within one sample path, and readers often misread it. Its benchmark
  `(1 + R_S,T)^beta` is not the buy-and-hold return. The realized variance in it measures within-sample reversals
  once the end points are fixed.
- Expected two-day rebalancing effect (his equation 4): `E[R_BH - R_RB] = (beta - beta^2) (mu1 mu2 + sigma1 sigma2 rho12)`.
  Three implications follow. Expected rebalancing costs fall when serial correlation is higher. Volatility alone has
  no effect when serial correlation is zero; it helps when the correlation is positive and hurts when it is negative.
  The cost is larger for leverage minus beta than for plus beta.
- So the variance ratio of the stock is the statistic to publish next to realized volatility.

**Bessembinder, H. (2025). "Returns to Constant Leverage Strategies: General Principles and Application to Levered
Single-Stock ETFs."** SSRN 5369417, first draft 2025-07-28, current draft 2026-03-12, 59 pages. Status: ABSTRACT.
The parent paper of the two above. It reports 0.79 percent a month (0.26 rebalancing, 0.53 frictions) for long
funds, and a fifty-year hypothetical sample built from CRSP stocks since 1973.

## 2. Costs, flows and who makes money (Murray and Sammon)

**Murray, C. and Sammon, M. (2026). "The Costs and Benefits of Leveraged ETFs."** SSRN 7133021, 2026-08-24,
62 pages. Status: PRIMARY for section 1.3 (fees and financing, pages 11 to 13) and the introduction.

- Five determinants of performance: volatility drag, fees, financing costs, which products the issuers launch,
  and market timing by investors.
- Funding-spread estimate (their equations 5 to 7): the authors regress the fund's daily return less
  `L * R_u - (L - 1) * R_rf - ER / 252` on a constant. The constant times 252 / (L - 1) is the yearly spread over the
  risk-free rate on the borrowed exposure. Index 2x funds: spreads below 1 percent. Single-stock 2x funds: 6.8 to
  9.8 percent.
- All-in yearly cost of a 2x fund at the end-of-sample risk-free rate: index `4.09% + 0.4% + 0.90% = 5.39%`;
  single stock `4.09% + 6.8% + 1.03% = 11.92%`.
- Breakeven: at 5 percent daily volatility the stock must return close to 100 percent in a year for a 2x fund to
  match it.
- Issuers launch single-stock funds on volatile recent winners. The median stock sits at the 94th percentile of
  volatility and the 92nd percentile of past six-month return among the top 1,000 stocks.
- Index LETFs made more than $100 billion for investors, over $40 billion above the unlevered alternative. The
  single-stock verdict depends on flows and timing (their Table 7).

How the Ledger maps to it: our `residual_annual_pct` is their funding spread plus the expense ratio plus tracking
noise. Our `hurdle_return_pct` is their breakeven. The flows columns prepare the v0.2 dollar-weighted return.

## 3. Daily reset against a non-reset position (Wang)

**Wang, B. (2025). "Multi-day Return Properties of Leveraged Index ETFs."** SSRN 5119860, 2025-05-30, 71 pages.
Status: ABSTRACT. ProShares funded the study.

Index LETFs track non-reset portfolios with the same initial leverage over holding periods up to a year. Large
deviations occur under high volatility and long holding periods, and they skew to the positive side. The paper
confirms the levered buy-and-hold benchmark as the right comparison.

## 4. Timing covariance (Bianchi and Goldberg)

**Bianchi, S. W. and Goldberg, L. R. (2026). "A Levered ETF Anomaly Explained."** arXiv 2604.27287; Journal of
Asset Management 27(4). Status: PRIMARY (HTML full text, read 2026-10-22).

S&P 500 2x and 3x funds fell over 2022 to 2023 while the index rose. Identity:
`E(R_ETF) = E(lambda) E(R) + Cov(lambda, R)` with `lambda_t = R_ETF,t / R_t` the realized daily leverage. The
covariance term explained about a quarter to a third of the shortfall. The ratio is unstable near zero index
returns, so winsorize it.

The Ledger does NOT publish this term. The identity is `Cov(lambda, r) = E[(lambda - L) r] - (E[lambda] - L) E[r]`,
the mean daily gap minus a mean term (v0.1.0 wrote it without the mean term; corrected 2026-10-22 after an
independent audit). With returns alone, a constant daily cost c gives `lambda = L - c / r` and a covariance of
`-c + c E[1 / r] E[r]`. That is not zero: a pure cost shows up as "timing". The covariance is observable, but
returns alone do not split it into financing, exposure policy and closing-price noise. We publish the capture
ratios on up and down days instead, costs included.

## 5. Compounding and autocorrelation (Hsieh, Chang and Chen)

**Hsieh, C.-H., Chang, J.-R. and Chen, H. H. (2025). "Compounding Effects in Leveraged ETFs: Beyond the Volatility
Drag Paradigm."** arXiv 2504.20116. Status: PRIMARY (HTML).

`CE_n = prod(1 + L x_t) - 1 - L (prod(1 + x_t) - 1)`. With independent returns the expected effect is non-negative.
Its sign follows the AR(1) coefficient of the stock. Index funds only. Our `compounding_pp` and `ar1_under`.

## 6. Flows into single-stock funds (Luo, Han and Zhang)

**Luo, D., Han, Y. and Zhang, Y. (2026). "The Dynamics of Leveraged Demand: Evidence from Leveraged Single-Stock
ETFs."** SSRN 7554363. Status: ABSTRACT.

Daily creations and redemptions for 453 US funds, July 2022 to July 2026. Flows run against recent stock
performance and react most to losses. Background for the v0.2 flows work.

## 7. Rebalancing predation (Zhao)

**Zhao, Y. (2026). "Preying on Leveraged ETFs."** arXiv 2608.03703. Status: ABSTRACT.

Korean single-stock LETFs: traders position against the predictable rebalance at the close. About 75 percent of
the first-day reaction to overnight US news reversed by the next close. Background for the v0.2 close-reversal
statistic.

## 8. The older canon

- Cheng, M. and Madhavan, A. (2009). "The Dynamics of Leveraged and Inverse Exchange-Traded Funds." Journal of
  Investment Management 7(4). The `(beta^2 - beta) R_t` rebalance trade at the end of the day. Status: SECONDARY
  (cited through Bessembinder).
- Avellaneda, M. and Zhang, S. (2010). "Path-Dependence of Leveraged ETF Returns." SIAM Journal on Financial
  Mathematics 1. The closed form with realized variance, fees and financing. Status: SECONDARY.
- Tang, H. and Xu, X. E. (2013). "Solving the Return Deviation Conundrum of Leveraged Exchange-Traded Funds."
  Journal of Financial and Quantitative Analysis 48(1), 309-342. Compounding against non-compounding deviation.
  Status: ABSTRACT (verified citation).
- Jarrow, R. (2010). "Understanding the Risk of Leveraged ETFs." Finance Research Letters 7(3). Status: from
  memory; verify.
- Trainor, W. and Baryla, E. (2008). "Leveraged ETFs: A Risky Double That Doesn't Multiply by Two." Journal of
  Financial Planning, May 2008. Status: SECONDARY (the PDF exists).
- Lo, A. and MacKinlay, A. C. (1988). "Stock Market Prices Do Not Follow Random Walks." Review of Financial Studies
  1(1). The variance ratio statistic. Status: from memory; verify.

## 9. Books

**Leung, T. and Santoli, M. (2016). *Leveraged Exchange-Traded Funds: Price Dynamics and Options Valuation.***
SpringerBriefs in Quantitative Finance, Springer, 97 pages. ISBN 978-3-319-29092-8 (print), 978-3-319-29094-2
(eBook), DOI 10.1007/978-3-319-29094-2. Status: PRIMARY for chapters 1 to 3 (read 2026-10-22 from the PDF in
`data/papers/`).

We did not read sections 2.4 and 2.5 (leveraged futures and delta-neutral option portfolios) or chapter 4 (options
on LETFs) for this project. It is the one monograph on the subject.

What it gives the engine:

- The leveraged benchmark `L_n = L_0 * prod(1 + beta * R_j)` (their 2.1) is our L1. Their continuous-time value
  (2.4 to 2.7): a long LETF invests `beta * L` in the stock and borrows `(beta - 1) * L` at rate r, with expense
  rate f. So `log(L_t / L_0) = beta * log(S_t / S_0) - ((beta - 1) r + f) t + (1/2) beta (1 - beta) * integral(sigma^2)`.
  For beta = 2 the last term is minus the realized variance. That is our exact penalty against the sigma-squared
  law, with the financing and fee terms spelled out.
- Realized leverage over k-day windows (their 2.3). A plain regression of the LETF log return on the stock log
  return and the realized variance suffers from collinearity. The two implied leverage ratios disagree. Their fix
  has one unknown: minimize `sum (y_i - f_i(beta))^2` with
  `f_i(beta) = beta (x_i - r dT) - beta (beta - 1) / 2 * v_i + (r - f) dT`. Here x_i is the stock log return, v_i the
  realized variance in the window, y_i the LETF log return. The first-order condition is a cubic in beta
  (their 2.12).
- The estimator is stable on quarters of data where regression is not (their Table 2.2). It recovers 2.000 for
  SSO over 2013 to 2015 (their Table 2.1). The model expands the daily log return to second order. That holds for
  index funds but not for single stocks with 30 percent days. On SMCX it reads 2.17 where the fund delivered an
  exact 2x (audit 2026-10-22).
- So the ledger's `beta_5d` minimizes the same one-parameter least squares with the exact discrete model inside
  each window (`leverage.exact_beta`). The book's estimator stays as `beta_5d_ls`.
- Sign-conditional leverage (their Figures 2.4 and 2.5): SSO ran above 2x on days the index rose and below 2x on
  days it fell. SDS did so more. This is the precedent for our `capture_up_1d` and `capture_down_1d`.
- Chapter 3 under constant drift and volatility: the LETF log growth rate is `psi(beta) = beta (mu - r) + r - f - beta^2
  sigma^2 / 2` (their 3.5). It peaks at the growth-optimal `beta = (mu - r) / sigma^2` (our `kelly_L_under`). A 2x
  fund beats the stock in log growth only when the stock's log growth exceeds `r + f + sigma^2`. That is our
  `hurdle_return_pct` with the financing and fee terms stated. The fund is certain to hit any lower barrier in the
  long run when `psi(beta) <= 0`. So the leverage with positive growth lies in
  `((mu - r) +- sqrt((mu - r)^2 + 2 sigma^2 (r - f))) / sigma^2` (their section 3.3).
- Risk tools we may add in v0.2, all closed form under lognormal returns:
  - relative value-at-risk `VaR_a(beta, T) = 1 - exp(psi T + |beta| sigma sqrt(T) Phi^-1(a))` (3.7) and the admissible
    leverage interval it implies (3.10 and 3.11);
  - the admissible risk horizon (3.16);
  - the probability of a hit on a loss level before a horizon (3.18), and on a stop-loss before a take-profit level
    (3.23).
  They explain rather than measure for stocks with jumps.
- MacLean, L., Thorp, E. and Ziemba, W., editors (2011). *The Kelly Capital Growth Investment Criterion.* World
  Scientific. The growth-optimal leverage `L* = (mu - r) / sigma^2`. Status: from memory; verify.
- Lo, A. and MacKinlay, A. C. (1999). *A Non-Random Walk Down Wall Street.* Princeton University Press. Status:
  from memory; verify.
- Hill, J., Nadig, D. and Hougan, M. (2015). *A Comprehensive Guide to Exchange-Traded Funds.* CFA Institute
  Research Foundation, free PDF. Status: from memory; verify.

## 10. Market facts used as context

- GraniteShares (2026-07-14). "GraniteShares 2x Long LCID Daily ETF (Nasdaq: LCDL) Fund Delisting - Negative
  NAV." Issuer notice. Status: PRIMARY. The fund "closed out its entire LCID position today at a loss that caused
  its net asset value to become negative."
- Reuters (2026-08-25), S. McGee, "US leveraged single-stock ETF boom may be cooling": Morningstar counted 63 US
  leveraged single-stock fund closures in 2026 to date against 3 in 2025. Status: SECONDARY (syndicated copy).
- ETF Action (2026-07-30): cumulative flows into levered single-stock ETFs of $35.4 billion against $29.9 billion of
  assets. Status: SECONDARY.
