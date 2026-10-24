"""ProShares (proshares.com; data files on accounts.profunds.com/etfdata/), read on 2026-10-23.

Four files cover every ProShares fund, so the capture does not depend on the universe list:
- daily: `psdlyhld.csv` (every position of every fund, one "AS OF" date; 1.8 MB, stored compressed) and
  `etf_splits.csv` (forward and reverse splits with pre and post CUSIPs and dates);
- monthly: `historical_nav.csv` (every fund's NAV, shares outstanding (000) and AUM for every day since
  inception; 53 MB, stored compressed; the history of record for ProShares) and `etf_performance.csv`
  (standardized monthly and quarterly returns with inception dates).
"""
import csv
import io

from issuer_capture import spec

SOURCE = "proshares"
BASE = "https://accounts.profunds.com/etfdata/"
NEEDS_FUNDS = False
FORMATS = {"psdlyhld": [("v1", b"PORTFOLIO HOLDINGS INFORMATION")], "historical_nav": [("v1", b"Date,ProShares Name,Ticker,NAV")],
           "etf_splits": [("v1", b"Symbol,Name,Pre Split Cusip")], "etf_performance": [("v1", b"Fund Name,Fund Symbol")]}


def plan(ctx):
    return [spec("psdlyhld.csv", BASE + "psdlyhld.csv", b"PORTFOLIO HOLDINGS INFORMATION", "daily", "holdings"),
            spec("etf_splits.csv", BASE + "etf_splits.csv", b"Symbol,Name,Pre Split Cusip", "daily", "events"),
            spec("historical_nav.csv", BASE + "historical_nav.csv", b"Date,ProShares Name,Ticker,NAV", "monthly", "history"),
            spec("etf_performance.csv", BASE + "etf_performance.csv", b"Fund Name,Fund Symbol", "monthly", "history")]


def parse_nav_history(body, tickers=None):
    """-> list of dict(date (MM/DD/YYYY), ticker, name, nav, shares_outstanding, aum); `tickers` filters."""
    want = set(tickers) if tickers else None
    out = []
    for r in csv.DictReader(io.StringIO(body.decode("utf-8", "replace"))):
        if want and r["Ticker"] not in want:
            continue
        out.append(dict(date=r["Date"], ticker=r["Ticker"], name=r["ProShares Name"], nav=_f(r["NAV"]),
                        shares_outstanding=_f(r["Shares Outstanding (000)"]) * 1000 if _f(r["Shares Outstanding (000)"]) is not None else None,
                        aum=_f(r["Assets Under Management"])))
    return out


def parse_holdings(body, tickers=None):
    """-> (as_of, rows of dict(fund, name, description, shares, market_value)) from psdlyhld.csv."""
    lines = body.decode("utf-8", "replace").splitlines()
    as_of = lines[1].split(",")[0].replace("AS OF", "").strip() if len(lines) > 1 else None
    want = set(tickers) if tickers else None
    rows = []
    for r in csv.reader(io.StringIO("\n".join(lines[2:]))):
        if len(r) < 9 or not r[0] or (want and r[0] not in want):
            continue
        rows.append(dict(fund=r[0], name=r[1], description=r[4], shares=_f(r[7]), market_value=_f(r[8])))
    return as_of, rows


def parse_splits(body, tickers=None):
    want = set(tickers) if tickers else None
    return [dict(ticker=r["Symbol"], name=r["Name"], kind=r["Split Type"], ratio=_f(r["Ratio"]), date=r["Date of Split"])
            for r in csv.DictReader(io.StringIO(body.decode("utf-8", "replace"))) if not want or r["Symbol"] in want]


def _f(x):
    try:
        return float(str(x).replace(",", "").strip()) if x not in (None, "") else None
    except ValueError:
        return None
