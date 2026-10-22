#!/usr/bin/env python3
"""The monthly run: one row per fund as of a date, appended to ledger.csv, with the register and a manifest.

    py -I code\\product\\run_monthly.py --asof 2026-09-30                 official run (appends to ledger.csv)
    py -I code\\product\\run_monthly.py --asof 2026-10-20 --no-write      development run, prints only
    py -I code\\product\\run_monthly.py --asof 2026-09-30 --cutoff 2026-10-21T23:59:59Z

Rules
- Point in time: the run sees only raw files fetched by `cutoff` (default: now) and only sessions up to `asof`.
- Every number comes from the engine (code/engine) on total-return series (code/domain/total_return).
- Since-inception columns use the fund's whole life; mechanics columns use the trailing 252 sessions (or all, if
  fewer); `ranked` is true only with at least MIN_HISTORY sessions. `coverage` says what was computed.
- Public outputs: ledger.csv (append-only, schema_version first), register.csv, results/<YYYY-MM>/windows.csv
  (returns by calendar year and trailing window), results/manifests/<YYYY-MM>.json (input hashes and dates only).
  No price level, no daily return SERIES and no clock time appears in them (single extreme-day statistics such as
  the worst day are aggregates). The snapshot columns (AUM, one-month flow) are issuer facts read through the quote
  feed and dated by `quote_date`; the public ledger carries only numbers the engine computes from inputs it can show,
  so TradingView's own NAV-premium field stays private (user decision 2026-10-22).
- A re-run for an as-of date that already has rows is refused unless --restate is given; the new rows then carry
  `restates` = the run date of the rows they supersede, and the old rows stay.
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _paths  # noqa: E402,F401
import tv_capture as tc  # noqa: E402
import yahoo_events as ye  # noqa: E402
import quotes as qt  # noqa: E402
import register as rg  # noqa: E402
import total_return as trm  # noqa: E402
import align as al  # noqa: E402
import rates  # noqa: E402
import decompose as dc  # noqa: E402
import leverage as lv  # noqa: E402
import drag  # noqa: E402
import periods as pr  # noqa: E402
import stats as st  # noqa: E402
from captured_by import captured_by  # noqa: E402
import benchmark as bm  # noqa: E402
import port  # noqa: E402

ROOT = _paths.ROOT
SCHEMA_VERSION = 2       # v0.1.1: + vr_q10_z_under, tail_index_se_under, rel_growth_log_pct; rate on days/360
MIN_HISTORY = 126
TRAIL = 252
GUARD_TOL = 0.25

COLUMNS = [
    "schema_version", "asof", "run_date_utc", "ticker", "symbol", "issuer", "underlying", "status", "target_leverage",
    "inception_date", "expense_ratio_pct", "history_days", "coverage", "ranked",
    # the ten questions, headline columns first
    "beta_1d", "beta_5d", "r2_1d", "te_annual_pct", "capture_up_1d", "capture_down_1d",
    "cost_annual_pct", "residual_annual_pct", "residual_ci_lo_pct", "residual_ci_hi_pct", "cost_multiple",
    "vol_under_annual_pct", "vol_gk_under_annual_pct", "vol_drag_annual_pct",
    "vr_q10_under", "vr_q10_z_under", "ar1_under",
    "rebalance_pp", "compounding_pp",
    "hurdle_return_pct", "kelly_L_under", "kelly_L_ci_lo", "kelly_L_ci_hi",
    "worst_day_under_pct", "worst_day_under_hist_pct", "tail_index_under", "tail_index_se_under", "kurtosis_under", "reverse_splits",
    "max_dd_fund_pct", "current_dd_fund_pct", "underwater_days", "roll1y_min_pct", "roll1y_med_pct", "roll1y_max_pct",
    "p_beat_stock_1y", "p_beat_2x_stock_1y",
    "aum_usd_m", "adv_20d_usd_m", "aum_to_adv_under", "dist_12m_pct",
    "fund_flows_1m_usd_m",
    # detail
    "ret_1m_fund_pct", "ret_1m_under_pct", "tr_incep_fund_pct", "tr_incep_under_pct", "tr_incep_ideal_pct",
    "tr_incep_fedfunds_pct", "tr_incep_bh_pct", "cagr_fund_pct", "cagr_under_pct", "rel_growth_log_pct",
    "financing_pp", "residual_pp", "levered_bh_pp", "financing_annual_pct",
    "max_dd_under_pct", "worst_day_fund_pct", "best_day_fund_pct", "oracle_best_pct", "oracle_worst_pct",
    "beta_5d_ls", "b_wiped", "beta_spx_under", "guard_flags", "quote_date", "restates", "inputs_sha256",
]


def sha_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def month_end_before(index, asof):
    first_of_month = pd.Timestamp(asof).replace(day=1)
    prior = index[index < first_of_month]
    return prior[-1] if len(prior) else None


def session_gap(fund_df, stock_df):
    """A reason string when the fund and its stock do not share every session between the fund's first and last
    captured close (either side missing a day, or the stock's data running past the fund's last close), else None."""
    lo, hi = fund_df.index[0], fund_df.index[-1]
    s = stock_df.loc[lo:]
    fund_only = fund_df.index.difference(s.index)
    stock_only = s.index.difference(fund_df.index)
    if len(fund_only) or len(stock_only):
        first = (list(fund_only) + list(stock_only))[0]
        return (f"session mismatch: {len(fund_only)} fund-only and {len(stock_only)} stock-only sessions "
                f"(first {pd.Timestamp(first).date()}); repair the capture before this fund is computed")
    return None


def spx_returns(root=ROOT):
    """Daily S&P 500 returns from the reference copy under the active cutoff, or None when there is no copy.
    The copy's manifest record travels in attrs so the run can list it among its inputs."""
    try:
        spx = bm.spx_closes(root)
    except FileNotFoundError:                   # the column stays empty; a hash mismatch still stops the run
        return None
    r = spx.pct_change().dropna()
    r.attrs.update(record=spx.attrs["record"])
    return r


