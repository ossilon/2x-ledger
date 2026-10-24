#!/usr/bin/env python3
"""Seed the draft fund register from Yahoo: name, exchange, first trade date, last close, row count per ticker.

    py -I scripts\\register_seed.py                      reads data/register/funds_draft.csv, writes funds_seed.csv
    py -I scripts\\register_seed.py --only AAPU NVDL     a few tickers

Each ticker gets one small chart request (the last 30 days) whose `meta` carries longName, exchangeName,
firstTradeDate and the last close date. Nothing is saved raw here: the seed is a lookup to help the user verify
DRAFT rows (v0.2 plan, D1), not a capture. A 404 marks the ticker "not found" (a wrong ticker, a fund not yet
trading, or a delisting). One request a second; about six minutes for 330 tickers.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "data" / "register" / "funds_draft.csv"
OUT = ROOT / "data" / "register" / "funds_seed.csv"
EXCHANGES = {"NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ", "PCX": "AMEX", "BTS": "CBOE", "NYQ": "NYSE", "ASE": "AMEX"}


def meta_for(ticker, now=None):
    now = now or int(time.time())
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(ticker)
           + f"?period1={now - 30 * 86400}&period2={now}&interval=1d")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        raw = urllib.request.urlopen(req, timeout=60).read()
    except urllib.error.HTTPError as err:
        return {"found": False, "error": f"HTTP {err.code}"}
    except (urllib.error.URLError, TimeoutError) as err:
        return {"found": False, "error": f"network: {str(err)[:40]}"}
    j = json.loads(raw)["chart"]
    if not j.get("result"):
        return {"found": False, "error": str(j.get("error"))[:60]}
    m = j["result"][0]["meta"]
    ts = j["result"][0].get("timestamp", [])
    first = m.get("firstTradeDate")
    return {"found": True, "yahoo_name": m.get("longName") or m.get("shortName") or "",
            "exchange_code": m.get("exchangeName", ""), "exchange": EXCHANGES.get(m.get("exchangeName", ""), m.get("exchangeName", "")),
            "first_trade_date": datetime.fromtimestamp(first, tz=timezone.utc).date().isoformat() if first else "",
            "last_close_date": datetime.fromtimestamp(ts[-1], tz=timezone.utc).date().isoformat() if ts else "",
            "last_close": m.get("regularMarketPrice", ""), "error": ""}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--pause", type=float, default=1.0)
    a = ap.parse_args(argv)
    draft = pd.read_csv(DRAFT, dtype=str, keep_default_na=False)
    rows = []
    todo = draft if a.only is None else draft[draft["ticker"].isin(a.only)]
    for i, (_, r) in enumerate(todo.iterrows()):
        m = meta_for(r["ticker"])
        rows.append({**r.to_dict(), **{k: m.get(k, "") for k in ("yahoo_name", "exchange", "exchange_code", "first_trade_date", "last_close_date", "last_close", "error")},
                     "yahoo_found": bool(m["found"]), "seeded_date": datetime.now(timezone.utc).date().isoformat()})
        print(f"{i + 1:4d} {r['ticker']:6s} {'ok ' if m['found'] else 'NO '} {m.get('exchange', ''):7s} {m.get('first_trade_date', ''):10s} {m.get('yahoo_name', m.get('error', ''))[:60]}")
        time.sleep(a.pause)
    out = pd.DataFrame(rows)
    if a.only is not None and OUT.exists():                       # merge a partial run into the existing seed
        old = pd.read_csv(OUT, dtype=str, keep_default_na=False)
        out = pd.concat([old[~old["ticker"].isin(out["ticker"])], out.astype(str)], ignore_index=True)
        out = out.set_index("ticker").loc[draft["ticker"][draft["ticker"].isin(out["ticker"])]].reset_index()
    out.to_csv(OUT, index=False, lineterminator="\n")
    found = int(out["yahoo_found"].astype(str).eq("True").sum())
    print(f"\nseeded {len(out)} tickers: {found} found on Yahoo, {len(out) - found} not found -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
