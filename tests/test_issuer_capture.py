"""Issuer capture: storage rules, cadence, STOP lines, follow-ups and every adapter's parser on planted bytes."""
import gzip
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from _harness import check, raises
import issuer_capture as ic
import issuer_corgi, issuer_defiance, issuer_direxion, issuer_graniteshares, issuer_kraneshares  # noqa: E401
import issuer_leverage_shares, issuer_proshares, issuer_tradr, issuer_trex  # noqa: E401
import port

FRI = datetime(2026, 10, 23, 23, 45, tzinfo=timezone.utc)      # a Friday
MON = datetime(2026, 10, 26, 23, 45, tzinfo=timezone.utc)
root = Path(tempfile.mkdtemp(prefix="ledger_issuers_"))

# ---------- 1. storage ----------
small = b"Date,Account\n1,2\n"
big = b"X" * (ic.GZIP_MIN + 10)
sp_small = ic.spec("s.csv", "https://x/s.csv", b"Date,Account", "daily", "nav")
sp_big = ic.spec("b.csv", "https://x/b.csv", None, "daily", "nav")


def getter_ok(url, method="GET", body=None):
    return 200, {"Last-Modified": "Thu, 22 Oct 2026 22:00:00 GMT", "Content-Type": "text/csv"}, (big if url.endswith("b.csv") else small)


recs = []
r1 = ic.store(sp_small, "src", root, FRI, recs, getter=getter_ok)
recs.append(r1)
check("a small body is saved raw with its sha256 and byte count", r1["result"] == "saved" and r1["sha256"] == port.sha256(small) and r1["bytes"] == len(small) and "encoding" not in r1, r1)
check("the saved path sits under raw/<source>/<UTC date>/", r1["path"] == "raw/src/2026-10-23/s.csv", r1["path"])
r2 = ic.store(sp_small, "src", root, FRI.replace(minute=50), recs, getter=getter_ok)
recs.append(r2)
check("identical bytes are recorded as unchanged and not saved again", r2["result"] == "unchanged" and r2["same_as"] == r1["path"])
r3 = ic.store(sp_big, "src", root, FRI, recs, getter=getter_ok)
recs.append(r3)
check("a big body is stored gzip-compressed; sha256 and bytes describe the raw body", r3["result"] == "saved" and r3.get("encoding") == "gzip" and r3["path"].endswith(".gz") and r3["sha256"] == port.sha256(big) and r3["bytes"] == len(big) and r3["stored_bytes"] < len(big), r3)
check("read_raw returns the decompressed bytes", ic.read_raw(root, r3) == big)
check("latest_bytes finds the newest saved copy", ic.latest_bytes(root, recs, "src", "b.csv") == big and ic.latest_bytes(root, recs, "src", "nope") is None)
r4 = ic.store(sp_big, "src", root, FRI.replace(minute=50), recs, getter=getter_ok)
recs.append(r4)
check("a compressed file is also recognized as unchanged on the next fetch", r4["result"] == "unchanged")


def getter_page(url, method="GET", body=None):
    return 200, {"Content-Type": "text/html"}, b"<html>maintenance</html>"


r5 = ic.store(sp_small, "src", root, FRI.replace(minute=51), recs, getter=getter_page)
recs.append(r5)
check("a body with the wrong header is saved for inspection and marked invalid", r5["result"] == "invalid" and r5["path"] == "raw/src/2026-10-23/s__235100.csv", r5)
r6 = ic.store(sp_small, "src", root, FRI.replace(minute=52), recs, getter=getter_page)
recs.append(r6)
check("the same wrong body again is invalid_repeat, not saved twice", r6["result"] == "invalid_repeat" and "path" not in r6)
r7 = ic.store(sp_small, "src", root, FRI.replace(minute=53), recs, getter=lambda u, m="GET", b=None: (503, {}, b""))
recs.append(r7)
check("a non-200 status is an http_error with the status recorded", r7["result"] == "http_error" and r7["status"] == 503)


def getter_boom(url, method="GET", body=None):
    raise OSError("dns failed")


