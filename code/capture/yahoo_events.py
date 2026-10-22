#!/usr/bin/env python3
"""Dividend, distribution and split events (plus adjusted closes) from Yahoo Finance, saved raw per symbol.

Uses the chart-endpoint fetch and validation ported from the LETF kit's fetch_yahoo.py (code/port.py), with the end
time set to the time of the call. Files go to data/raw/yahoo/<UTC date>/<TICKER>.json, listed in
data/raw/yahoo/manifest.jsonl with SHA-256 and fetch time. Raw files are never edited.

Why this exists: the TradingView feed is split-adjusted only. Fund distributions (TSLL pays ~4%/yr of collateral
interest) and stock dividends must be added back to build total return, and Yahoo is the scriptable source of the
event history. Yahoo's `adjclose` (split and dividend adjusted) is also the independent cross-check of the
TradingView closes: a price copied wrongly from an MCP reply shows up as a disagreement on that date.

Commands (run from twox_ledger/):
    py -I code\\capture\\yahoo_events.py fetch NASDAQ:TSLL NASDAQ:TSLA ...      download (1 s pause between symbols)
    py -I code\\capture\\yahoo_events.py events NASDAQ:TSLL                     print dividends and splits
    py -I code\\capture\\yahoo_events.py crosscheck NASDAQ:TSLL                 Yahoo close vs the built TradingView series
"""
import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _paths  # noqa: E402,F401
import port  # noqa: E402  (yahoo_url, yahoo_fetch, yahoo_validate ported from the LETF kit's fetch_yahoo.py)
import captured_by as pit  # noqa: E402
import tv_capture as tc  # noqa: E402

ROOT = _paths.ROOT
CROSSCHECK_TOL = 1e-3     # 0.1%: both feeds carry the official close; larger gaps are listed for review


def raw_dir(root=ROOT):
    return Path(root) / "data" / "raw" / "yahoo"


def ticker(symbol):
    """Yahoo symbol from EXCHANGE:TICKER (TradingView form); a plain ticker passes through."""
    return symbol.split(":")[-1]


def read_manifest(root=ROOT):
    p = raw_dir(root) / "manifest.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def records(symbol=None, root=ROOT, cutoff=None):
    if cutoff is not None:
        pit._check(cutoff)
    t = ticker(symbol) if symbol else None
    recs = [r for r in read_manifest(root) if r.get("result") == "saved" and (t is None or r["ticker"] == t)
            and pit.allowed(r["fetched_utc"], cutoff)]
    return sorted(recs, key=lambda r: (r["fetched_utc"], r["path"]))


def fetch(symbol, root=ROOT, now=None):
    """Download one symbol's full daily history with events and store it raw. Returns the manifest record."""
    t = ticker(symbol)
    now = now or datetime.now(timezone.utc)
    raw = port.yahoo_fetch(t, int(now.timestamp()))
    s, has_adj = port.yahoo_validate(raw, t)           # raises on non-daily, duplicate, unsorted or non-positive data
    fetched_utc = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    day = fetched_utc[:10]
    folder = raw_dir(root) / day
    folder.mkdir(parents=True, exist_ok=True)
    dest, k = folder / f"{t}.json", 2
    while dest.exists() and dest.read_bytes() != raw:
        dest, k = folder / f"{t}-{k}.json", k + 1
    dest.write_bytes(raw)
    j = json.loads(raw)["chart"]["result"][0]
    ev = j.get("events", {})
    rec = {"path": dest.relative_to(raw_dir(root)).as_posix(), "ticker": t, "symbol": symbol, "rows": int(len(s)),
           "first": str(s.index[0].date()), "last": str(s.index[-1].date()), "adjclose": bool(has_adj),
           "dividends": len(ev.get("dividends", {})), "splits": len(ev.get("splits", {})),
           "fetched_utc": fetched_utc, "sha256": hashlib.sha256(raw).hexdigest(), "result": "saved"}
    with (raw_dir(root) / "manifest.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")
    return rec


