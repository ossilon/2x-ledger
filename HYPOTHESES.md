# Hypotheses on record

A script (`code/forward/ledger.py`) makes this page from `forward/hypotheses.jsonl`. Do not edit it by hand.
Chain check: **chain intact** (7 entries). Each entry carries the hash of the entry before it. The git history shows when each entry went on record.

## Protocol P1 (on record 2026-10-22)

- Universe: the 21 funds in register.csv on 2026-10-22. A fund that closes before its review date leaves the test, and the verdict names it. A test that does not reach its minimum sample reads inconclusive.
- Data: the public files of the run as of 2027-09-30 (the review run). These are the ledger.csv rows with asof 2027-09-30 and the T12M rows of results/2027-09/windows.csv. The engine of v0.1.0 defines every column (DATA_DICTIONARY.md). If a later version changes a definition, the verdict uses the v0.1.0 code on the review data.
- Window cost: for a T12M row, cost = -ln((1 + fund_pct / 100) / (1 + fedfunds_pct / 100)) x 365 / days x 100. Days are the calendar days in the window. The unit is percent a year. This is the fund's all-in cost beyond fed funds on one borrowed turn over the window.
- Ranked funds: only ledger rows with ranked = true count (at least 126 sessions of history).
- Rank correlation: Spearman, with average ranks for ties, computed by pandas. The band decides; no p-value does.
- Verdicts: code/forward/verdicts.py computes every verdict from these rules and the review files. No judgment overrides it. Results read pass, fail, inconclusive (minimum sample not reached) or void (a fund the test needs has closed).
- Multiple tests: four tests. One failure by chance is plausible. A failure marks a lead to investigate, not proof on its own.
- Before the freeze: the run as of 2026-09-30 (windows 2025-09-30 to 2026-09-30) shaped the bands below. It tests nothing.
- Void events: if a fund's target leverage in the register changes between 2026-09-30 and 2027-09-30, that fund leaves H2 and H4. The verdict names it.

## Hypotheses

| ID | On record | Claim | Review on | Status |
|---|---|---|---|---|
| H1 | 2026-10-22 | The cost of a fund rises with the volatility of its stock. | 2027-10-15 | open |
| H2 | 2026-10-22 | The issuer, not the stock, sets the gap in cost. The T-Rex fund costs at least 1.5 points a year more than every other fund on the same stock. | 2027-10-15 | open |
| H3 | 2026-10-22 | Over one year, most funds do not deliver twice the return of their stock, even when the stock rises. | 2027-10-15 | open |
| H4 | 2026-10-22 | The funds on MSTR and SMCI stay the most expensive: each costs more than 20 percent a year beyond fed funds. | 2027-10-15 | open |

### H1: The cost of a fund rises with the volatility of its stock.

- **Test:** On the review run: the Spearman rank correlation across ranked funds between the T12M window cost and vol_under_annual_pct. The cost window is 2026-09-30 to 2027-09-30. The volatility is the stock's realized volatility over the trailing 252 sessions.
- **Pass if:** The correlation is at least 0.5, with at least 15 ranked funds. Inconclusive below 15 funds.
- **If it fails:** The issuer's financing terms set the cost, not the risk of the stock. The cross-section of costs then needs an issuer explanation, and the hurdle table changes shape.
- **Before the freeze (shaped the band, tests nothing):** On the window 2025-09-30 to 2026-09-30, the correlation was 0.76 over 21 funds. With the since-inception cost it was 0.81. The correlation of cost with the stated expense ratio was 0.44.
- **Review on:** 2027-10-15

### H2: The issuer, not the stock, sets the gap in cost. The T-Rex fund costs at least 1.5 points a year more than every other fund on the same stock.

- **Test:** On the review run, in the NVDA group (NVDL, NVDU, NVDX, NVDG) and the TSLA group (TSLL, TSLT, TSLG). The statistic is the T12M window cost of the T-Rex fund (NVDX, TSLT) minus the highest T12M window cost of the other funds.
- **Pass if:** The gap is at least 1.5 points a year in both groups. Void for a group whose T-Rex fund, or all of whose other funds, have closed.
- **If it fails:** Cost differences between issuers do not persist from one year to the next. A fund's past cost then says little about its next year. The issuer league table needs a longer sample before anyone acts on it.
- **Before the freeze (shaped the band, tests nothing):** Window to 2026-09-30: NVDX 12.1 percent a year against 7.7 for the next fund (gap 4.5). TSLT 11.5 against 8.7 (gap 2.8). Since inception: gaps of 3.4 and 2.8.
- **Review on:** 2027-10-15

### H3: Over one year, most funds do not deliver twice the return of their stock, even when the stock rises.

- **Test:** On the review run, take the ranked funds whose stock's T12M total return (stock_pct) is positive. The statistic is the share of them whose T12M fund_pct is above 2 x stock_pct.
- **Pass if:** The share is at most 0.5, with at least 8 such funds. Inconclusive below 8 funds.
- **If it fails:** The year trended strongly enough that compounding beat the costs for most funds. Bessembinder (2026) shows the rebalancing effect can be positive when returns trend. vr_q10_under then sits above 1 for most stocks.
- **Before the freeze (shaped the band, tests nothing):** On the window to 2026-09-30, 12 stocks rose. One fund of those 12 (AMDL) returned more than twice its stock, a share of 0.08. In calendar 2024, 5 of 20 funds (0.25) returned more than twice their stock, over stocks that rose and stocks that fell.
- **Review on:** 2027-10-15

### H4: The funds on MSTR and SMCI stay the most expensive: each costs more than 20 percent a year beyond fed funds.

- **Test:** On the review run, the T12M window cost of MSTU, MSTX and SMCX.
- **Pass if:** Each fund that still trades costs more than 20 percent a year. A closed fund leaves the test, and the verdict names it. Void if all three have closed.
- **If it fails:** The financing terms of these funds improved, or swap capacity returned. The cost of about 30 percent a year measured for 2024 to 2026 was an episode, not a feature of the funds.
- **Before the freeze (shaped the band, tests nothing):** On the window to 2026-09-30: MSTU 28.1, MSTX 29.1, SMCX 28.8 percent a year. Since inception: 30.2, 32.6, 30.4. The next most expensive fund (ASTX) cost 15.0 on the window.
- **Review on:** 2027-10-15

## Parked (on record, not yet testable)

| ID | On record | Claim | Why parked | Better test |
|---|---|---|---|---|
| H5 | 2026-10-22 | The pilot funds' mean monthly shortfall against levered buy-and-hold sits in Bessembinder's band for long 2x funds: 0.4 to 1.5 percent a month. | The engine measures the shortfall per window, not as a monthly series per fund. The monthly series comes with the strategy panel of v0.2. | In v0.2, compute fund minus B month by month for every fund and compare the pooled mean with the published band. |
| H6 | 2026-10-22 | Funds with large assets against the stock's daily dollar volume (CONL, MSTU, MSTX) show a reversal after the close. Part of each day's move reverses the next morning. | The test needs the open and close of each session and the fund's assets by day. It also needs a rule for the reversal statistic, which v0.1 does not define. | In v0.2, define the close-to-open reversal share as in Zhao (2026). Test it on the three funds against the funds with small assets. |