r8 = ic.store(sp_small, "src", root, FRI.replace(minute=54), recs, getter=getter_boom)
check("a network exception becomes a network_error record, never an exception", r8["result"] == "network_error" and "dns failed" in r8["error"])
sp_post = ic.spec("h.json", "https://x/h", b"[", "daily", "holdings", method="POST", body=b'{"ticker": "NVDL", "dataDate": "2026-10-22"}')
seen = {}


def getter_post(url, method="GET", body=None):
    seen["method"], seen["body"] = method, body
    return 200, {}, b'[{"security": "NVDA SWAP"}]'


r9 = ic.store(sp_post, "src", root, FRI, recs, getter=getter_post)
recs.append(r9)
check("a POST spec sends its method and body and records the body", seen["method"] == "POST" and seen["body"] == sp_post["body"] and r9["body"].startswith('{"ticker"') and r9["result"] == "saved")
sp_post2 = ic.spec("h.json", "https://x/h", b"[", "daily", "holdings", method="POST", body=b'{"ticker": "AAPB", "dataDate": "2026-10-22"}')
r10 = ic.store(sp_post2, "src", root, FRI.replace(minute=55), recs, getter=getter_post)
check("the same URL with a different POST body is a different file, not unchanged", r10["result"] == "saved", r10)
check("the manifest holds one line per fetch", len(port.read_manifest(root)) == 10)
ok_same_second = ic.store(ic.spec("twice.csv", "https://x/twice", None), "src", root, FRI, [], getter=lambda u, m="GET", b=None: (200, {}, b"A"))
ok_same_second2 = ic.store(ic.spec("twice.csv", "https://x/twice", None), "src", root, FRI, [], getter=lambda u, m="GET", b=None: (200, {}, b"B"))
check("two different bodies in the same second never overwrite each other", ok_same_second["path"] != ok_same_second2["path"] and (root / ok_same_second["path"]).read_bytes() == b"A")

# ---------- 2. cadence ----------
raises("a dated spec without a date is refused", lambda: ic.spec("x", "u", None, "dated"), "needs its date")
check("daily is always due", ic.due([], "s", ic.spec("a", "u", None, "daily"), MON))
wk = ic.spec("w", "u", None, "weekly")
check("weekly is due on a Friday", ic.due([], "s", wk, FRI))
recent = [{"source": "s", "name": "w", "result": "saved", "fetched_utc": "2026-10-23T23:45:00Z"}]
check("weekly is not due on a Monday with a copy from Friday", not ic.due(recent, "s", wk, MON))
check("weekly is due on the last weekday of the month", ic.due(recent, "s", wk, datetime(2026, 10, 30, 23, 0, tzinfo=timezone.utc)))
check("weekly is due again once the last copy is over 7 days old", ic.due(recent, "s", wk, datetime(2026, 11, 3, 23, 0, tzinfo=timezone.utc)))
mo = ic.spec("m", "u", None, "monthly")
old = [{"source": "s", "name": "m", "result": "unchanged", "fetched_utc": "2026-10-01T23:45:00Z"}]
check("monthly is not due 22 days after an unchanged copy", not ic.due(old, "s", mo, FRI))
check("monthly is due 26 days after the last copy", ic.due(old, "s", mo, datetime(2026, 10, 27, 23, 0, tzinfo=timezone.utc)))
dt = ic.spec("d.csv", "u", None, "dated", date=datetime(2026, 10, 20).date())
check("a dated file is due until saved", ic.due([], "s", dt, FRI))
check("a dated file is not due once saved", not ic.due([{"source": "s", "name": "d.csv", "result": "saved", "fetched_utc": "x"}], "s", dt, FRI))
fails = [{"source": "s", "name": "d.csv", "result": "http_error", "fetched_utc": "x"}]
check("a failing dated file is retried within the give-up window", ic.due(fails, "s", dt, FRI))
check("a failing dated file is given up after GIVE_UP_DAYS", not ic.due(fails, "s", dt, datetime(2026, 10, 30, 23, 0, tzinfo=timezone.utc)))
check("weekdays_back lists weekdays oldest first and ends today", ic.weekdays_back(MON.date(), 5) == [datetime(2026, 10, 21).date(), datetime(2026, 10, 22).date(), datetime(2026, 10, 23).date(), MON.date()])
ready = ic.spec("r.csv", "u", None, "dated", date=MON.date(), ready_utc=ic.published_at(MON.date(), 23))
check("a dated file is not due before the issuer publishes it", not ic.due([], "s", ready, MON.replace(hour=22)) and ic.due([], "s", ready, MON.replace(hour=23, minute=1)))
check("published_at next_day gives the morning after", ic.published_at(MON.date(), 8, next_day=True) == datetime(2026, 10, 27, 8, tzinfo=timezone.utc))
badu = root / "bad_universe.csv"
badu.write_text("issuer_key,issuer,ticker,underlying,slug,status,capture\nleverageshares,Leverage Shares,METG,META,,VERIFIED,1\n", encoding="utf-8")
raises("a misspelled issuer_key is refused with the ticker named", lambda: ic.load_universe(badu), "unknown issuer_key 'leverageshares' for METG")
idx = ic.Index([{"url": "u", "body": None, "source": "s", "name": "a", "result": "saved", "fetched_utc": "x"}])
check("Index groups by request and by file", len(idx.same_request(ic.spec("a", "u", None))) == 1 and len(idx.file("s", "a")) == 1 and idx.file("s", "zz") == [])
check("last_weekday_of_month knows 2026-10-30 (Friday) and not 10-29", ic.last_weekday_of_month(datetime(2026, 10, 30).date()) and not ic.last_weekday_of_month(datetime(2026, 10, 29).date()))