def latest(symbol, root=ROOT, cutoff=None):
    recs = records(symbol, root, cutoff)
    if not recs:
        raise FileNotFoundError(f"{symbol}: no Yahoo file saved (under the cutoff); run fetch")
    rec = recs[-1]
    raw = (raw_dir(root) / rec["path"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != rec["sha256"]:
        raise ValueError(f"{rec['path']}: file hash differs from the manifest; raw files must never change")
    return rec, json.loads(raw)["chart"]["result"][0]


def _dates(res):
    tz = res["meta"]["exchangeTimezoneName"]
    return pd.to_datetime(res["timestamp"], unit="s", utc=True).tz_convert(tz).normalize().tz_localize(None)


def events(symbol, root=ROOT, cutoff=None):
    """Two frames: dividends (date, amount) and splits (date, numerator, denominator, ratio), from the latest file."""
    rec, res = latest(symbol, root, cutoff)
    tz = res["meta"]["exchangeTimezoneName"]

    def day(ts):
        return pd.Timestamp(int(ts), unit="s", tz="UTC").tz_convert(tz).normalize().tz_localize(None)

    ev = res.get("events", {})
    div = pd.DataFrame([{"date": day(v["date"]), "amount": float(v["amount"])} for v in ev.get("dividends", {}).values()])
    spl = pd.DataFrame([{"date": day(v["date"]), "numerator": v["numerator"], "denominator": v["denominator"],
                         "ratio": str(v.get("splitRatio", ""))} for v in ev.get("splits", {}).values()])
    for f in (div, spl):
        if not f.empty:
            f.sort_values("date", inplace=True)
            f.reset_index(drop=True, inplace=True)
    div.attrs.update(source=rec["path"], fetched_utc=rec["fetched_utc"])
    spl.attrs.update(source=rec["path"], fetched_utc=rec["fetched_utc"])
    return div, spl


def closes(symbol, root=ROOT, cutoff=None):
    """Yahoo daily closes (split-adjusted, price only) and adjclose (total return) as one frame indexed by date."""
    rec, res = latest(symbol, root, cutoff)
    q = res["indicators"]["quote"][0]
    adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose")
    df = pd.DataFrame({"close": q["close"], "adjclose": adj if adj else q["close"]}, index=_dates(res)).dropna()
    df.attrs.update(source=rec["path"], fetched_utc=rec["fetched_utc"])
    return df


def crosscheck(symbol, root=ROOT, cutoff=None, tol=CROSSCHECK_TOL):
    """Compare the built TradingView series with Yahoo's split-adjusted close on common dates."""
    tv = tc.load_series(symbol, root)
    y = closes(symbol, root, cutoff)
    both = tv[["close"]].join(y[["close"]].rename(columns={"close": "yahoo"}), how="inner")
    rel = (both["close"] / both["yahoo"] - 1.0)
    off = rel[rel.abs() > tol]
    return {"symbol": symbol, "common_days": int(len(both)), "tv_only": int(len(tv.index.difference(y.index))),
            "yahoo_only": int(len(y.index.difference(tv.index))), "max_abs_rel_diff": float(rel.abs().max()) if len(rel) else None,
            "days_over_tol": int(len(off)), "worst": [(str(d.date()), round(float(v), 5)) for d, v in off.abs().sort_values(ascending=False).head(5).items()]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch").add_argument("symbols", nargs="+")
    sub.add_parser("events").add_argument("symbol")
    sub.add_parser("crosscheck").add_argument("symbols", nargs="+")
    a = ap.parse_args(argv)
    if a.cmd == "fetch":
        for i, s in enumerate(a.symbols):
            if i:
                time.sleep(1.0)
            r = fetch(s)
            print(f"saved {s:16s} {r['rows']:6d} rows {r['first']} .. {r['last']}  adjclose={r['adjclose']}  "
                  f"dividends={r['dividends']} splits={r['splits']}  -> {r['path']}")
    elif a.cmd == "events":
        div, spl = events(a.symbol)
        print(f"dividends ({len(div)}):")
        print(div.to_string(index=False) if not div.empty else "  none")
        print(f"splits ({len(spl)}):")
        print(spl.to_string(index=False) if not spl.empty else "  none")
    elif a.cmd == "crosscheck":
        for s in a.symbols:
            print(crosscheck(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