def fund_row(symbol, asof, funds, run_date, root=ROOT, reps=1000):
    f = funds.loc[symbol]
    stock_sym = f["underlying"]
    asof = pd.Timestamp(asof)
    row = {c: np.nan for c in COLUMNS}
    row.update(schema_version=SCHEMA_VERSION, asof=str(asof.date()), run_date_utc=run_date, ticker=f["ticker"],
               symbol=symbol, issuer=f["issuer"], underlying=stock_sym, status=f["status"],
               inception_date=str(f["inception_date"].date()), expense_ratio_pct=float(f["expense_ratio_pct"]),
               restates="", guard_flags=0)
    inputs = []

    try:
        fund_df = trm.fund_tr(symbol, root)
        stock_df = trm.stock_tr(stock_sym, root)
    except (FileNotFoundError, tc.NoFetchUnderCutoff) as err:     # only "nothing captured yet" is a quiet row;
        row.update(coverage=f"no raw data under the cutoff: {str(err)[:80]}", ranked=False, history_days=0)
        return row, inputs                                         # a split, hash or price failure stops the run
    fund_df = fund_df.loc[:asof]
    stock_df = stock_df.loc[:asof]
    if fund_df.empty:
        row.update(coverage="no fund data by asof", ranked=False, history_days=0)
        return row, inputs
    gap = session_gap(fund_df, stock_df)
    if gap:
        # an inner join would turn two sessions into one and invent a cost (audit 2026-10-22, D03): never for daily-reset math
        row.update(coverage=gap, ranked=False, history_days=0)
        return row, inputs
    fund_a, stock_a, info = al.align(fund_df, stock_df.loc[fund_df.index[0]:fund_df.index[-1]])
    idx = fund_a.index
    n = len(idx)
    row["history_days"] = int(n - 1)
    row["ranked"] = bool(n - 1 >= MIN_HISTORY)
    if n < 20:
        row.update(coverage="under 20 sessions")
        return row, inputs
    years_life = dc.years_in(idx)
    # leverage, rate, accrual
    L = rg.target_leverage_series(symbol, idx, root)
    row["target_leverage"] = float(L.iloc[-1])
    rate = rates.fed_funds_daily(idx)
    a = rates.accrual(idx)
    payout = (fund_a["dividend"] / fund_a["close"].shift(1)).fillna(0.0)      # the fund's cash paid out, as a fraction of prior close
    lay = dc.layers(stock_a["tr"], L, rate, a, fund_tr=fund_a["tr"], payout=payout)
    flags = al.relative_guard(lay["r_fund"].iloc[1:], lay["r_stock"].iloc[1:], L.iloc[1:], tol=GUARD_TOL)
    row["guard_flags"] = len(flags)

    # since inception
    s = dc.window_summary(lay)
    res = dc.residual_annual(lay, reps=reps)
    row.update(tr_incep_fund_pct=s["fund_pct"], tr_incep_under_pct=s["stock_pct"], tr_incep_ideal_pct=s["l1_pct"],
               tr_incep_fedfunds_pct=s["l2_pct"], tr_incep_bh_pct=s["b_pct"], compounding_pp=s["compounding_pp"],
               financing_pp=s["financing_pp"], rebalance_pp=s["rebalance_pp"], residual_pp=s["residual_pp"],
               levered_bh_pp=s["levered_bh_pp"], b_wiped=s["b_wiped"], residual_annual_pct=res["annual_pct"],
               residual_ci_lo_pct=res["ci_lo_pct"], residual_ci_hi_pct=res["ci_hi_pct"],
               financing_annual_pct=dc.financing_annual_pct(lay),
               cagr_fund_pct=100 * st.cagr(lay["L3"]), cagr_under_pct=100 * st.cagr(lay["L0"]))
    if not res["wiped"] and np.isfinite(res["annual_pct"]):
        row["cost_annual_pct"] = -res["annual_pct"]
        row["cost_multiple"] = -res["annual_pct"] / float(f["expense_ratio_pct"]) if float(f["expense_ratio_pct"]) > 0 else np.nan

    # month return
    me = month_end_before(idx, asof)
    if me is not None:
        row["ret_1m_fund_pct"] = 100 * (lay["L3"].iloc[-1] / lay["L3"][me] - 1)
        row["ret_1m_under_pct"] = 100 * (lay["L0"].iloc[-1] / lay["L0"][me] - 1)

    # trailing mechanics
    tr_rows = lay.iloc[-(TRAIL + 1):] if n > TRAIL + 1 else lay
    rf, rs = tr_rows["r_fund"].iloc[1:], tr_rows["r_stock"].iloc[1:]
    Lt = tr_rows["L"].iloc[1:]
    b = lv.ols_beta(rf, rs)
    row.update(beta_1d=b["beta"], r2_1d=b["r2"], te_annual_pct=lv.tracking_error_annual(rf, rs, Lt))
    cu, cd = lv.capture_ratios(rf, rs)
    row.update(capture_up_1d=cu, capture_down_1d=cd)
    fee_a = rates.fee_accrual(tr_rows.index, rg.expense_ratio_series(symbol, tr_rows.index, root)).iloc[1:]
    ra = tr_rows["rate_accrual"].iloc[1:]
    row["beta_5d"] = lv.exact_beta(rf, rs, k=5, rate_accrual=ra, fee_accrual=fee_a, payout=tr_rows["payout"].iloc[1:])[0]
    row["beta_5d_ls"] = lv.cubic_beta(lv.kday(rf, rs, k=5, rate_accrual=ra, fee_accrual=fee_a))[0]
    row["vol_under_annual_pct"] = drag.realized_vol(rs)
    ohlc = trm.bars(stock_sym, root).loc[tr_rows.index[1]:tr_rows.index[-1]]
    row["vol_gk_under_annual_pct"] = drag.garman_klass_vol(ohlc["open"], ohlc["high"], ohlc["low"], ohlc["close"])
    row["vol_drag_annual_pct"] = drag.exact_penalty(rs, 2.0, years=dc.years_in(tr_rows.index))[1]
    row["vr_q10_under"] = drag.variance_ratio(rs, 10)
    row["vr_q10_z_under"] = drag.variance_ratio_z(rs, 10)
    row["ar1_under"] = drag.ar1(rs)
    row["kurtosis_under"] = st.excess_kurtosis(rs)
    k_l, k_lo, k_hi = st.kelly_leverage(rs, ra.values)
    row.update(kelly_L_under=k_l, kelly_L_ci_lo=k_lo, kelly_L_ci_hi=k_hi)
    # hurdle on one footing, all over the fund's life: the exact compounding penalty of a 2x reset on the stock's
    # daily returns (not the sigma^2 law: jumps break it; engine review 2026-10-22), the mean rate, the fund's cost
    rs_life = lay["r_stock"].iloc[1:]
    pen_total, _ = drag.exact_penalty(rs_life, 2.0)
    r_life = float(lay["rate_accrual"].iloc[1:].sum() / years_life)
    if np.isfinite(pen_total) and np.isfinite(row["cost_annual_pct"]):
        row["hurdle_return_pct"] = st.hurdle_return(-pen_total / years_life, r_life, row["cost_annual_pct"] / 100)["hurdle_log_pct"]
    if float(lay["L3"].iloc[-1]) > 0:
        row["rel_growth_log_pct"] = 100 * float(np.log(lay["L3"].iloc[-1] / lay["L0"].iloc[-1])) / years_life
    spx = spx_returns(root)
    if spx is not None:
        both = pd.concat([rs.rename("s"), spx.rename("m")], axis=1, join="inner", sort=True).dropna()
        if len(both) >= 100:
            row["beta_spx_under"] = lv.ols_beta(both["s"], both["m"])["beta"]
        rec = spx.attrs["record"]
        inputs.append({"kind": "reference", "path": rec["path"], "sha256": rec["sha256"]})

    # risk and holding
    full_stock = stock_df["tr"]                                   # the stock's whole captured history to asof
    row["worst_day_under_pct"] = st.worst_day(lay["L0"])         # since the fund's inception
    row["worst_day_under_hist_pct"] = st.worst_day(full_stock)   # since the stock's listing or the 5000-bar window
    ht = st.hill_tail(full_stock.pct_change().dropna())
    row.update(tail_index_under=ht["alpha"], tail_index_se_under=ht["se"])
    row["max_dd_under_pct"] = st.max_drawdown(lay["L0"])
    row.update(max_dd_fund_pct=st.max_drawdown(lay["L3"]), current_dd_fund_pct=st.current_drawdown(lay["L3"]),
               underwater_days=st.underwater_days(lay["L3"]), worst_day_fund_pct=st.worst_day(lay["L3"]),
               best_day_fund_pct=st.best_day(lay["L3"]))
    if n > TRAIL + 1:
        r1 = pr.rolling_stats(lay["L3"], TRAIL)
        row.update(roll1y_min_pct=r1["min_pct"], roll1y_med_pct=r1["med_pct"], roll1y_max_pct=r1["max_pct"],
                   p_beat_stock_1y=pr.p_beat(lay["L3"], lay["L0"], TRAIL), p_beat_2x_stock_1y=pr.p_beat(lay["L3"], lay["L0"], TRAIL, 2.0))
    best, worst, _, _ = pr.oracle_bounds(lay["L3"])
    row.update(oracle_best_pct=best, oracle_worst_pct=worst)
    ev = rg.events(root, symbol, "reverse_split")
    row["reverse_splits"] = int((ev["date"] <= asof).sum())
    year_ago = idx[idx <= asof - pd.DateOffset(years=1)]
    if len(year_ago):
        d12 = fund_a["dividend"].loc[year_ago[-1]:].iloc[1:].sum()
        row["dist_12m_pct"] = 100 * d12 / float(fund_a["close"].iloc[-1])     # trailing yield on the as-of price

    # snapshot (quote batch) and liquidity
    try:
        qrec, q = qt.latest(root)
        if symbol in q.index:
            qs = q.loc[symbol]
            # AUM and net flow are issuer facts read through the quote feed; the NAV premium field is TradingView's
            # own calculation and is not published until the engine computes it from issuer NAV history (v0.2)
            row.update(aum_usd_m=float(qs.get("aum", np.nan)) / 1e6,
                       fund_flows_1m_usd_m=float(qs.get("fund_flows.1M", np.nan)) / 1e6, quote_date=qrec["fetched_utc"][:10])
            # the snapshot is as of its quote date, so the volume it is compared with ends on that date too
            stock_px = trm.bars(stock_sym, root).loc[:row["quote_date"]].iloc[-20:]
            adv = float((stock_px["close"] * stock_px["volume"].astype(float)).mean()) / 1e6
            row["adv_20d_usd_m"] = adv
            if adv > 0 and np.isfinite(row["aum_usd_m"]):
                row["aum_to_adv_under"] = row["aum_usd_m"] / adv
        inputs.append({"kind": "quotes", "path": qrec["path"], "sha256": qrec["sha256"]})
    except FileNotFoundError:
        pass

    # inputs used
    for sym in (symbol, stock_sym):
        for r in tc.records(sym, root):
            inputs.append({"kind": "tradingview", "path": r["path"], "sha256": r["sha256"]})
        for r in ye.records(sym, root):
            inputs.append({"kind": "yahoo", "path": r["path"], "sha256": r["sha256"]})
    row["coverage"] = "full" if n > TRAIL + 1 else f"short history: {n - 1} sessions"
    return row, inputs