# ---------- 3. a full run over every adapter with planted bodies ----------
UNIVERSE = root / "universe.csv"
UNIVERSE.write_text("issuer_key,issuer,ticker,underlying,slug,status,capture\n"
                    "corgi,Corgi,AXTC,AXTI,,VERIFIED,1\ncorgi,Corgi,SKIP,SKIP,,VERIFIED,0\n"
                    "leverage_shares,Leverage Shares,METG,META,,VERIFIED,1\n"
                    "defiance,Defiance,MSTX,MSTR,,PILOT,1\n"
                    "graniteshares,GraniteShares,NVDL,NVDA,1088,PILOT,1\n"
                    "direxion,Direxion,TSLL,TSLA,,PILOT,1\n"
                    "kraneshares,KraneShares,KBAB,BABA,,VERIFIED,1\n"
                    "trex,T-Rex,NVDX,NVDA,,PILOT,1\n", encoding="utf-8")
uni = ic.load_universe(UNIVERSE)
check("load_universe groups by issuer and drops capture=0 rows", [f["ticker"] for f in uni["corgi"]] == ["AXTC"] and uni["tradr"] == [] and uni["graniteshares"][0]["slug"] == "1088")

LS_LIST = (b"<!DOCTYPE html><html><script>var products = [{ name: \"2x Long META Daily ETF\", product_logo: 'x.svg', ticker: 'METG', externalLink: false, "
           b"leverage_factor: '2', leverage_factor_label: \"2x Daily\", fund: \"2x Long META Daily ETF\", category: \"Leveraged\", category2: \"META\", nav: '15.81', price: '15.78', "
           b"expense_ratio: '0.75', product_url: 'https://leverageshares.com/us/etfs/leverage-shares-2x-long-meta-daily-etf', is_api_product: false },"
           b"{ name: \"2x Long Memory Daily ETF\", product_logo: 'y.svg', ticker: 'RAML', externalLink: false, leverage_factor: '2', leverage_factor_label: \"2x Daily\", "
           b"fund: \"x\", category: \"Leveraged\", category2: \"DRAM<sup>1</sup>\", nav: '7.87', price: '7.97', expense_ratio: '0.99', product_url: 'https://leverageshares.com/us/etfs/leverage-shares-2x-long-memory-daily-etf' }];</script></html>")
LS_PAGE = (b"<!DOCTYPE html><html><body><h2>Key Information</h2><p>As of 10/23/2026</p><dt>Inception Date</dt><dd>Jul 02, 2026</dd><dt>Total Expense Ratio</dt><dd>0.75%</dd>"
           b"<dt>Net Asset Value (NAV)</dt><dd>$15.81</dd><dt>Shares Outstanding</dt><dd>120,000</dd><h3>ETF Prices</h3><p>As of 10/22/2026</p><dt>NAV</dt><dd>$15.81</dd>"
           b"<dt>Market Price</dt><dd>$15.78</dd></body></html>")
