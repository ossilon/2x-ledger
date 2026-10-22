"""The fund register: facts about each fund and stock, with sources, as hand-edited CSV tables in data/register/.

Tables (every row carries source URLs and the date the source was read):
    funds.csv              one row per fund: symbol, issuer, underlying, inception, status, expense ratio, sources
    stocks.csv             one row per underlying stock
    leverage_timeline.csv  target leverage by period: symbol, effective_from, effective_to (blank = open), target_leverage
    expense_timeline.csv   total expense ratio by period
    events.csv             dated events: inception, forward_split, reverse_split, distribution, leverage_change,
                           name_change, closure, swap_termination (value = ratio "10:1" / "1:10", amount, or text)

Rules: a fund's leverage timeline must start at its inception and have no gaps or overlaps; dates are ISO; status
is live or closed; nothing here is a price. The public register.csv is rendered from these tables (public columns
only) by public_register(). Issuer names and fund-specific facts live ONLY here (lab-standard: instrument adapter).
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _paths  # noqa: E402,F401

ROOT = _paths.ROOT
EVENT_TYPES = {"inception", "forward_split", "reverse_split", "distribution", "leverage_change", "name_change",
               "closure", "swap_termination", "expense_change", "note"}
PUBLIC_FUND_COLS = ["symbol", "ticker", "exchange", "issuer", "fund_name", "underlying", "inception_date", "status",
                    "close_date", "target_leverage_now", "expense_ratio_pct", "expense_asof", "distributions_url",
                    "inception_source", "captured_date"]


def register_dir(root=ROOT):
    return Path(root) / "data" / "register"


def _read(name, root=ROOT, dates=()):
    p = register_dir(root) / name
    if not p.exists():
        raise FileNotFoundError(f"register table missing: {p}")
    df = pd.read_csv(p, dtype=str, keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    for c in df.columns:
        df[c] = df[c].str.strip()
    for c in dates:
        if c in df:
            df[c] = pd.to_datetime(df[c].replace("", pd.NA), format="%Y-%m-%d", errors="raise")
    return df


def load_funds(root=ROOT):
    df = _read("funds.csv", root, dates=("inception_date", "close_date"))
    if df["symbol"].duplicated().any():
        raise ValueError(f"duplicate fund symbols: {sorted(df['symbol'][df['symbol'].duplicated()])}")
    bad = df[~df["status"].isin(["live", "closed"])]
    if len(bad):
        raise ValueError(f"status must be live or closed: {bad['symbol'].tolist()}")
    return df.set_index("symbol", drop=False)


def load_stocks(root=ROOT):
    df = _read("stocks.csv", root)
    return df.set_index("symbol", drop=False)


def leverage_timeline(root=ROOT):
    df = _read("leverage_timeline.csv", root, dates=("effective_from", "effective_to"))
    df["target_leverage"] = df["target_leverage"].astype(float)
    return df.sort_values(["symbol", "effective_from"]).reset_index(drop=True)


def expense_timeline(root=ROOT):
    df = _read("expense_timeline.csv", root, dates=("effective_from", "effective_to"))
    df["expense_total_pct"] = df["expense_total_pct"].astype(float)
    return df.sort_values(["symbol", "effective_from"]).reset_index(drop=True)


def events(root=ROOT, symbol=None, kind=None):
    df = _read("events.csv", root, dates=("date",))
    unknown = set(df["type"]) - EVENT_TYPES
    if unknown:
        raise ValueError(f"unknown event types {sorted(unknown)}; allowed {sorted(EVENT_TYPES)}")
    if symbol is not None:
        df = df[df["symbol"] == symbol]
    if kind is not None:
        df = df[df["type"] == kind]
    return df.sort_values(["symbol", "date"]).reset_index(drop=True)


def check_timeline(tl, funds, what="leverage"):
    """Every fund's periods start at inception, touch each other, and only the last one is open-ended."""
    problems = []
    for sym, f in funds.iterrows():
        rows = tl[tl["symbol"] == sym].sort_values("effective_from")
        if rows.empty:
            problems.append(f"{sym}: no {what} period")
            continue
        if rows["effective_from"].iloc[0] != f["inception_date"]:
            problems.append(f"{sym}: first {what} period starts {rows['effective_from'].iloc[0].date()}, "
                            f"inception is {f['inception_date'].date()}")
        for i in range(len(rows) - 1):
            end, nxt = rows["effective_to"].iloc[i], rows["effective_from"].iloc[i + 1]
            if pd.isna(end) or end != nxt:
                problems.append(f"{sym}: {what} period {i + 1} ends {end} but the next starts {nxt.date()}")
        if not pd.isna(rows["effective_to"].iloc[-1]) and f["status"] == "live":
            problems.append(f"{sym}: last {what} period is closed but the fund is live")
    return problems


