# Assumptions

Every input the Ledger uses, with its status and source. The status words:

- VERIFIED: read in a primary source.
- MEASURED: computed from data in this project.
- ASSUMED: a choice, with the reason.
- DECIDED: a user decision.
- OPEN: not yet settled.

## 1. Prices

| Input | Value | Status | Source and date |
|---|---|---|---|
| Fund and stock daily bars | TradingView MCP, interval 1D, regular session, split-adjusted only. | VERIFIED | The notice on every reply, read 2026-10-21. |
| Fund dividends, distributions and splits | Yahoo Finance chart events. The register cross-checks each fund's amounts against the issuer page before use. | VERIFIED as a source | `data/raw/yahoo`, 2026-10-21. |
| Stock history older than the 5000-bar window | Yahoo adjusted close. TradingView paging comes in v0.3. | ASSUMED for v0.1 | `stocks.csv` marks `complete_history`. |
| Last bar of a reply | The build drops a bar dated on the fetch day (New York), because the bar may still form. | ASSUMED | `tv_capture.build`. |
| Feed agreement | The TradingView close and the Yahoo close agree within 0.1 percent on 99.9 percent of common days for the 13 stocks. The exceptions are old half-day or pre-merger sessions before any fund existed. | MEASURED 2026-10-21 | `yahoo_events.crosscheck`. |
| Total-return convention | The engine reinvests a cash payment D with ex-date t at the close of t: `r_t = (P_t + D) / P_{t-1} - 1`. This is the CRSP definition, and Bessembinder's data uses it. Yahoo's adjusted close implies `P_t / (P_{t-1} - D) - 1` instead. The two differ on the ex-date by `-(D / P_{t-1}) x r_yahoo`, so the gap matters only when the payout is large and the price moves. MSTX on 2024-12-31 (payment 27 percent of price, price down 34 percent): the holder's return was -6.44 percent, Yahoo's -8.84 percent. The LETF kit's MSTX late-2024 cost figure (99.8 percent) carries that approximation. On the same constant-2x definition and this project's data, the figure is 90.7 percent. With the fund's actual 1.75x target over that window, this engine's cost is 43.8 percent. | VERIFIED (derivation) and MEASURED 2026-10-22 | `total_return.tr_index`; the private cross-check `scripts/continuity_pin_local.py`. |
| Payouts in the frictionless layers | On an ex-date the fund pays D out and levers the remaining NAV. The frictionless layers L1 and L2 do the same: the daily gross return is `(1 - d_t)(1 + L r_t - ...) + d_t` with `d_t = D_t / P_{t-1}`. Without this term, the layers would lever cash the holder had already received. On MSTX 2024-12-31 the difference was +2.4 points, a false gain in the residual. Two consequences follow. The payout day's cash effect now sits in `compounding_pp` and `rebalance_pp`. A fund that keeps leverage on its pre-distribution NAV shows a real deviation in its residual. PLTU on 2025-12-10 ran at about 2.4x its ex-distribution NAV. So PLTU's cost is 6.6 percent, not 7.2. The same payout term is in `leverage.exact_beta`. | VERIFIED (mechanics; audit 2026-10-22) | `decompose.layers(payout=...)`. |
| Snapshot columns | AUM and one-month net flow are issuer facts read through TradingView's quote feed, as of `quote_date` (the capture after month-end), not the as-of date. `aum_to_adv_under` compares them with the stock's 20-day dollar volume that ends on the same quote date. The NAV premium field is TradingView's own calculation from two public inputs. The ledger does NOT publish it. The ledger carries only numbers this engine computes from inputs it can show. A premium computed from issuer NAV history is a v0.2 item. The register (inception, leverage, expense timelines) is a current-knowledge table, not point in time; a `known_from` column is a v0.2 item. | DECIDED by the user 2026-10-22 | `run_monthly.fund_row`. |
| No timing-covariance column | Returns alone do not identify Bianchi and Goldberg's `Cov(lambda, r)`. A constant daily cost c gives `lambda = L - c / r` and a covariance of `-c`. Also, `Cov(lambda, r) = E[(lambda - L) r]` is the mean daily gap itself. So the fund's cost and any leverage-return co-movement are one observable. The ledger publishes the capture ratios (costs included) and the residual instead. | VERIFIED (derivation and planted test, audit finding 4, 2026-10-22) | `leverage.capture_ratios`, `tests/test_engine_leverage.py`. |
| Buy-and-hold benchmark across a leverage change | B borrows once per target regime. At each change of the register's target leverage, the position re-levers to the new target (the investor re-borrows once). The benchmark goes to zero, and stays there, if its value reaches zero. The ledger's since-inception `rebalance_pp` therefore spans regimes; Bessembinder's figures are per window. | ASSUMED (choice, audit 2026-10-22) | `decompose.bh_index`. |
| Register distribution amounts | Issuer amounts are nominal per share. Before use, the build moves them onto the split-adjusted basis of the prices. The factor is the cumulative factor of later splits (1:10 reverse x10; 10:1 forward /10). | VERIFIED (MSTX 2024-12-31: $14.4276 nominal = $144.28 adjusted, equal to Yahoo's event) | `total_return.split_factor_after`. |

## 2. Reference rate and benchmark

| Input | Value | Status | Source |
|---|---|---|---|
| Benchmark interest rate | Effective federal funds (FRED DFF), known before the day (`port.rate_on`, lag 1). | VERIFIED | `reference/DFF.csv` (public), 1954-07-01 to 2026-10-08, downloaded from FRED. |
| Accrual | Calendar days / 365. | ASSUMED, same as the LETF kit | `port.accrual_fraction`. |
| S&P 500 close (for `beta_spx_under` only) | The daily close of the price index, from a private copy in `data/reference/`. The manifest records the fetch time of the bars (2026-10-12). A run under an earlier cutoff leaves the column empty. | VERIFIED (a copy of a TradingView series, cross-checked in the author's price library) | `code/domain/benchmark.py`. |

## 2a. Code taken from the author's other kits

The Ledger's rule is "import, never copy", so one kit's fix reaches every project. A public repository cannot import
private siblings. So the few helpers this project needs live in `code/port.py`, each with its source named. A
git-ignored cross-check (`tests/port_local.py`) compares every copy with its original whenever the tests run on the
author's machine. A change on either side fails the tests. Status: VERIFIED (cross-check 2026-10-22).

## 3. Fund facts

See `data/register/` (private tables with source URLs) and the public `register.csv`. Two items carry the mark APPROX
in the register. The exact day of the 2024 leverage changes: the issuers wrote "on or about". The expense ratio
between launch and the latest prospectus, where only the launch and current values are known.

## 4. Bar fixes

One bad bar is known in the TradingView feed. SMCX on 2024-11-11 carries the pre-split price (close 1248.00). The bars
around it and Yahoo (62.40) carry the adjustment for the 1:20 reverse split of 2024-11-18. The build scales that
day's open, high, low and close by 0.05 from `data/register/bar_fixes.csv`. It lists the fix in the series metadata
and leaves the raw file unchanged.

Status: MEASURED (cross-check 2026-10-21). Every other common day of the 19 fund series agrees with Yahoo within
0.01 percent.

## 5. Open items

- NVDL forward split 6:1 on 2024-03-13: resolved on 2026-10-22 with the GraniteShares 497 supplement of
  2024-02-28 (record 2024-03-11, split-adjusted trading 2024-03-13).
- MSTU distribution on 2026-08-25: the issuer page says $0.0279, Yahoo says $0.288. The 1:10 reverse split took effect
  the day before, so the share basis of the issuer figure is unclear. The ex-date price gap supports Yahoo's amount
  (audit 2026-10-22). The build uses Yahoo's amount until the issuer confirms the basis. The register row is
  UNVERIFIED.
- Swap counterparties for the Direxion funds other than AAPU and AMZU: the SEC schedule of investments did not
  load in full.
