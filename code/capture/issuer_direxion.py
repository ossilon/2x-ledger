"""Direxion (direxion.com), read on 2026-10-23.

- daily, per fund: `/holdings/<T>.csv`: three header lines (fund name, ticker, "Shares Outstanding:<n>"), then
  the positions with TradeDate, shares, price, market value and weight. Dated rows, latest day only.
The NAV history lives in `direxion-prod.s3.amazonaws.com/public-data/nav-chart/<PAIR>.json`, keyed by the
bull-and-bear pair slug of the product page (for example TSLL-TSLS); the pair slug is not derivable from the
ticker, so this file waits for a slug column (v0.2.1). Scripted requests with this project's user agent get
HTTP 200 (a generic fetch tool got 403).
"""
import csv
import io
import re

from issuer_capture import spec

SOURCE = "direxion"
BASE = "https://www.direxion.com"
FORMATS = {"holdings": [("v1", b"Direxion Daily")]}


def plan(ctx):
    return [spec(f"{f['ticker']}_holdings.csv", f"{BASE}/holdings/{f['ticker']}.csv", b"Direxion Daily", "daily", "holdings", ticker=f["ticker"])
            for f in ctx.funds]


def parse_holdings(body):
    """-> dict(name, ticker, shares_outstanding, rows[dict(date, stock_ticker, description, shares, price, market_value, cusip, weight_pct)])."""
    text = body.decode("utf-8", "replace").lstrip("﻿")
    lines = text.splitlines()
    name, ticker = lines[0].strip(), lines[1].strip()
    m = re.search(r"Shares Outstanding:\s*([\d,]+)", text)
    shares_out = float(m.group(1).replace(",", "")) if m else None
    start = next(i for i, ln in enumerate(lines) if ln.startswith('"TradeDate"'))
    rows = []
    for r in csv.DictReader(io.StringIO("\n".join(lines[start:]))):
        rows.append(dict(date=r["TradeDate"][:10], stock_ticker=r.get("StockTicker"), description=r.get("SecurityDescription"),
                         shares=_f(r.get("Shares")), price=_f(r.get("Price")), market_value=_f(r.get("MarketValue")),
                         cusip=r.get("Cusip"), weight_pct=_f(r.get("HoldingsPercent"))))
    return dict(name=name, ticker=ticker, shares_outstanding=shares_out, rows=rows)


def _f(x):
    try:
        return float(str(x).replace(",", "").strip()) if x not in (None, "") else None
    except ValueError:
        return None