def target_leverage_series(symbol, index, root=ROOT):
    """Target leverage on each date of `index` (a DatetimeIndex) from the leverage timeline; raises off the timeline."""
    rows = leverage_timeline(root)
    rows = rows[rows["symbol"] == symbol]
    if rows.empty:
        raise KeyError(f"{symbol}: no leverage timeline")
    out = pd.Series(float("nan"), index=index, name="target_leverage")
    for _, r in rows.iterrows():
        end = r["effective_to"]
        mask = (index >= r["effective_from"]) & ((index < end) if not pd.isna(end) else True)
        out[mask] = r["target_leverage"]
    if out.isna().any():
        first = out.index[out.isna()][0]
        raise ValueError(f"{symbol}: no target leverage on {first.date()} (timeline starts "
                         f"{rows['effective_from'].min().date()})")
    return out


def expense_ratio_series(symbol, index, root=ROOT):
    """Total expense ratio (percent a year) on each date of `index` from the expense timeline; raises off it.

    v0.1.0 used the latest ratio for the whole trailing window; 11 pilot funds changed fees inside it (engine
    review 2026-10-22, F6). The effect on the leverage fit is below 0.001, but the timeline is the record.
    """
    rows = expense_timeline(root)
    rows = rows[rows["symbol"] == symbol]
    if rows.empty:
        raise KeyError(f"{symbol}: no expense timeline")
    out = pd.Series(float("nan"), index=index, name="expense_total_pct")
    for _, r in rows.iterrows():
        end = r["effective_to"]
        mask = (index >= r["effective_from"]) & ((index < end) if not pd.isna(end) else True)
        out[mask] = r["expense_total_pct"]
    if out.isna().any():
        first = out.index[out.isna()][0]
        raise ValueError(f"{symbol}: no expense ratio on {first.date()} (timeline starts {rows['effective_from'].min().date()})")
    return out


def public_leverage(root=ROOT):
    """The public register_leverage.csv frame: dated target-leverage periods per fund with their sources.

    Facts, not prices: the forward verdicts need dated leverage events to apply protocol P1's exclusion rule
    (audit 2026-10-22, D01)."""
    tl = leverage_timeline(root).copy()
    funds = load_funds(root)
    tl["ticker"] = tl["symbol"].map(funds["ticker"])
    for c in ("effective_from", "effective_to"):
        tl[c] = tl[c].dt.strftime("%Y-%m-%d").fillna("")
    cols = ["symbol", "ticker", "target_leverage", "effective_from", "effective_to"] + [c for c in ("source",) if c in tl.columns]
    return tl[cols].sort_values(["ticker", "effective_from"]).reset_index(drop=True)


def validate(root=ROOT):
    """All register checks; returns a list of problems (empty = clean)."""
    funds = load_funds(root)
    problems = check_timeline(leverage_timeline(root), funds, "leverage")
    problems += check_timeline(expense_timeline(root), funds, "expense")
    ev = events(root)
    for sym in funds.index:
        inc = ev[(ev["symbol"] == sym) & (ev["type"] == "inception")]
        if inc.empty:
            problems.append(f"{sym}: no inception event")
        elif inc["date"].iloc[0] != funds.at[sym, "inception_date"]:
            problems.append(f"{sym}: inception event {inc['date'].iloc[0].date()} differs from funds.csv")
        if funds.at[sym, "status"] == "closed":
            if pd.isna(funds.at[sym, "close_date"]):
                problems.append(f"{sym}: closed without a close_date")
            if ev[(ev["symbol"] == sym) & (ev["type"] == "closure")].empty:
                problems.append(f"{sym}: closed without a closure event")
    stocks = load_stocks(root)
    missing = sorted(set(funds["underlying"]) - set(stocks.index))
    if missing:
        problems.append(f"underlying stocks missing from stocks.csv: {missing}")
    return problems


def public_register(root=ROOT):
    """The public register.csv frame: public columns only, one row per fund, current target leverage filled in."""
    funds = load_funds(root).copy()
    tl = leverage_timeline(root)
    now_l = tl[tl["effective_to"].isna()].set_index("symbol")["target_leverage"]
    funds["target_leverage_now"] = funds["symbol"].map(now_l)
    for c in ("inception_date", "close_date"):
        funds[c] = funds[c].dt.strftime("%Y-%m-%d").fillna("")
    return funds[PUBLIC_FUND_COLS].reset_index(drop=True)


if __name__ == "__main__":
    probs = validate()
    print("\n".join(probs) if probs else "register: 0 problem(s)")
    print(public_register().to_string(index=False))
