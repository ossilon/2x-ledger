"""GraniteShares (graniteshares.com), read on 2026-10-23.

Every fund page carries `var PRODUCT_ID = <n>` and the URLs of the data services it calls:
- daily, per fund: `/product/<id>/en-us/` JSON (NAV, AUM, closing price, premium, fee lines including the swap
  fee, listing date; the inner "Data" field is a JSON string);
- daily, per fund (follow-up): the holdings service, a POST with {"ticker": T, "dataDate": NavDate} that returns
  the positions (security, share, value, weight) for the NAV date read from the product JSON;
- monthly, per fund: the NAV history service (every NAV, closing price and AUM since inception);
- weekly, per fund: the fund page itself (the product id and the signed service URLs are re-read from it by
  scripts/universe_capture_local.py when funds change).
The product id per ticker comes from the universe file (column `slug`). The service URLs are signed Azure
logic-app triggers published in every page; a changed signature shows up as an HTTP error and a STOP.
"""
import json

from issuer_capture import is_html, spec

SOURCE = "graniteshares"
BASE = "https://graniteshares.com"
KNOCKOUT = "https://knockoutv2.azurewebsites.net/api/"
NAV_HISTORY_URL = (KNOCKOUT + "ProductNavHistory/triggers/When_a_HTTP_request_is_received/invoke/{id}"
                   "?api-version=2022-05-01&sp=%2Ftriggers%2FWhen_a_HTTP_request_is_received%2Frun&sv=1.0&sig=bH7VS-AEVsHFaoHEdwodgWM-T_MUr8kOaZi9St7whis")
HOLDINGS_URL = (KNOCKOUT + "ProductHoldings/triggers/When_a_HTTP_request_is_received/invoke"
                "?api-version=2022-05-01&sp=%2Ftriggers%2FWhen_a_HTTP_request_is_received%2Frun&sv=1.0&sig=HVz3V8DcFoMg1DMwf2gc_2e24Bg_4xZD3abCZiBly6M")
FORMATS = {"product": [("v1", b'{"odata.etag"')], "nav_history": [("v1", b'[{"PriceHistoryId"')], "holdings": [("v1", b"[")]}


def plan(ctx):
    out = []
    for f in ctx.funds:
        t, pid = f["ticker"], f.get("slug")
        if not pid:
            ctx.notes.append(f"graniteshares {t}: no product id in the universe file (slug column); nothing fetched. Run scripts/universe_capture_local.py --refresh-ids")
            continue
        out.append(spec(f"{t}_product.json", f"{BASE}/product/{pid}/en-us/", b'{"odata.etag"', "daily", "nav", ticker=t))
        out.append(spec(f"{t}_nav_history.json", NAV_HISTORY_URL.format(id=pid), b'[{"PriceHistoryId"', "monthly", "history", ticker=t))
        out.append(spec(f"{t}_page.html", f"{BASE}/etfs/{t.lower()}/", None, "weekly", "page", ticker=t, valid=is_html))
    return out


def followups(ctx, got):
    out = []
    for f in ctx.funds:
        t = f["ticker"]
        body = got.get(f"{t}_product.json")
        if body is None:
            continue
        nav_date = parse_product(body).get("nav_date")
        if nav_date:
            payload = json.dumps({"ticker": t, "dataDate": nav_date}).encode()
            out.append(spec(f"{t}_holdings.json", HOLDINGS_URL, b"[", "daily", "holdings", method="POST", body=payload, ticker=t))
    return out


def parse_product(body):
    """-> dict(ticker, name, nav_date (YYYY-MM-DD), nav, aum, closing_price, premium, fees_pct, swap_fees, listing_date)."""
    j = json.loads(body)
    d = json.loads(j["Data"]) if isinstance(j.get("Data"), str) else (j.get("Data") or {})
    nav_date = (d.get("NavDate") or "")[:10] or None
    return dict(ticker=d.get("Ticker"), name=d.get("ProductName"), nav_date=nav_date, nav=d.get("Nav"), aum=d.get("AUM"),
                closing_price=d.get("ClosingPrice"), premium=d.get("Discount"), fees_pct=d.get("Fees"),
                management_fee=d.get("ManagementFees"), swap_fees=d.get("SwapFees"), listing_date=(d.get("ListingDate") or "")[:10] or None)


def parse_nav_history(body):
    """-> list of dict(date, nav, closing_price, aum) oldest first."""
    return [dict(date=r["PriceDate"], nav=r.get("Price"), closing_price=r.get("ClosingPrice"), aum=r.get("AUM")) for r in json.loads(body)]