CORGI_SUMMARY = (b'{"ticker":"AXTC","canonical_fund_id":null,"latest_nav":"8.2642","latest_nav_date":"2026-10-22","latest_aum":"495852.00","latest_aum_date":"2026-10-22",'
                 b'"latest_market_price":"8.2861","latest_premium_discount_pct":"0.2650","latest_median_30_day_spread_pct":"0.6200","latest_holdings_date":"2026-10-22","holdings_count":2}')
CORGI_HOLD = b'[{"position_date":"2026-10-23","security_name":"AXT, INC.-SWAP-CANT-L","weight_pct":"198.9100","market_value":"986291.24","shares":"19129.0","net_assets":"495852.00","as_of_date":"2026-10-22"}]'
DEF_EXPLORE = b'[{"ticker":"MSTX","name":"Defiance Daily Target 2X Long MSTR ETF","category":"leveraged-long","url":"u","rate_date":"2026-10-22","nav":15.72,"market_price":15.72,"net_assets":325900000,"premium_discount":-0.03}]'
DEF_PAGE = (b"<!DOCTYPE html><html><body>Fund Details Data as of 10/22/2026 Net Assets $325.90M Premium/Discount -0.03% NAV $15.72 Closing Price $15.72 "
            b"Shares Outstanding 20,725,464 Median 30 Day Spread 0.11% Fund Inception 08/14/2024 Ticker MSTX Gross Expense Ratio 1.31%</body></html>")
DEF_HOLD = (b"<!doctype html><html><body><table id=\"table-full-holdings\"><tr><th>Ticker</th><th>Name</th><th>CUSIP</th><th>ETF Weight</th><th>Shares</th></tr>"
            b"<tr><td>594972408-TRS-11/09/27-L-MSTX</td><td>Strategy Inc Swap Clearstreet</td><td>594972408-TRS</td><td>43.50%</td><td>941,414</td></tr>"
            b"<tr><td>Cash&amp;Other</td><td>Cash &amp; Other</td><td>Cash&amp;Other</td><td>-141.06%</td><td>-445,080,503</td></tr></table><p>Data as of 10/23/2026.</p></body></html>")
GS_PRODUCT = (b'{"odata.etag":"W/x","RowKey":"1088","Data":"{\\"Ticker\\":\\"NVDL\\",\\"ProductName\\":\\"GraniteShares 2x Long NVDA Daily ETF\\",\\"AUM\\":6386742825.93,\\"Nav\\":138.5,'
              b'\\"ClosingPrice\\":138.4,\\"NavDate\\":\\"2026-10-22T00:00:00\\",\\"Discount\\":-0.0007,\\"Fees\\":9.03,\\"ManagementFees\\":0.0099,\\"SwapFees\\":4.1,\\"ListingDate\\":\\"2022-12-13T00:00:00\\"}"}')
GS_HIST = b'[{"PriceHistoryId":1,"ProductId":1088,"Price":1.38817125,"PriceDate":"2022-12-12","AUM":0.0,"ClosingPrice":1.38817125},{"PriceHistoryId":2,"ProductId":1088,"Price":1.45,"PriceDate":"2022-12-13","AUM":784297.62,"ClosingPrice":1.4531}]'
GS_HOLD = b'[{"security":"NVDA SWAP","share":"30096333","value":"6386742825.93","weight":1.999538},{"security":"US Dollars","share":"3194108640.5","value":"3194108640.5","weight":1.0}]'
DIREXION = (b'Direxion Daily TSLA Bull 2X ETF\r\nTSLL\r\nShares Outstanding:352150001\r\n\r\n\r\n"TradeDate","AccountTicker","StockTicker","SecurityDescription","Shares","Price","MarketValue","Cusip","HoldingsPercent"\r\n'
            b'"10/23/2026 12:00:00 AM","TSLL","","DREYFUS GOVT CASH MAN INS","785594647.5000","1.0000","785594647.5000","X9USDDGCM","22.5575073136"\r\n'
            b'"10/23/2026 12:00:00 AM","TSLL","TSLA","TESLA INC SWAP","1000.0000","2.0000","2000.0000","88160R101","0.0001"\r\n')
