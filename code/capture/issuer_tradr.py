"""Tradr (tradretfs.com; data served by FilePoint at axsetf.filepoint.live), read on 2026-10-23.

Every Tradr fund is in the same file, one file per day, named by date, and older days stay downloadable:
- `NSDEAXS2.MMDDYYYY.csv`: the fund accountant's daily record (NAV, shares, net assets and about 90 other
  fields per fund; quoted CSV, header row starts "30 Day Effective Yield");
- `ICE_ETP_AXS_Premium_0130_YYYYMMDD.csv`: exchange closes, volumes and the premium/discount per fund;
- `BBH_AXS_ETF_PVAL_WEB.YYYYMMDD.csv`: the custodian's holdings file (every position of every fund).
The accounting and holdings files appear after the US close (about 22:20 to 22:50 UTC); the ICE file appears
the next morning (about 06:40 UTC). The capture therefore asks for every recent weekday's files that it has
not saved yet (cadence "dated"), so a file published after the run is picked up the next day.
Undated history files: `AXS_PREMIUM_DISCOUNT.CSV` (since 2015) and `Tradr_Exposure_History.csv` monthly;
`AXS_Dividend_History.csv` and `AXS_ETF_Performance.csv` monthly.
"""
import csv
import io

from issuer_capture import published_at, spec, weekdays_back

SOURCE = "tradr"
BASE = "https://axsetf.filepoint.live/assets/data/"
NEEDS_FUNDS = False
FORMATS = {"NSDEAXS2": [("v1", b'"30 Day Effective Yield"')], "ICE": [("v1", b"Trade Date,Symbol")], "BBH": [("v1", b"ETF Ticker,Date")]}
EOD_HOUR_UTC = 23          # accounting and holdings files were on the host by 22:20 and 22:53 UTC (2026-10-22)
ICE_HOUR_UTC = 8           # the ICE price file appeared at 06:41 UTC the next day


def plan(ctx):
    out = []
    for d in weekdays_back(ctx.today):
        eod, morning = published_at(d, EOD_HOUR_UTC), published_at(d, ICE_HOUR_UTC, next_day=True)
        out.append(spec(f"NSDEAXS2.{d:%m%d%Y}.csv", f"{BASE}NSDEAXS2.{d:%m%d%Y}.csv", b'"30 Day Effective Yield"', "dated", "nav", date=d, ready_utc=eod))
        out.append(spec(f"ICE_ETP_AXS_Premium_0130_{d:%Y%m%d}.csv", f"{BASE}ICE_ETP_AXS_Premium_0130_{d:%Y%m%d}.csv", b"Trade Date,Symbol", "dated", "price", date=d, ready_utc=morning))
        out.append(spec(f"BBH_AXS_ETF_PVAL_WEB.{d:%Y%m%d}.csv", f"{BASE}BBH_AXS_ETF_PVAL_WEB.{d:%Y%m%d}.csv", b"ETF Ticker,Date", "dated", "holdings", date=d, ready_utc=eod))
    out.append(spec("Tradr_Exposure_History.csv", BASE + "Tradr_Exposure_History.csv", b"DATE,", "monthly", "history"))
    out.append(spec("AXS_PREMIUM_DISCOUNT.CSV", BASE + "AXS_PREMIUM_DISCOUNT.CSV", None, "monthly", "history"))
    out.append(spec("AXS_Dividend_History.csv", BASE + "AXS_Dividend_History.csv", b"Fund,Year", "monthly", "history"))
    out.append(spec("AXS_ETF_Performance.csv", BASE + "AXS_ETF_Performance.csv", b"<CONFLUENCE_TRANSFORMER>", "monthly", "history"))
    return out


def parse_ice(body):
    """-> list of dict(date, ticker, name, close, volume, nav?, premium?) from the ICE premium file."""
    rows = list(csv.DictReader(io.StringIO(body.decode("utf-8", "replace"))))
    out = []
    for r in rows:
        out.append(dict(date=r.get("Trade Date"), ticker=r.get("Symbol"), name=r.get("Name"),
                        close=_f(r.get("Consolidated Close Price")), volume=_f(r.get("Consolidated Volume")),
                        nav=_f(r.get("NAV")), premium_pct=_f(r.get("Premium/Discount") or r.get("Premium Discount"))))
    return out


def parse_holdings(body):
    """-> list of dict(fund, date, ticker, description, shares, price, market_value, shares_outstanding, net_assets, weight_pct)."""
    rows = list(csv.DictReader(io.StringIO(body.decode("utf-8", "replace"))))
    return [dict(fund=r["ETF Ticker"], date=r["Date"], ticker=r.get("Ticker"), description=r.get("Description"),
                 shares=_f(r.get("Shares")), price=_f(r.get("Security Price")), market_value=_f(r.get("Market Value")),
                 shares_outstanding=_f(r.get("Shares Outstanding")), net_assets=_f(r.get("Total Net Assets")),
                 weight_pct=_f((r.get("Market Value Weight") or "").rstrip("%"))) for r in rows]


def _f(x):
    try:
        return float(str(x).replace(",", "").strip()) if x not in (None, "") else None
    except ValueError:
        return None
