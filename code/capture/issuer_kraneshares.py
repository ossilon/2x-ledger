"""KraneShares (kraneshares.com), read on 2026-10-23.

- dated, per fund: `/csv/MM_DD_YYYY_<t>_holdings.csv` (the issuer names holdings files by date; recent weekdays
  that have no saved copy are asked for on every run);
- daily, per fund: the fund page `/etf/<t>/`, server-rendered "Fund Details" (net assets, shares outstanding,
  expense ratios, inception) and the daily performance block. Five funds, so the pages are captured daily.
"""
import re

from issuer_capture import is_html, published_at, spec, weekdays_back

SOURCE = "kraneshares"
BASE = "https://kraneshares.com"
HOLDINGS_HOUR_UTC = 8      # the file for a close was linked the next morning (the 10-22 file on 10-23; 10-23's absent at 20:00 UTC)


def plan(ctx):
    out = []
    for f in ctx.funds:
        t = f["ticker"]
        for d in weekdays_back(ctx.today):
            out.append(spec(f"{t}_holdings_{d:%Y-%m-%d}.csv", f"{BASE}/csv/{d:%m_%d_%Y}_{t.lower()}_holdings.csv", None, "dated", "holdings",
                            ticker=t, date=d, ready_utc=published_at(d, HOLDINGS_HOUR_UTC, next_day=True)))
        out.append(spec(f"{t}_page.html", f"{BASE}/etf/{t.lower()}/", None, "daily", "page", ticker=t, valid=is_html))
    return out


def parse_page(body):
    """Fund Details block -> dict(as_of, net_assets, shares_outstanding, expense_gross_pct, expense_net_pct, inception)."""
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body.decode("utf-8", "replace")))
    i = text.find("Fund Details")
    block = text[i:i + 1200] if i >= 0 else text

    def grab(label, pattern=r"\$?([\d,]+\.?\d*)"):
        m = re.search(re.escape(label) + r"\s*" + pattern, block)
        return m.group(1) if m else None

    return dict(as_of=grab("Data as of", r"(\d{1,2}/\d{1,2}/\d{4})"), net_assets=_f(grab("Net Assets")),
                shares_outstanding=_f(grab("Shares Outstanding")),
                expense_gross_pct=_f(grab("Total Annual Fund Operating Expense (Gross)", r"([\d.]+)%")),
                expense_net_pct=_f(grab("Total Annual Fund Operating Expense (Net)", r"([\d.]+)%")),
                inception=grab("Inception Date", r"(\d{1,2}/\d{1,2}/\d{4})"))


def _f(x):
    try:
        return float(str(x).replace(",", "").strip()) if x not in (None, "") else None
    except ValueError:
        return None