def register_hashes(root=ROOT):
    out = []
    for p in sorted((Path(root) / "data" / "register").glob("*.csv")):
        out.append({"kind": "register", "path": p.name, "sha256": sha_of(p)})
    dff = port.REFERENCE / "DFF.csv"                 # public: reference/DFF.csv (FRED effective federal funds)
    out.append({"kind": "rate", "path": "reference/DFF.csv", "sha256": sha_of(dff)})
    return out


def windows_table(symbol, asof, funds, root=ROOT):
    """Per-window returns for one fund: calendar years and trailing 1/3/12 months (percent)."""
    f = funds.loc[symbol]
    try:
        fund_df = trm.fund_tr(symbol, root).loc[:asof]
        stock_df = trm.stock_tr(f["underlying"], root).loc[:asof]
    except (FileNotFoundError, tc.NoFetchUnderCutoff):      # nothing captured under the cutoff; other errors propagate
        return []
    if len(fund_df) < 20 or session_gap(fund_df, stock_df):
        return []
    fund_a, stock_a, _ = al.align(fund_df, stock_df.loc[fund_df.index[0]:fund_df.index[-1]])
    idx = fund_a.index
    payout = (fund_a["dividend"] / fund_a["close"].shift(1)).fillna(0.0)
    lay = dc.layers(stock_a["tr"], rg.target_leverage_series(symbol, idx, root), rates.fed_funds_daily(idx), rates.accrual(idx),
                    fund_tr=fund_a["tr"], payout=payout)
    sessions = trm.bars(f["underlying"], root).index          # the stock's full session calendar decides month-ends
    rows = []
    wins = [(f"Y{y}", d0, d1) for y, (d0, d1) in pr.calendar_years(idx).items() if d0 != d1]
    for label, months in (("T1M", 1), ("T3M", 3), ("T12M", 12)):
        d0, d1 = pr.trailing(idx, months, sessions=sessions)
        if d0 != d1:
            wins.append((label, d0, d1))
    for label, d0, d1 in wins:
        s = dc.window_summary(lay, d0, d1)
        rows.append({"asof": str(pd.Timestamp(asof).date()), "ticker": f["ticker"], "window": label, "start": str(d0.date()),
                     "end": str(d1.date()), "fund_pct": s["fund_pct"], "stock_pct": s["stock_pct"], "naive_pct": s["naive_pct"],
                     "ideal_pct": s["l1_pct"], "fedfunds_pct": s["l2_pct"], "bh_pct": s["b_pct"], "compounding_pp": s["compounding_pp"],
                     "rebalance_pp": s["rebalance_pp"], "residual_pp": s["residual_pp"], "L_start": s["L_start"]})
    return rows


