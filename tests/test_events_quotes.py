"""Yahoo event files and quote snapshots: synthetic replies in a temp folder (no network)."""
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from _harness import check, raises
import yahoo_events as ye
import quotes as qt
import tv_capture as tc
from captured_by import captured_by

root = Path(tempfile.mkdtemp(prefix="ledger_events_"))
TZ = "America/New_York"


def ts(day, hour=9, minute=30):
    return int(pd.Timestamp(f"{day} {hour:02d}:{minute:02d}", tz=TZ).timestamp())


def yahoo_reply(ticker, days, closes, dividends=(), splits=()):
    """Mimic the Yahoo chart JSON: timestamps, quote closes, adjclose, events."""
    adj = list(closes)
    res = {"meta": {"symbol": ticker, "exchangeTimezoneName": TZ, "dataGranularity": "1d"},
           "timestamp": [ts(d) for d in days],
           "indicators": {"quote": [{"close": closes, "open": closes, "high": [c * 1.01 for c in closes],
                                     "low": [c * 0.99 for c in closes], "volume": [1000] * len(closes)}],
                          "adjclose": [{"adjclose": adj}]},
           "events": {}}
    if dividends:
        res["events"]["dividends"] = {str(ts(d)): {"amount": a, "date": ts(d)} for d, a in dividends}
    if splits:
        res["events"]["splits"] = {str(ts(d)): {"numerator": n, "denominator": m, "splitRatio": f"{n}:{m}", "date": ts(d)}
                                   for d, n, m in splits}
    return json.dumps({"chart": {"result": [res], "error": None}}).encode("utf-8")


days = [str(d.date()) for d in pd.bdate_range("2024-01-02", periods=40)]
closes = [100.0 * 1.01 ** i for i in range(40)]

# store a synthetic Yahoo file by hand through the same path fetch() uses (no network): monkeypatch fy.fetch
raw = yahoo_reply("TST", days, closes, dividends=[(days[10], 0.25), (days[30], 0.30)], splits=[(days[20], 10, 1)])
ye.port.yahoo_fetch = lambda sym, end: raw
rec = ye.fetch("NASDAQ:TST", root=root, now=datetime(2024, 3, 1, 22, 0, tzinfo=timezone.utc))
check("yahoo fetch stores the file and counts events", rec["rows"] == 40 and rec["dividends"] == 2 and rec["splits"] == 1, rec)
check("yahoo manifest path is under the UTC date", rec["path"].startswith("2024-03-01/"), rec["path"])
div, spl = ye.events("NASDAQ:TST", root=root)
check("dividend events come back as dated amounts", len(div) == 2 and float(div["amount"].iloc[0]) == 0.25 and str(div["date"].iloc[0].date()) == days[10])
check("split events carry numerator and denominator", len(spl) == 1 and int(spl["numerator"].iloc[0]) == 10 and str(spl["date"].iloc[0].date()) == days[20])
cl = ye.closes("NASDAQ:TST", root=root)
check("closes are indexed by session date", len(cl) == 40 and str(cl.index[0].date()) == days[0])

# captured_by hides the Yahoo file
with captured_by("2024-02-01T00:00:00Z"):
    raises("captured_by before the Yahoo fetch hides it", lambda: ye.events("NASDAQ:TST", root=root), "no Yahoo file")

# crosscheck against a TradingView series built in the same temp root
bars = []
prev = closes[0] / 1.01
for d, c in zip(days, closes):
    bars.append({"t": ts(d), "o": prev, "h": max(prev, c) * 1.001, "l": min(prev, c) * 0.999, "c": c, "v": 500})
    prev = c
bars[5]["c"] = bars[5]["c"] * 1.004                  # one TradingView close 0.4% off Yahoo
bars[5]["h"] = max(bars[5]["o"], bars[5]["c"]) * 1.001
summary = {"first_t": bars[0]["t"], "last_t": bars[-1]["t"], "first_open": bars[0]["o"], "last_close": bars[-1]["c"],
           "high": max(b["h"] for b in bars), "low": min(b["l"] for b in bars), "total_volume": sum(b["v"] for b in bars)}
reply = {"success": True, "symbol": "NASDAQ:TST", "interval": "1D", "format": "rows", "count": 40, "has_more": False,
         "bars": bars, "summary": summary}
inbox = root / "inbox"
inbox.mkdir()
(inbox / "tst.json").write_text(json.dumps(reply), encoding="utf-8")
tc.ingest(inbox / "tst.json", root=root, fetched_utc="2024-03-01T22:00:00Z")
tc.build("NASDAQ:TST", root=root)
cc = ye.crosscheck("NASDAQ:TST", root=root)
check("crosscheck finds the one planted 0.4% disagreement", cc["common_days"] == 40 and cc["days_over_tol"] == 1 and cc["worst"][0][0] == days[5], cc)

# point in time for prices: total_return.bars rebuilds from raw under the cutoff instead of reading the series file
import total_return as trm
check("bars under a cutoff after the fetch gives the series", len(trm.bars("NASDAQ:TST", root=root, cutoff="2024-03-02T00:00:00Z")) == 40)
raises("bars under a cutoff before the fetch sees nothing, even though the series file exists", lambda: trm.bars("NASDAQ:TST", root=root, cutoff="2024-02-01T00:00:00Z"), "full-history")

# quotes snapshot
q = {"count": 2, "success": True, "missing": [],
     "data": {"NASDAQ:TST": {"brand": "Issuer", "expense_ratio": 0.95, "aum": 1.0e8, "nav": 10.0, "nav_discount_premium": 0.1,
                             "fund_flows.1M": 5.0e6, "dividends_yield": 3.9},
              "NASDAQ:A": {"brand": None, "expense_ratio": None, "aum": None, "nav": None, "nav_discount_premium": None,
                           "fund_flows.1M": None, "dividends_yield": 0.3}}}
(inbox / "q.json").write_text(json.dumps(q), encoding="utf-8")
qrec = qt.ingest(inbox / "q.json", root=root, fetched_utc="2024-03-01T22:30:00Z")
check("quote snapshot is stored with its symbol count", qrec["symbols"] == 2, qrec)
qrec2, qdf = qt.latest(root=root)
check("latest snapshot loads as a frame indexed by symbol", float(qdf.at["NASDAQ:TST", "expense_ratio"]) == 0.95 and pd.isna(qdf.at["NASDAQ:A", "aum"]))
bad = dict(q, count=3)
(inbox / "qbad.json").write_text(json.dumps(bad), encoding="utf-8")
raises("a snapshot whose count disagrees with its data is refused", lambda: qt.ingest(inbox / "qbad.json", root=root, fetched_utc="2024-03-01T22:31:00Z"), "count")
with captured_by("2024-02-01T00:00:00Z"):
    raises("captured_by before the snapshot hides it", lambda: qt.latest(root=root), "no quote snapshot")

shutil.rmtree(root, ignore_errors=True)