KRANE_PAGE = (b"<!DOCTYPE html><html><body>Fund Details Data as of 10/22/2026 Ticker KBAB Primary Exchange NASDAQ CUSIP 500767280 Net Assets $2,900,297 Shares Outstanding 450,002 "
              b"Total Annual Fund Operating Expense (Gross) 1.26% Total Annual Fund Operating Expense (Net) 0.99%* Inception Date 3/11/2025</body></html>")
TREX_PAGE = (b"<!DOCTYPE html><html><body>Ticker NVDX CUSIP 26923N819 Fund Inception 10/19/2023 As of 10/22/2026 NAV $17.6 NAV Change ($) $-1.7 Closing Price $17.62 "
             b"Median Bid/Ask Spread 0.05% Discount/Premium 0.139800% Fund Assets $346,937,800.00 Shares Outstanding 19,690,000 Number of Holdings 11 Total Expense Ratio 1.05% Underlying Ticker NVDA</body></html>")
ICE = (b"Trade Date,Symbol,Name,CUSIP,ISIN,Primary Exchange,Currency,Consolidated Volume,Primary Exchange Volume,Consolidated High Price,Consolidated Low Price,Consolidated Close Price\n"
       b"20261022,AAOX,Tradr 2X Long AAOI Daily ETF,46152A429,US46152A4296,Z,USD,24498989,4675731,4.47,3.60,3.82\n")
BBH = (b"ETF Ticker,Date,ISIN,CUSIP,SEDOL,Ticker,Description,Security Type,Market Value,Maturity Date,Shares,Security Price,Asset Currency,Shares Outstanding,Total Net Assets,Market Value Weight\n"
       b"NXTE,10/22/2026,US8740391003,874039100,2113382,TSM,TAIWAN SEMICONDUCTOR-SP ADR,COMMON STOCK,5583631.35,,13541,412.35,USD,1090000,46617364.76,11.98%\n")
PSH_NAV = (b"Date,ProShares Name,Ticker,NAV,Prior NAV,NAV Change (%),NAV Change ($),Shares Outstanding (000),Assets Under Management\n"
           b"10/22/2026,ProShares Ultra CRCL,CRCA,18.6378,20.0283,-6.94268,-1.3905,5815.91,108395692.8468\n10/22/2026,ProShares Big Data Refiners ETF,DAT,53.5,53.49,0.002,0.001,100,5350143.5\n")
PSH_HOLD = (b"PORTFOLIO HOLDINGS INFORMATION,,,,\nAS OF 10/22/2026,,,,\n"
            b'"CRCA","ProShares Ultra CRCL","","","CIRCLE INTERNET  (CRCL) SWAP BANK OF AMERICA NA",,,381678,33060948.36,,\n')
PSH_SPLITS = b"Symbol,Name,Pre Split Cusip,Post Split Cusip,Split Type,Ratio,Date of Split\nCRCA,Ultra CRCL,74349Y431,74350P543,Reverse,10,02/26/2026\n"

BODIES = {
    "corgiinvest.com/api/data/funds/AXTC/summary": CORGI_SUMMARY, "holdings?ticker=AXTC": CORGI_HOLD, "AXTC/daily-nav": b'[{"rate_date":"2026-07-06","nav":"25.0000","net_assets":"25.00","market_price":"25.0000","premium_discount_percentage":"0.0000"}]',
    "corgiinvest.com/api/data/funds": b'{"funds":[{"ticker":"AXTC","name":"Corgi AXTI 2x Daily ETF","category":"2x Single Stock","underlyingTicker":"AXTI","inceptionDate":"2026-07-07","expenseRatio":"0.45%","leverageFactor":2.0}]}',
    "all-etfs": LS_LIST, "2x-long-meta": LS_PAGE, "etfs-explore": DEF_EXPLORE, "defianceetfs.com/mstx/": DEF_PAGE, "mstx-full-holdings": DEF_HOLD,
    "product/1088": GS_PRODUCT, "ProductNavHistory": GS_HIST, "ProductHoldings": GS_HOLD, "graniteshares.com/etfs/nvdl/": b"<!doctype html><html>var PRODUCT_ID = 1088;</html>",
    "holdings/TSLL.csv": DIREXION, "kraneshares.com/etf/kbab/": KRANE_PAGE, "_kbab_holdings.csv": b"Ticker,Name\nBABA,Alibaba\n",
    "rexshares.com/nvdx/": TREX_PAGE, "nvdx_index.json": b"[[1697587200000,0],[1697673600000,0.1194]]",
    "psdlyhld.csv": PSH_HOLD, "etf_splits.csv": PSH_SPLITS, "historical_nav.csv": PSH_NAV, "etf_performance.csv": b"Fund Name,Fund Symbol,Return Type\nUltra CRCL,CRCA,NAV\n",
    "Tradr_Exposure_History.csv": b"DATE,AAOX\n8/30/2024,0\n", "AXS_PREMIUM_DISCOUNT.CSV": b"KNO,7/7/2015,25.0000,25.0000,0.00\n", "AXS_Dividend_History.csv": b"Fund,Year\nNVDS,2022\n",
    "AXS_ETF_Performance.csv": b"<CONFLUENCE_TRANSFORMER>\n",
}
calls = []


