"""Defiance (defianceetfs.com, WordPress), read on 2026-10-23.

- daily: `/wp-json/defiance/v1/etfs-explore`, one JSON list of every Defiance fund with rate_date, nav,
  market_price, net_assets and premium_discount (the lineup and the day's NAV in one request).
- weekly (Friday and month-end), per fund: the fund page `/<t>/` (server-rendered "Fund Details": net assets,
  NAV, closing price, shares outstanding, inception, CUSIP, gross expense ratio) and `/<t>-full-holdings/`
  (server-rendered holdings table with "Data as of"). No CSV exists; pages are stored compressed.
"""
import json
import re

from issuer_capture import is_html, spec

SOURCE = "defiance"
BASE = "https://www.defianceetfs.com"
FORMATS = {"explore": [("v1", b'[{"ticker"')]}


def plan(ctx):
    out = [spec("etfs_explore.json", f"{BASE}/wp-json/defiance/v1/etfs-explore", b'[{"ticker"', "daily", "list")]
    for f in ctx.funds:
        t = f["ticker"]
        out.append(spec(f"{t}_page.html", f"{BASE}/{t.lower()}/", None, "weekly", "page", ticker=t, valid=is_html))
        out.append(spec(f"{t}_holdings.html", f"{BASE}/{t.lower()}-full-holdings/", None, "weekly", "holdings", ticker=t, valid=is_html))
    return out


def parse_explore(body):
    """-> list of dict(ticker, name, category, date, nav, market_price, net_assets, premium_pct)."""
    return [dict(ticker=x["ticker"], name=x["name"], category=x.get("category"), date=x.get("rate_date"), nav=x.get("nav"),
                 market_price=x.get("market_price"), net_assets=x.get("net_assets"), premium_pct=x.get("premium_discount"))
            for x in json.loads(body)]


def parse_page(body):
    """Fund Details block -> dict(as_of, net_assets, nav, closing_price, shares_outstanding, inception, expense_ratio_pct)."""
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body.decode("utf-8", "replace")))
    i = text.find("Fund Details")
    block = text[i:i + 1500] if i >= 0 else text

    def grab(label, pattern=r"\$?([\d,]+\.?\d*)"):
        m = re.search(re.escape(label) + r"\s*" + pattern, block)
        return m.group(1) if m else None

    return dict(as_of=grab("Data as of", r"(\d{2}/\d{2}/\d{4})"), net_assets=grab("Net Assets", r"\$([\d,.]+[MKB]?)"),
                nav=_f(grab("NAV")), closing_price=_f(grab("Closing Price")), shares_outstanding=_f(grab("Shares Outstanding")),
                inception=grab("Fund Inception", r"(\d{2}/\d{2}/\d{4})"), expense_ratio_pct=_f(grab("Gross Expense Ratio", r"([\d.]+)%")))


def parse_holdings(body):
    """Holdings table -> (as_of, rows of dict(ticker, name, cusip, weight_pct, shares))."""
    text = body.decode("utf-8", "replace")
    m = re.search(r"Data as of (\d{2}/\d{2}/\d{4})", text)
    rows = []
    for tr in re.findall(r"<tr>(.*?)</tr>", text, flags=re.S):
        cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)]
        if len(cells) == 5:
            rows.append(dict(ticker=cells[0], name=cells[1], cusip=cells[2], weight_pct=_f(cells[3].rstrip("%")), shares=_f(cells[4])))
    return (m.group(1) if m else None), rows


def _f(x):
    try:
        return float(str(x).replace(",", "").replace("−", "-").strip()) if x not in (None, "") else None
    except ValueError:
        return None
