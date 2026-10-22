#!/usr/bin/env python3
"""Capture store for TradingView daily bars (replies of the MCP tool mcp-tv-get-ohlcv).

Each reply is saved as it arrived under data/raw/tradingview/<UTC date>/ and listed in
data/raw/tradingview/manifest.jsonl with its SHA-256 hash and fetch time. Nothing in raw/ is ever edited.
The daily series in data/series/<SYMBOL>.csv are rebuilt from raw at every run.

Commands (run from twox_ledger/):
    py -I code\\capture\\tv_capture.py plan                       symbols to fetch now, with the bar count each needs
    py -I code\\capture\\tv_capture.py ingest REPLY.json [...]     [--fetched-utc 2026-10-22T20:15:00Z]
    py -I code\\capture\\tv_capture.py build [--all | SYMBOL ...]  [--cutoff 2026-10-31T23:59:59Z]
    py -I code\\capture\\tv_capture.py status

Checks on ingest (a reply that fails any check is not stored):
- success true, interval 1D, bars in rows format, at least one bar;
- the bars reproduce the MCP's own summary (count, first and last time, first open, last close, high, low,
  total volume): a mismatch means the file is not a faithful copy of the reply (port.verify_summary).
  Known limit: the summary covers the ends, the extremes and total volume, so a wrong interior price with its
  volume intact passes. The overlap check at build time (prices within PRICE_TOL against the previous fetch) and
  the relative split guard in the engine are the second line of defence;
- prices positive and inside the high-low range; one bar per session date; no weekend dates.

Rules on build:
- a series starts from the latest FULL fetch (has_more false: the reply reaches back to the listing) fetched at or
  before the cutoff, then applies later top-up fetches in fetch order;
- a top-up must overlap the series by MIN_OVERLAP bars with prices within PRICE_TOL; a constant price ratio across
  the overlap is a split or an adjustment change: the build stops and asks for a full refetch of that symbol;
- bars dated on the fetch day (New York) are dropped, because the last bar of a reply may still be forming.

The checksum, bar-frame and bar-sanity functions are ported from the price library's marketdata.py in code/port.py.
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
import port as md  # noqa: E402  (helpers ported from the price library's marketdata.py; see code/port.py)
import captured_by as pit  # noqa: E402

ROOT = _paths.ROOT
TZ = "America/New_York"                 # every pilot symbol is US-listed


class NoFetchUnderCutoff(ValueError):
    """No full-history fetch of the symbol is visible under the point-in-time cutoff (a row can say 'no data')."""
PRICE_COLS = md.PRICE_COLS
MIN_OVERLAP, EXTRA_BARS, PRICE_TOL, MAX_BARS = md.MIN_OVERLAP, md.EXTRA_BARS, md.PRICE_TOL, md.MCP_MAX_BARS
SERIES_TYPE = "price_only"
ADJUSTMENT = "split-adjusted only, NOT dividend-adjusted (TradingView MCP feed)"


# ---------- paths and small helpers ----------

def raw_dir(root=ROOT):
    return Path(root) / "data" / "raw" / "tradingview"


def series_dir(root=ROOT):
    return Path(root) / "data" / "series"


def register_dir(root=ROOT):
    return Path(root) / "data" / "register"


def utc_now_iso(now=None):
    now = datetime.now(timezone.utc) if now is None else now
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def file_symbol(symbol):
    return symbol.replace(":", "_")


def _day(ts):
    return str(pd.Timestamp(ts).date())


def ny_date(fetched_utc):
    """The New York calendar date at the moment of the fetch (naive Timestamp at midnight)."""
    return pd.Timestamp(fetched_utc).tz_convert(TZ).tz_localize(None).normalize()


# ---------- manifest ----------

def read_manifest(root=ROOT):
    p = raw_dir(root) / "manifest.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def _append_manifest(rec, root=ROOT):
    p = raw_dir(root) / "manifest.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")


def records(symbol=None, root=ROOT, cutoff=None):
    """Saved fetches, oldest first, visible under the cutoff (explicit, else the active captured_by cutoff)."""
    if cutoff is not None:
        pit._check(cutoff)
    recs = [r for r in read_manifest(root) if r.get("result") == "saved"
            and (symbol is None or r["symbol"] == symbol) and pit.allowed(r["fetched_utc"], cutoff)]
    return sorted(recs, key=lambda r: (r["fetched_utc"], r["path"]))


# ---------- ingest ----------

def _rows_from_columns(cols, source="reply"):
    """Turn the MCP's columns layout ({t: [...], o: [...], ...}) into the rows layout ([{t, o, h, l, c, v}, ...])."""
    keys = ("t", "o", "h", "l", "c", "v")
    if "t" not in cols:
        raise ValueError(f"{source}: columns format without a t[] array")
    n = len(cols["t"])
    for k in keys:
        if k in cols and len(cols[k]) != n:
            raise ValueError(f"{source}: column {k} has {len(cols[k])} values, t has {n}")
    return [{k: (cols[k][i] if k in cols else None) for k in keys} for i in range(n)]