def fake_getter(url, method="GET", body=None):
    calls.append((method, url, body))
    if "NSDEAXS2." in url:
        return (200, {}, b'"30 Day Effective Yield","30 Day Yield"\n"0","0"\n') if "10232026" in url or "10222026" in url else (404, {}, b"")
    if "ICE_ETP_AXS" in url:
        return (200, {}, ICE) if "20261022" in url else (404, {}, b"")
    if "BBH_AXS" in url:
        return (200, {}, BBH) if "20261022" in url else (404, {}, b"")
    if "_kbab_holdings.csv" in url and "10_22_2026" not in url and "10_23_2026" not in url:
        return 404, {}, b""
    for key, b in BODIES.items():
        if key in url:
            return 200, {"Content-Type": "application/octet-stream"}, b
    return 404, {}, b""


root2 = Path(tempfile.mkdtemp(prefix="ledger_issuers_run_"))
records, stops, notes = ic.run(root2, uni, now=FRI, getter=fake_getter, sleep=lambda: None)
results = {r["result"] for r in records}
check("a full Friday run over every adapter fetches without STOP on complete planted sources", stops == [], stops)
names = {(r["source"], r["name"]) for r in records if r["result"] == "saved"}
check("Corgi: summary, holdings, daily-nav history and the fund list were saved", {("corgi", "AXTC_summary.json"), ("corgi", "AXTC_holdings.json"), ("corgi", "AXTC_daily_nav.json"), ("corgi", "funds.json")} <= names, sorted(n for s, n in names if s == "corgi"))
check("Corgi: the capture=0 fund was not fetched", not any("SKIP" in r["name"] for r in records))
check("Leverage Shares: the fund page was found through the list page (follow-up) on a Friday", ("leverage_shares", "METG_page.html") in names)
check("GraniteShares: the holdings POST used the NavDate from the product JSON", any(m == "POST" and b == b'{"ticker": "NVDL", "dataDate": "2026-10-22"}' for m, u, b in calls))
check("Tradr: the three dated files for 10-22 were saved; 10-23's ICE file (published next morning) was not asked for yet", ("tradr", "ICE_ETP_AXS_Premium_0130_20261022.csv") in names and ("tradr", "BBH_AXS_ETF_PVAL_WEB.20261022.csv") in names and not any("ICE_ETP_AXS_Premium_0130_20261023" in n for n in notes), notes)
check("Tradr: 10-23's accounting file (published after 23:00 UTC) was fetched by the 23:45 run", ("tradr", "NSDEAXS2.10232026.csv") in names)
check("ProShares: daily holdings and splits plus the monthly history were saved", {("proshares", "psdlyhld.csv"), ("proshares", "etf_splits.csv"), ("proshares", "historical_nav.csv")} <= names)
check("Defiance, Direxion, KraneShares and T-Rex files were saved", {("defiance", "etfs_explore.json"), ("defiance", "MSTX_holdings.html"), ("direxion", "TSLL_holdings.csv"), ("kraneshares", "KBAB_page.html"), ("trex", "NVDX_page.html"), ("trex", "NVDX_index.json")} <= names, sorted(names))
check("every saved record carries kind and cadence", all("kind" in r and "cadence" in r for r in records))
calls.clear()
records2, stops2, notes2 = ic.run(root2, uni, now=MON, getter=fake_getter, sleep=lambda: None)
check("a Monday run skips the weekly pages saved on Friday and the monthly histories", not any(r["name"] in ("METG_page.html", "historical_nav.csv", "AXTC_daily_nav.json") for r in records2), [r["name"] for r in records2])
check("a Monday run records the daily files as unchanged", all(r["result"] == "unchanged" for r in records2 if r["name"] in ("AXTC_summary.json", "psdlyhld.csv", "TSLL_holdings.csv")))
tradr_fails = [r for r in records2 if r["source"] == "tradr" and r["result"] == "http_error"]
check("Tradr: files already saved are not asked for again; missing recent dates are", not any("20261022" in r["name"] for r in tradr_fails) and tradr_fails)


