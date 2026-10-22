# Changelog

This project uses semantic versioning. Features raise the minor version; fixes raise the patch version.

## 0.1.1 (2026-10-22)

Two reviews of v0.1.0 on 2026-10-22 drove this release: the author's own engine review and an independent audit by
another AI model (GPT Astra). Every audit finding reproduced here on fresh fixtures before it entered this list.
The run appends restated rows for 2026-09-30; the old rows stay, and the new rows carry `restates`. Schema
version 2.

Engine (numbers change):

- Day count: the reference rate accrues on calendar days / 360, the money-market basis of fed funds. The ISDA
  floating rate option is ACT/360 (dealer disclosure read 2026-10-22). v0.1.0 used 365. Every cost falls by about
  0.05 points a year.
- Cost interval: mean plus or minus t(k-1) times the bootstrap standard error, with k the number of 21-session
  blocks. In simulation the percentile interval covered 0.85 to 0.94 instead of 0.95. The t interval covers 0.955
  to 0.968.
- Hurdle: the exact compounding penalty of a 2x reset over the fund's life replaces the sigma-squared law. SMCX's
  hurdle rises from 137 to 152. PLTU's falls from 53.4 to 50.6 and agrees with the realized outcome. New column
  `rel_growth_log_pct`: the fund's log growth minus the stock's, per year.
- `oracle_worst_pct` includes the zero-length hold, so it equals the maximum drawdown and never turns positive.
- `exact_beta` computes the feasible interval of beta first, scans a grid, then refines. It returns NaN when two
  betas fit the k-day windows equally. v0.1.0 could miss a feasible beta, and it picked one of two equal fits.
- Kelly leverage: the exact discrete maximizer of mean log growth replaces the ratio mean / variance. The two
  differ by less than 0.2 on the pilot.
- New columns `vr_q10_z_under` (Lo-MacKinlay heteroskedasticity-robust z of the variance ratio) and
  `tail_index_se_under` (Hill standard error).
- `financing_annual_pct` is the log rate 100 ln(L1 / L2) / years, on the same footing as the residual.
- The exact penalty and the trailing penalty column annualize on calendar years like the residual.
- The trailing leverage fit uses the expense timeline instead of the latest expense ratio.

Data and point in time (no number change):

- A fund whose sessions do not match its stock's gets a coverage reason and no numbers. An inner join would turn
  two sessions into one and invent a cost. The check found no such fund in the September rows.
- Month-end detection uses the stock's full session calendar, so a month that ends on an exchange holiday anchors
  correctly.
- `run()` activates the cutoff for every loader. v0.1.0 did so only in the command line. The default cutoff is the
  end of the run's UTC day, and the manifest records it.
- Reference copies (the S&P 500 close) take their file name from their content hash, so an earlier copy stays
  replayable after a later import.

Protocol:

- `code/forward/verdicts.py` enforces P1. It applies the frozen universe, closures from `register.csv` and leverage
  changes from the new public `register_leverage.csv`. A live fund without its input gives "unresolved". The
  evidence names every exclusion. Fixtures cover closure, new listing, change-and-revert and missing data.
- Protocol P2 joins the hypothesis ledger as a new entry, and no entry changes. It records the NVDX gap correction (3.2,
  not 3.4), the review window's 22-day overlap with the freeze, the executable eligibility rules and the day-count
  change.

Documents and guards:

- The covariance identity in ASSUMPTIONS, CANON and the leverage module now reads
  Cov(lambda, r) = E[(lambda - L) r] - (E[lambda] - L) E[r]. v0.1.0 dropped the mean term.
- README templates have states for missing values, ties and margins. The tracking reading gives the slope and the
  tracking error and never claims an exact 2x. The trend reading follows the robust z. The Kelly reading counts
  the intervals that exclude 2. The hurdle table marks funds that ran below 2x.
- Text: point-in-time wording (capture cutoff, not knowledge date) and restated FINDINGS numbers with dated
  corrections. Also the CANON bracket sign, dictionary entries for every changed or new column, and
  `requirements.txt`.