def parse_reply(raw_bytes, source="reply"):
    """Validate one mcp-tv-get-ohlcv reply (rows format). Returns (data, frame) or raises."""
    data = json.loads(raw_bytes.decode("utf-8"))
    if data.get("success") is not True:
        raise ValueError(f"{source}: reply has success={data.get('success')!r}")
    symbol = data.get("symbol")
    if not symbol or ":" not in symbol:
        raise ValueError(f"{source}: reply has no EXCHANGE:TICKER symbol")
    if str(data.get("interval")) != "1D":
        raise ValueError(f"{source}: interval is {data.get('interval')!r}; only daily (1D) replies are stored")
    bars = data.get("bars")
    if isinstance(bars, dict):
        bars = _rows_from_columns(bars, source)       # compact columns format: arrays t[], o[], h[], l[], c[], v[]
        data = dict(data, bars=bars)
    if not isinstance(bars, list) or not bars:
        raise ValueError(f"{source}: bars must be a non-empty list (rows format) or column arrays")
    md.verify_summary(data)
    frame = md.bars_to_frame(bars, TZ, source)
    bad = md.bar_problems(frame)
    if bad:
        raise ValueError(f"{source}: impossible prices on {bad[:5]}")
    return data, frame


def ingest(src, root=ROOT, fetched_utc=None):
    """Store one reply file byte-for-byte under raw/<UTC date>/ and record it. Returns the manifest record.

    `fetched_utc` is the time the MCP call was made, not the time of this call: the forming-bar rule drops bars
    dated on the fetch day (New York), so a late ingest with the wrong stamp could keep a bar that was still forming.
    """
    if fetched_utc is None:
        raise ValueError("fetched_utc is required: pass the UTC time of the MCP call (YYYY-MM-DDTHH:MM:SSZ)")
    src = Path(src)
    raw_bytes = src.read_bytes()
    data, frame = parse_reply(raw_bytes, src.name)
    pit._check(fetched_utc)
    digest = sha256_bytes(raw_bytes)
    for r in read_manifest(root):
        if r.get("sha256") == digest:
            return r                       # the same reply was stored before: idempotent
    day = fetched_utc[:10]
    folder = raw_dir(root) / day
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"{file_symbol(data['symbol'])}_1D_{day}"
    dest, k = folder / f"{stem}.json", 2
    while dest.exists():
        dest, k = folder / f"{stem}-{k}.json", k + 1
    dest.write_bytes(raw_bytes)
    rec = {
        "path": dest.relative_to(raw_dir(root)).as_posix(), "symbol": data["symbol"], "interval": "1D",
        "bars": len(data["bars"]), "first": _day(frame.index[0]), "last": _day(frame.index[-1]),
        "full": not bool(data.get("has_more", False)), "fetched_utc": fetched_utc, "sha256": digest,
        "result": "saved",
    }
    _append_manifest(rec, root)
    return rec


# ---------- build ----------

def bar_fixes(root=ROOT):
    """Dated corrections to single bad bars in the feed, from data/register/bar_fixes.csv (sourced, never silent).

    Columns: symbol, date, fields (pipe-separated, e.g. open|high|low|close), factor, reason, source, captured_date.
    The raw file is never edited; the fix is applied at build time and listed in the series metadata.
    """
    p = register_dir(root) / "bar_fixes.csv"
    cols = ["symbol", "date", "fields", "factor", "reason", "source", "captured_date"]
    if not p.exists():
        return pd.DataFrame(columns=cols)
    df = pd.read_csv(p, dtype=str, keep_default_na=False)
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d")
    df["factor"] = df["factor"].astype(float)
    return df


def _apply_fixes(df, symbol, root=ROOT):
    fixes = bar_fixes(root)
    fixes = fixes[fixes["symbol"] == symbol]
    applied = []
    for _, f in fixes.iterrows():
        if f["date"] not in df.index:
            continue
        cols = [c.strip() for c in str(f["fields"]).split("|") if c.strip()]
        bad = [c for c in cols if c not in df.columns]
        if bad:
            raise ValueError(f"{symbol}: bar fix on {f['date'].date()} names unknown fields {bad}")
        df.loc[f["date"], cols] = df.loc[f["date"], cols].astype(float) * float(f["factor"])
        applied.append({"date": str(f["date"].date()), "fields": cols, "factor": float(f["factor"]),
                        "reason": f["reason"], "source": f["source"]})
    return df, applied