def broken_getter(url, method="GET", body=None):
    if "psdlyhld" in url:
        return 200, {}, b"<html>maintenance</html>"
    if "holdings/TSLL.csv" in url:
        return 500, {}, b""
    return fake_getter(url, method, body)


records3, stops3, notes3 = ic.run(root2, {"proshares": [], "direxion": uni["direxion"], "tradr": []}, now=MON.replace(minute=50), only=["proshares", "direxion", "tradr"], getter=broken_getter, sleep=lambda: None)
check("a daily file with a changed header is a STOP naming the file", any("psdlyhld.csv" in s and "header changed" in s for s in stops3), stops3)
check("a daily file with an HTTP error is a STOP", any("TSLL_holdings.csv" in s and "500" in s for s in stops3), stops3)
check("a dated file that the issuer should have published and did not is a note, not a STOP", any("NSDEAXS2.10262026" in n for n in notes3) and not any("tradr" in s for s in stops3), (stops3, notes3))
THU = datetime(2026, 10, 30, 23, 45, tzinfo=timezone.utc)      # more than DARK_WEEKDAYS weekdays after the newest saved Tradr files (10-23)
records4, stops4, notes4 = ic.run(root2, {"tradr": []}, now=THU, only=["tradr"], getter=lambda u, m="GET", b=None: (404, {}, b""), sleep=lambda: None)
check("a dated source that published nothing for over DARK_WEEKDAYS weekdays is a STOP naming the newest saved date", any("tradr: no nav file" in s and "2026-10-23" in s for s in stops4), stops4)
records4b, stops4b, _ = ic.run(root2, {"tradr": []}, now=datetime(2026, 10, 28, 23, 45, tzinfo=timezone.utc), only=["tradr"], getter=lambda u, m="GET", b=None: (404, {}, b""), sleep=lambda: None)
check("three weekdays without a file (a holiday plus a late file) is not yet a STOP", not any("no nav file" in s for s in stops4b), stops4b)
first = Path(tempfile.mkdtemp(prefix="ledger_first_run_"))
records5, stops5, notes5 = ic.run(first, {"tradr": []}, now=THU, only=["tradr"], getter=lambda u, m="GET", b=None: (404, {}, b""), sleep=lambda: None)
check("a first run that finds no dated files yet is notes only (nothing to judge)", stops5 == [] and notes5, (stops5, notes5[:2]))
lines = ic.summary(records3, stops3, notes3, MON)
check("the summary names the STOP state and counts per source", lines[0].endswith("STOP") and any(ln.startswith("- proshares:") for ln in lines) and any(ln.startswith("- STOP:") for ln in lines))