- Guards: the scanner flags dated rows with one decimal; the linter skips only quotations of at most 15 words.
- `tests/test_scan_identifiers.py`: a public clone has no private term list, so the test runs the generic checks
  without it. The v0.1.0 tag's public suite showed that one failure; main fixed it before this release.

## 0.1.0 (2026-10-22)

The first public release: the pilot of 21 funds, the engine, the tests, the frozen hypotheses and the first ledger
row set (as of 2026-09-30). The steps below built it.

### S0: scaffold, capture, register, canon

- Project layout with flat code folders (engine, domain, capture, forward, product), a test harness and a runner.
- Capture store for TradingView daily bars: byte-exact raw files, a SHA-256 manifest, a summary checksum, split
  detection, a point-in-time cutoff (`captured_by`). Each run rebuilds the series from the raw files.
- Yahoo event fetcher (dividends, distributions, splits, adjusted closes) and a cross-check of TradingView closes
  against Yahoo closes.
- Monthly quote snapshot store (expense ratio, AUM, NAV premium, flows).
- Fund register: 21 pilot funds, 13 stocks, leverage and expense timelines, dated events, one bar fix. Each row
  names its source and access date.
- `docs/CANON.md`: the research the method rests on, with the read status of each source.

### S1: engine and synthetic tests

- `code/engine/decompose.py`: the layers L0 (stock), L1 (frictionless daily reset), L2 (fed funds on the borrowed
  turn), B (levered buy-and-hold) and L3 (fund). Window summaries in percentage points. The yearly log residual
  with a block-bootstrap interval. A fund at zero stays at zero.
- `code/engine/leverage.py`: 1-day OLS slope and R-squared, tracking error, up-day and down-day capture,
  non-overlapping k-day windows, and the Leung-Santoli (2016) one-parameter leverage estimator.
- `code/engine/drag.py`: realized and Garman-Klass volatility, the exact daily compounding penalty and the
  sigma-squared law, the Lo-MacKinlay variance ratio, lag-one autocorrelation.
- `code/engine/periods.py`: calendar years, trailing windows, benchmark drawdown episodes, rolling holding returns,
  the share of windows above a benchmark, perfect-timing bounds.
- `code/engine/stats.py`: CAGR, drawdowns, underwater days, hurdle return, Kelly leverage with an interval, Hill tail
  index, excess kurtosis, Bowley skew.
- `code/domain/`: reference rate and accrual (LETF kit conventions), total return from closes plus Yahoo events
  with VERIFIED register overrides, alignment and the relative split guard.
- Tests: 159 checks in 8 modules, planted answers and closed forms, 0 failures. `scripts/smoke_fund.py` prints the
  ten questions for one fund from the captured data.

### S2: pilot run, continuity pin, pins

- `code/product/run_monthly.py`: one row per fund as of a date, appended to `ledger.csv`; `register.csv`;
  `results/<YYYY-MM>/windows.csv` (returns by calendar year and trailing window). `results/manifests/<YYYY-MM>.json`
  holds input hashes and dates only. Point in time through `--cutoff`.
- First pilot run as of 2026-09-30 on 21 funds (cutoff 2026-10-21).
- A private cross-check script (`continuity_pin_local.py`, outside the repository) recomputes the LETF kit's audited all-in costs for MSTU and MSTX by half-year. Every
  closed window agrees to 0.00 points. The exception is MSTX late 2024. The kit's Yahoo-based figure carries Yahoo's
  ex-date approximation on a distribution of 27 percent of the price (`ASSUMPTIONS.md`, section 1).
- The build converts register distribution amounts from the issuer's nominal basis to the split-adjusted basis of
  the prices by the cumulative factor of later splits.
- `scripts/make_pins.py` and `tests/test_pins.py`: private real-data pins (rounded to 6 decimals) recomputed for
  three funds. A new pin needs an explicit flag.

### S2 audit fixes (independent audit on Opus 5.5; findings 1-9 closed)

- Calendar-year and trailing windows now start at the last session before the window. So the first session's
  return belongs to the window (TSLL 2023: 139.7 percent, not 194.3).