def run(asof, root=ROOT, write=True, restate=False, cutoff=None, reps=1000, symbols=None):
    """One monthly run. The cutoff (default: the end of the run's UTC day) is activated here for every loader, so
    the Python entry point and the CLI enforce the same point-in-time contract (audit 2026-10-22, D05)."""
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cutoff = cutoff or f"{run_date}T23:59:59Z"
    with captured_by(cutoff):
        return _run(asof, root, write, restate, cutoff, reps, symbols, run_date)


def _run(asof, root, write, restate, cutoff, reps, symbols, run_date):
    funds = rg.load_funds(root)
    problems = rg.validate(root)
    if problems:
        raise ValueError("register problems: " + "; ".join(problems))
    todo = list(funds.index) if symbols is None else symbols
    rows, all_inputs, wrows = [], {}, []
    for sym in todo:
        row, inputs = fund_row(sym, asof, funds, run_date, root, reps=reps)
        rows.append(row)
        for i in inputs:
            all_inputs[(i["kind"], i["path"])] = i
        wrows += windows_table(sym, asof, funds, root)
        if row["history_days"] and np.isfinite(float(row["cost_annual_pct"])):
            print(f"  {row['ticker']:5s} sessions {row['history_days']:5d}  cost {row['cost_annual_pct']:7.2f}%/yr  beta {row['beta_1d']:.3f}  "
                  f"fund {row['tr_incep_fund_pct']:8.1f}%  stock {row['tr_incep_under_pct']:8.1f}%  {row['coverage']}")
        else:
            print(f"  {row['ticker']:5s} {row['coverage']}")
    for i in register_hashes(root):
        all_inputs[(i["kind"], i["path"])] = i
    inputs = sorted(all_inputs.values(), key=lambda i: (i["kind"], i["path"]))
    digest = hashlib.sha256("".join(i["sha256"] for i in inputs).encode()).hexdigest()
    for r in rows:
        r["inputs_sha256"] = digest
    table = pd.DataFrame(rows, columns=COLUMNS)
    wtable = pd.DataFrame(wrows)
    if write:
        asof_s = str(pd.Timestamp(asof).date())
        ledger = Path(root) / "ledger.csv"
        if ledger.exists():
            old = pd.read_csv(ledger, dtype=str)
            dup = old[(old["asof"] == asof_s) & (old["ticker"].isin(table["ticker"]))]
            if len(dup) and not restate:
                raise ValueError(f"ledger.csv already has {len(dup)} rows for {asof_s}; pass --restate to supersede them")
            if len(dup):
                table["restates"] = dup["run_date_utc"].iloc[-1]
            out = pd.concat([old, table.astype(str).replace("nan", "")], ignore_index=True)
        else:
            out = table.astype(str).replace("nan", "")
        out = out.reindex(columns=COLUMNS).fillna("")      # schema order; rows of an older schema get empty new columns
        out.to_csv(ledger, index=False, lineterminator="\n")
        rg.public_register(root).to_csv(Path(root) / "register.csv", index=False, lineterminator="\n")
        rg.public_leverage(root).to_csv(Path(root) / "register_leverage.csv", index=False, lineterminator="\n")
        month = asof_s[:7]
        rdir = Path(root) / "results" / month
        rdir.mkdir(parents=True, exist_ok=True)
        wtable.to_csv(rdir / "windows.csv", index=False, float_format="%.4f", lineterminator="\n")
        man = {"asof": asof_s, "run_date_utc": run_date, "schema_version": SCHEMA_VERSION, "funds": int(len(table)),
               "cutoff": cutoff, "inputs": inputs, "inputs_sha256": digest, "ledger_sha256": sha_of(ledger),
               "windows_sha256": sha_of(rdir / "windows.csv")}
        mdir = Path(root) / "results" / "manifests"
        mdir.mkdir(parents=True, exist_ok=True)
        (mdir / f"{month}.json").write_text(json.dumps(man, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {len(table)} rows to ledger.csv, register.csv, results/{month}/windows.csv and the manifest")
    return table, wtable


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--asof", required=True)
    ap.add_argument("--cutoff", default=None)
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--restate", action="store_true")
    ap.add_argument("--reps", type=int, default=1000)
    ap.add_argument("--symbols", nargs="*", default=None)
    a = ap.parse_args(argv)
    run(a.asof, write=not a.no_write, restate=a.restate, cutoff=a.cutoff, reps=a.reps, symbols=a.symbols)
    return 0


if __name__ == "__main__":
    sys.exit(main())
