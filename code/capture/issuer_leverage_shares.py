"""Leverage Shares (leverageshares.com/us): server-rendered pages, read on 2026-10-23.

- daily: `/us/all-etfs/`, whose inline JavaScript product array lists every fund with ticker, leverage factor,
  underlying, NAV, market price, expense ratio and the fund page URL. One request gives the lineup and the day's
  NAV for every fund.
- weekly (Friday and month-end), per fund: the fund page named in that array; it renders NAV, market price,
  shares outstanding and the holdings table with their "As of" dates. Pages are 300 to 350 KB, stored compressed.
The holdings CSV under `/us/storage/holdings/<T>_Holdings.csv` was last written on 2026-08-24 for every fund
tested, so it is not captured: the page table is the current one.
"""
import re

from issuer_capture import is_html, spec

SOURCE = "leverage_shares"
LIST_URL = "https://leverageshares.com/us/all-etfs/"
PRODUCT_RE = re.compile(
    r'\{\s*name:\s*"(?P<name>.*?)",.*?ticker:\s*\'(?P<ticker>\w+)\',.*?leverage_factor:\s*\'(?P<lev>[^\']*)\',.*?'
    r'category2:\s*"(?P<under>.*?)",\s*nav:\s*\'(?P<nav>[^\']*)\',\s*price:\s*\'(?P<price>[^\']*)\',\s*'
    r'expense_ratio:\s*\'(?P<er>[^\']*)\',\s*product_url:\s*\'(?P<url>[^\']*)\'', re.S)


def plan(ctx):
    return [spec("all_etfs.html", LIST_URL, None, "daily", "list", valid=is_html)]


def followups(ctx, got):
    html = got.get("all_etfs.html")
    if html is None:
        return []
    urls = {p["ticker"]: p["product_url"] for p in parse_products(html)}
    out = []
    for f in ctx.funds:
        t = f["ticker"]
        if t in urls:
            out.append(spec(f"{t}_page.html", urls[t], None, "weekly", "page", ticker=t, valid=is_html))
    return out


def parse_products(body):
    """-> list of dict(ticker, name, leverage, underlying, nav, price, expense_ratio, product_url)."""
    text = body.decode("utf-8", "replace") if isinstance(body, bytes) else body
    out = []
    for m in PRODUCT_RE.finditer(text):
        d = m.groupdict()
        out.append(dict(ticker=d["ticker"], name=d["name"], leverage=d["lev"], underlying=re.sub(r"<sup>.*?</sup>", "", d["under"]),
                        nav=_f(d["nav"]), price=_f(d["price"]), expense_ratio=_f(d["er"]), product_url=d["url"]))
    return out


def parse_page(body):
    """Key facts from a fund page: as-of date, NAV, market price, shares outstanding, expense ratio, inception."""
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body.decode("utf-8", "replace") if isinstance(body, bytes) else body))

    def grab(label, pattern=r"\$?([\d,]+\.?\d*)"):
        m = re.search(re.escape(label) + r"\s*" + pattern, text)
        return m.group(1) if m else None

    prices = re.search(r"ETF Prices\s*As of (\d{2}/\d{2}/\d{4})", text)
    return dict(as_of=prices.group(1) if prices else None,
                nav=_f(grab("Net Asset Value (NAV)")), market_price=_f(grab("Market Price")),
                shares_outstanding=_f(grab("Shares Outstanding")), expense_ratio_pct=_f(grab("Total Expense Ratio", r"([\d.]+)%")),
                inception=grab("Inception Date", r"([A-Z][a-z]{2} \d{2}, \d{4})"))


def _f(x):
    try:
        return float(str(x).replace(",", "")) if x not in (None, "") else None
    except ValueError:
        return None