# ---------- 4. parsers ----------
s = issuer_corgi.parse_summary(CORGI_SUMMARY)
check("Corgi summary parser", s["ticker"] == "AXTC" and s["nav"] == 8.2642 and s["nav_date"] == "2026-10-22" and s["aum"] == 495852.0)
check("Corgi funds parser", issuer_corgi.parse_funds(BODIES["corgiinvest.com/api/data/funds"])[0]["category"] == "2x Single Stock")
check("Corgi daily-nav parser", issuer_corgi.parse_daily_nav(BODIES["AXTC/daily-nav"])[0]["nav"] == 25.0)
prods = issuer_leverage_shares.parse_products(LS_LIST)
check("Leverage Shares product array parser reads both funds and strips the footnote tag", [p["ticker"] for p in prods] == ["METG", "RAML"] and prods[0]["nav"] == 15.81 and prods[1]["underlying"] == "DRAM" and prods[0]["product_url"].endswith("meta-daily-etf"))
pg = issuer_leverage_shares.parse_page(LS_PAGE)
check("Leverage Shares page parser", pg["as_of"] == "10/22/2026" and pg["nav"] == 15.81 and pg["market_price"] == 15.78 and pg["shares_outstanding"] == 120000 and pg["expense_ratio_pct"] == 0.75 and pg["inception"] == "Jul 02, 2026", pg)
ice = issuer_tradr.parse_ice(ICE)
check("Tradr ICE parser", ice[0]["ticker"] == "AAOX" and ice[0]["close"] == 3.82 and ice[0]["date"] == "20261022")
bbh = issuer_tradr.parse_holdings(BBH)
check("Tradr holdings parser", bbh[0]["fund"] == "NXTE" and bbh[0]["shares_outstanding"] == 1090000 and bbh[0]["weight_pct"] == 11.98)
check("Defiance explore parser", issuer_defiance.parse_explore(DEF_EXPLORE)[0]["nav"] == 15.72)
dp = issuer_defiance.parse_page(DEF_PAGE)
check("Defiance page parser", dp["as_of"] == "10/22/2026" and dp["nav"] == 15.72 and dp["shares_outstanding"] == 20725464 and dp["expense_ratio_pct"] == 1.31 and dp["inception"] == "08/14/2024", dp)
as_of, rows = issuer_defiance.parse_holdings(DEF_HOLD)
check("Defiance holdings table parser", as_of == "10/23/2026" and len(rows) == 2 and rows[0]["weight_pct"] == 43.5 and rows[1]["shares"] == -445080503, (as_of, rows))
gp = issuer_graniteshares.parse_product(GS_PRODUCT)
check("GraniteShares product parser reads the inner JSON", gp["ticker"] == "NVDL" and gp["nav_date"] == "2026-10-22" and gp["swap_fees"] == 4.1 and gp["listing_date"] == "2022-12-13", gp)
check("GraniteShares NAV history parser", issuer_graniteshares.parse_nav_history(GS_HIST)[1]["aum"] == 784297.62)
dx = issuer_direxion.parse_holdings(DIREXION)
check("Direxion holdings parser", dx["ticker"] == "TSLL" and dx["shares_outstanding"] == 352150001 and dx["rows"][1]["stock_ticker"] == "TSLA" and dx["rows"][0]["date"] == "10/23/2026", dx)
kp = issuer_kraneshares.parse_page(KRANE_PAGE)
check("KraneShares page parser", kp["net_assets"] == 2900297 and kp["shares_outstanding"] == 450002 and kp["expense_net_pct"] == 0.99 and kp["inception"] == "3/11/2025", kp)
tp = issuer_trex.parse_page(TREX_PAGE)
check("T-Rex page parser", tp["as_of"] == "10/22/2026" and tp["nav"] == 17.6 and tp["shares_outstanding"] == 19690000 and tp["fund_assets"] == 346937800.0 and tp["underlying"] == "NVDA" and tp["premium_pct"] == 0.1398, tp)
pn = issuer_proshares.parse_nav_history(PSH_NAV, ["CRCA"])
check("ProShares NAV history parser filters by ticker and scales shares", len(pn) == 1 and pn[0]["shares_outstanding"] == 5815910 and pn[0]["nav"] == 18.6378)
ph_as_of, ph = issuer_proshares.parse_holdings(PSH_HOLD, ["CRCA"])
check("ProShares holdings parser", ph_as_of == "10/22/2026" and ph[0]["shares"] == 381678 and ph[0]["market_value"] == 33060948.36, (ph_as_of, ph))
check("ProShares splits parser", issuer_proshares.parse_splits(PSH_SPLITS)[0] == dict(ticker="CRCA", name="Ultra CRCL", kind="Reverse", ratio=10.0, date="02/26/2026"))
check("is_html accepts a BOM and lower-case doctype, rejects CSV", ic.is_html(b"\xef\xbb\xbf<!doctype html>") and ic.is_html(b"<HTML>") and not ic.is_html(b"Date,Account"))