def _frame_for(rec, root=ROOT):
    """Bars of one stored reply as a date-indexed frame, without bars dated on the fetch day (may be forming)."""
    p = raw_dir(root) / rec["path"]
    raw_bytes = p.read_bytes()
    if sha256_bytes(raw_bytes) != rec["sha256"]:
        raise ValueError(f"{rec['path']}: file hash differs from the manifest; raw files must never change")
    _, frame = parse_reply(raw_bytes, rec["path"])
    return frame[frame.index < ny_date(rec["fetched_utc"])]


def build(symbol, root=ROOT, cutoff=None, write=True):
    """Rebuild data/series/<SYMBOL>.csv from raw fetches visible under the cutoff. Returns the frame."""
    recs = records(symbol, root, cutoff)
    # A base fetch reaches the listing (has_more false) or is a maximal window of MAX_BARS bars: stocks listed
    # more than ~20 years ago exceed one reply, and v0.1 works with the latest MAX_BARS sessions of them.
    bases = [r for r in recs if r["full"] or r["bars"] >= MAX_BARS]
    if not bases:
        raise NoFetchUnderCutoff(f"{symbol}: no full-history fetch (has_more false, or {MAX_BARS} bars) is visible "
                                 f"under the cutoff; fetch it with count {MAX_BARS}")
    base = bases[-1]
    df = _frame_for(base, root)
    used = [base["path"]]
    complete = bool(base["full"])
    for r in recs:
        if r["fetched_utc"] <= base["fetched_utc"]:
            continue
        new = _frame_for(r, root)
        if new.empty:
            continue
        last = df.index[-1]
        if last not in new.index:
            raise ValueError(f"{symbol}: top-up {r['path']} does not reach back to the stored last date {_day(last)}; "
                             f"fetch again with count >= gap + {EXTRA_BARS}")
        window = df[df.index >= new.index[0]]
        fetched = new[new.index <= last]
        if not window.index.equals(fetched.index):
            only_s = [_day(d) for d in window.index.difference(fetched.index)][:5]
            only_f = [_day(d) for d in fetched.index.difference(window.index)][:5]
            raise ValueError(f"{symbol}: stored and fetched dates disagree in the overlap of {r['path']}. "
                             f"Only stored: {only_s}; only fetched: {only_f}")
        if len(window) < MIN_OVERLAP:
            raise ValueError(f"{symbol}: only {len(window)} overlapping bars in {r['path']}; need {MIN_OVERLAP}")
        ratio = window[PRICE_COLS] / fetched[PRICE_COLS]
        worst = float((ratio - 1).abs().max().max())
        if worst > PRICE_TOL:
            rc = ratio["close"]
            if float(rc.std() / rc.mean()) < PRICE_TOL:
                raise ValueError(f"{symbol}: SPLIT or adjustment change: stored prices are a constant {rc.mean():.6f}x "
                                 f"the prices in {r['path']} across the overlap. Full refetch needed (count {MAX_BARS}); "
                                 "record the split in the register")
            bad = rc[(rc - 1).abs() > PRICE_TOL]
            raise ValueError(f"{symbol}: stored and fetched prices disagree (worst {worst:.4%}) on "
                             f"{[_day(d) for d in bad.index[:5]]} in {r['path']}")
        df = pd.concat([df, new[new.index > last]])
        used.append(r["path"])
    df, fixes = _apply_fixes(df.copy(), symbol, root)
    df.attrs.update(symbol=symbol, series_type=SERIES_TYPE, adjustment=ADJUSTMENT, built_from=used,
                    complete_history=complete, fixes_applied=fixes,
                    cutoff=cutoff if cutoff is not None else pit.cutoff())
    if write:
        out = series_dir(root)
        out.mkdir(parents=True, exist_ok=True)
        md.write_table(df, out / f"{file_symbol(symbol)}.csv")
        meta = {"symbol": symbol, "series_type": SERIES_TYPE, "adjustment": ADJUSTMENT, "built_from": used,
                "complete_history": complete, "fixes_applied": fixes, "cutoff": df.attrs["cutoff"],
                "rows": int(len(df)), "first": _day(df.index[0]), "last": _day(df.index[-1])}
        (out / f"{file_symbol(symbol)}.meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n",
                                                             encoding="utf-8", newline="\n")
    return df


