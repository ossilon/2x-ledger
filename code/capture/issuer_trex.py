"""T-Rex (REX Shares, rexshares.com), read on 2026-10-23.

- weekly (Friday and month-end), per fund: the fund page `/<t>/`, server-rendered facts block (as-of date,
  NAV, closing price, premium, fund assets, shares outstanding, number of holdings, expense ratio, underlying);
  about 290 KB each, stored compressed;
- monthly, per fund: `/wp-content/themes/jupiter-child/assets/json/<t>_index.json` (daily returns since
  inception as [epoch ms, return] pairs).
The holdings table is loaded on a tab click and is not in the served HTML; no holdings file was found. No daily
file exists for T-Rex, so its shares outstanding are known weekly only (recorded in docs/issuer_sources_draft.md).
"""
import re

from issuer_capture import is_html, spec

SOURCE = "trex"
BASE = "https://www.rexshares.com"


def plan(ctx):
    out = []
    for f in ctx.funds:
        t = f["ticker"]
        out.append(spec(f"{t}_page.html", f"{BASE}/{t.lower()}/", None, "weekly", "page", ticker=t, valid=is_html))
        out.append(spec(f"{t}_index.json", f"{BASE}/wp-content/themes/jupiter-child/assets/json/{t.lower()}_index.json", b"[[", "monthly", "history", ticker=t))
    return out


def parse_page(body):
    """Facts block -> dict(as_of, nav, closing_price, premium_pct, fund_assets, shares_outstanding, expense_ratio_pct, underlying)."""
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body.decode("utf-8", "replace")))

    def grab(label, pattern=r"\$?([\d,]+\.?\d*)"):
        m = re.search(re.escape(label) + r"\s*" + pattern, text)
        return m.group(1) if m else None

    return dict(as_of=grab("As of", r"(\d{2}/\d{2}/\d{4})"), nav=_f(grab("NAV")), closing_price=_f(grab("Closing Price")),
                premium_pct=_f(grab("Discount/Premium", r"(-?[\d.]+)%")), fund_assets=_f(grab("Fund Assets")),
                shares_outstanding=_f(grab("Shares Outstanding")), expense_ratio_pct=_f(grab("Total Expense Ratio", r"([\d.]+)%")),
                underlying=grab("Underlying Ticker", r"([A-Z]{1,6})"))


def _f(x):
    try:
        return float(str(x).replace(",", "").strip()) if x not in (None, "") else None
    except ValueError:
        return None
