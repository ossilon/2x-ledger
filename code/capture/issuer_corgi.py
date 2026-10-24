"""Corgi (corgiinvest.com): a JSON API behind every fund page, read from the network calls on 2026-10-23.

- daily, per fund: `/api/data/funds/<T>/summary` (latest NAV, AUM, market price, premium, spread, holdings date)
  and `/api/data/holdings?ticker=<T>` (latest positions: the swap line names the counterparty code).
- weekly: `/api/data/funds` (the lineup of record: every Corgi fund with category, underlying, inception, expense
  ratio; about 3.4 MB, stored compressed).
- monthly, per fund: `/api/data/funds/<T>/daily-nav` (NAV, net assets, market price, premium since inception; a
  missed day comes back here, so this is the history of record for Corgi).
The latest NAV lags the market price by a day on the site (2026-10-23: NAV dated 10-22).
"""
import json

from issuer_capture import spec

SOURCE = "corgi"
BASE = "https://corgiinvest.com/api/data"
FORMATS = {"summary": [("v1", b'{"ticker"')], "holdings": [("v1", b"[")], "funds": [("v1", b'{"funds"')], "daily_nav": [("v1", b"[")]}


def plan(ctx):
    out = [spec("funds.json", f"{BASE}/funds", b'{"funds"', "weekly", "list")]
    for f in ctx.funds:
        t = f["ticker"]
        out.append(spec(f"{t}_summary.json", f"{BASE}/funds/{t}/summary", b'{"ticker"', "daily", "nav", ticker=t))
        out.append(spec(f"{t}_holdings.json", f"{BASE}/holdings?ticker={t}", b"[", "daily", "holdings", ticker=t))
        out.append(spec(f"{t}_daily_nav.json", f"{BASE}/funds/{t}/daily-nav", b"[", "monthly", "history", ticker=t))
    return out


def parse_summary(body):
    """-> dict(ticker, nav_date, nav, aum, market_price, premium_pct, spread_pct, holdings_date)."""
    j = json.loads(body)
    return dict(ticker=j["ticker"], nav_date=j.get("latest_nav_date"), nav=_f(j.get("latest_nav")),
                aum=_f(j.get("latest_aum")), market_price=_f(j.get("latest_market_price")),
                premium_pct=_f(j.get("latest_premium_discount_pct")), spread_pct=_f(j.get("latest_median_30_day_spread_pct")),
                holdings_date=j.get("latest_holdings_date"))


def parse_daily_nav(body):
    """-> list of dict(date, nav, net_assets, market_price, premium_pct) oldest first."""
    return [dict(date=r["rate_date"], nav=_f(r["nav"]), net_assets=_f(r["net_assets"]), market_price=_f(r["market_price"]),
                 premium_pct=_f(r["premium_discount_percentage"])) for r in json.loads(body)]


def parse_funds(body):
    """-> list of dict(ticker, name, category, underlying, inception, expense_ratio, leverage) for every fund."""
    return [dict(ticker=x.get("ticker"), name=x.get("name"), category=x.get("category"), underlying=x.get("underlyingTicker"),
                 inception=x.get("inceptionDate"), expense_ratio=x.get("expenseRatio"), leverage=x.get("leverageFactor"))
            for x in json.loads(body)["funds"]]


def _f(x):
    try:
        return float(x) if x not in (None, "") else None
    except (TypeError, ValueError):
        return None