def load_series(symbol, root=ROOT):
    """A built series: DataFrame indexed by date with open high low close volume source; attrs say what it is."""
    p = series_dir(root) / f"{file_symbol(symbol)}.csv"
    if not p.exists():
        raise FileNotFoundError(f"{symbol}: no built series at {p}; run build first")
    df = pd.read_csv(p, parse_dates=["date"], index_col="date")
    meta = json.loads(p.with_suffix(".meta.json").read_text(encoding="utf-8"))
    df.attrs.update(meta)
    return df


def banner(symbol, root=ROOT):
    df = load_series(symbol, root)
    span = "from the listing" if df.attrs.get("complete_history") else f"a {MAX_BARS}-bar window, NOT the full listing"
    fixes = df.attrs.get("fixes_applied") or []
    note = f"; {len(fixes)} bar fix(es) applied: " + ", ".join(f["date"] for f in fixes) if fixes else ""
    return (f"SERIES {symbol}: {df.attrs['series_type']} ({df.attrs['adjustment']}); {len(df)} sessions "
            f"{df.attrs['first']} .. {df.attrs['last']} ({span}); built from {len(df.attrs['built_from'])} fetch(es){note}")


# ---------- plan and status ----------

def register_symbols(root=ROOT):
    """EXCHANGE:TICKER symbols from data/register/funds.csv and stocks.csv (columns `symbol`, optional `status`)."""
    out = []
    for name in ("funds.csv", "stocks.csv"):
        p = register_dir(root) / name
        if not p.exists():
            continue
        t = pd.read_csv(p, dtype=str)
        for _, r in t.iterrows():
            out.append((r["symbol"].strip(), str(r.get("status", "live")).strip().lower()))
    return out


def plan(root=ROOT, now=None):
    """What to fetch now: full history (count 5000) for symbols with no series, else the gap plus EXTRA_BARS."""
    today = ny_date(utc_now_iso(now))
    rows = []
    for symbol, status in register_symbols(root):
        p = series_dir(root) / f"{file_symbol(symbol)}.csv"
        if not p.exists():
            rows.append({"symbol": symbol, "count": MAX_BARS, "reason": "full: no series yet"})
            continue
        last = pd.Timestamp(json.loads(p.with_suffix(".meta.json").read_text(encoding="utf-8"))["last"])
        if status == "closed":
            rows.append({"symbol": symbol, "count": 0, "reason": f"closed; series ends {_day(last)}"})
            continue
        gap = int(np.busday_count(last.date() + pd.Timedelta(days=1), today.date()))
        rows.append({"symbol": symbol, "count": min(gap + EXTRA_BARS, MAX_BARS), "reason": f"top-up from {_day(last)}"})
    return rows


def status(root=ROOT):
    rows = []
    recs = read_manifest(root)
    for symbol in sorted({r["symbol"] for r in recs}):
        mine = [r for r in recs if r["symbol"] == symbol]
        p = series_dir(root) / f"{file_symbol(symbol)}.csv"
        meta = json.loads(p.with_suffix(".meta.json").read_text(encoding="utf-8")) if p.exists() else {}
        rows.append({"symbol": symbol, "fetches": len(mine), "last_fetch_utc": max(r["fetched_utc"] for r in mine),
                     "series_rows": meta.get("rows"), "series_first": meta.get("first"), "series_last": meta.get("last")})
    return rows


# ---------- command line ----------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan")
    sub.add_parser("status")
    p_in = sub.add_parser("ingest")
    p_in.add_argument("files", nargs="+")
    p_in.add_argument("--fetched-utc", required=True, help="UTC time of the MCP call, YYYY-MM-DDTHH:MM:SSZ")
    p_b = sub.add_parser("build")
    p_b.add_argument("symbols", nargs="*")
    p_b.add_argument("--all", action="store_true")
    p_b.add_argument("--cutoff", default=None)
    a = ap.parse_args(argv)
    if a.cmd == "plan":
        for r in plan():
            print(f"{r['symbol']:16s} count={r['count']:5d}  {r['reason']}")
    elif a.cmd == "status":
        for r in status():
            print(r)
    elif a.cmd == "ingest":
        for f in a.files:
            r = ingest(f, fetched_utc=a.fetched_utc)
            print(f"saved {r['symbol']:16s} {r['bars']:5d} bars {r['first']} .. {r['last']}  full={r['full']}  -> {r['path']}")
    elif a.cmd == "build":
        symbols = sorted({r["symbol"] for r in records(cutoff=a.cutoff)}) if a.all else a.symbols
        for s in symbols:
            df = build(s, cutoff=a.cutoff)
            print(f"built {s:16s} {len(df):5d} sessions {_day(df.index[0])} .. {_day(df.index[-1])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