- The buy-and-hold benchmark B re-levers at each change of target leverage. It goes to zero, and stays there, when
  its value reaches zero. The sign of `rebalance_pp` flips for NVDU and AAPU, and B is -100 percent for AMDL and SMCX.
- The frictionless layers pay out the fund's distributions on the ex-date and lever the rest (`payout`). MSTX's
  cost rises from 31.4 to 32.6 percent a year once a 2.4-point false gain on 2024-12-31 leaves the residual.
- The timing-covariance column is gone: a constant cost and a leverage-return covariance are one observable
  (`ASSUMPTIONS.md`, section 1).
- `beta_5d` now uses the exact discrete one-parameter fit; the book's small-move estimator stays as `beta_5d_ls`.
- Point in time: each run rebuilds the series from raw files under the cutoff; `ingest` requires the fetch time.
- `dist_12m_pct` is a trailing yield on the as-of price. `worst_day_under_pct` counts from the fund's inception
  and `worst_day_under_hist_pct` from the stock's available history. The hurdle uses the fund-life variance, the
  mean rate and the cost together.
- The register drops the MSTU 2026-08-25 distribution override (share basis unclear); Yahoo's amount stands.
- Pins regenerated (`--repin`: the audit fixes above).
- Verification pass (same auditor): trailing windows on a month-end as-of date now anchor at the prior month-end,
  so T1M equals the ledger's month return. Only "nothing captured under the cutoff" yields a quiet row; every other
  build error stops the run. `exact_beta` carries the payout term and returns NaN on a -100 percent fund day.
  `aum_to_adv_under` compares the snapshot with the volume that ends on the snapshot's own date. Pins regenerated.
- Third pass: the month-end test in `periods.trailing` now asks whether the next business day falls in the next
  month. The earlier test was always true on an index cut at the as-of date. 193 checks, 0 failures.
- Publication decision (user, 2026-10-22): the public ledger keeps AUM and one-month flow (issuer facts, attributed
  to the quote feed and dated). It does not carry the NAV premium, which is the provider's own calculation. A
  premium computed from issuer NAV history comes in v0.2.

### S3: freeze and ship

- The project runs on its own. The helpers it took from the author's private sibling kits now live in
  `code/port.py` with their sources named. From the price library: the bar checks and the bar frame. From the LETF
  kit: the rate loader, the accrual, the daily-reset synthetic fund, the underwater spells and the Yahoo chart
  fetch. A git-ignored cross-check (`tests/port_local.py`) compares each copy with its original on the author's
  machine. Every module imports with the sibling kits blocked.
- `reference/DFF.csv`: the FRED effective federal funds series ships in the repository (public domain, to
  2026-10-08). The S&P 500 close for `beta_spx_under` moves to a private reference copy (`data/reference/`,
  `code/domain/benchmark.py`) with a fetch stamp, so the point-in-time rule covers it too.
- The pilot run as of 2026-09-30 ran again after the port under the same cutoff. Every number is identical, column
  by column. Only the input list changed: it now names `reference/DFF.csv` and the S&P 500 copy. Pins regenerated
  for the new input hash (`--repin`: inputs list; metrics unchanged).
- Hypotheses on record: `code/forward/ledger.py` (hash-chained, append-only), protocol P1, hypotheses H1 to H4,
  two parked items, frozen 2026-10-22 before the first public commit. `code/forward/verdicts.py` computes the
  verdicts from the public files; `tests/test_verdicts.py` checks each rule on planted tables.
- Documents: `README.md` with the ten questions (rendered by `code/product/render.py` from `ledger.csv`),
  `DATA_DICTIONARY.md`, `FINDINGS.md`, `HYPOTHESES.md`, `docs/GLOSSARY.md`, `docs/STYLE.md`, `docs/learn/`.
- Guards: `scripts/ste_check.py` (ASD-STE100 lint of the public text) and `scripts/scan_identifiers.py` (personal
  terms, secrets, clock times, data files). Both have tests. Both stand at 0 problems at release.
- `CITATION.cff`, MIT license, first commit, tag v0.1.0.
