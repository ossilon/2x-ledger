"""Capture store: synthetic mcp-tv-get-ohlcv replies with planted bars (no network, temp folder)."""
import json
import shutil
import tempfile
from pathlib import Path

import pandas as pd

from _harness import check, raises
import tv_capture as tc
from captured_by import captured_by

TZ = "America/New_York"


def make_reply(symbol, start, n, price0=100.0, step=0.01, scale=1.0, has_more=False, fmt="rows", weekend=False):
    """A faithful synthetic reply: n business-day bars from `start`, closes growing by `step` a day."""
    days = list(pd.bdate_range(start, periods=n))
    if weekend:
        days[-1] = days[-1] + pd.Timedelta(days=(5 - days[-1].dayofweek))  # push the last bar onto a Saturday
    bars, prev = [], price0 * scale / (1 + step)      # first open = the close before the window, so top-ups agree
    for i, d in enumerate(days):
        c = round(price0 * (1 + step) ** i * scale, 6)
        o = prev
        h, l = round(max(o, c) * 1.001, 6), round(min(o, c) * 0.999, 6)
        t = int(pd.Timestamp(d.strftime("%Y-%m-%d") + " 09:30", tz=TZ).timestamp())
        bars.append({"t": t, "o": o, "h": h, "l": l, "c": c, "v": 1000 + i})
        prev = c
    summary = {"first_t": bars[0]["t"], "last_t": bars[-1]["t"], "first_open": bars[0]["o"],
               "last_close": bars[-1]["c"], "high": max(b["h"] for b in bars), "low": min(b["l"] for b in bars),
               "total_volume": sum(b["v"] for b in bars), "avg_volume": sum(b["v"] for b in bars) / n}
    data = {"success": True, "symbol": symbol, "interval": "1D", "format": fmt, "count": n,
            "has_more": has_more, "bars": bars, "summary": summary}
    if fmt == "columns":
        data["bars"] = {k: [b[k] for b in bars] for k in ("t", "o", "h", "l", "c", "v")}
    return data


def write_reply(folder, name, data):
    p = Path(folder) / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


root = Path(tempfile.mkdtemp(prefix="ledger_capture_"))
inbox = root / "inbox"
inbox.mkdir(parents=True)
SYM = "NASDAQ:TEST"

# 1. a good full-history reply is stored byte for byte and recorded
r1 = make_reply(SYM, "2024-01-02", 60)
f1 = write_reply(inbox, "r1.json", r1)
rec1 = tc.ingest(f1, root=root, fetched_utc="2024-04-01T22:00:00Z")
check("ingest records the symbol and bar count", rec1["symbol"] == SYM and rec1["bars"] == 60, rec1)
check("ingest stores the exact bytes (hash matches)", tc.sha256_bytes((tc.raw_dir(root) / rec1["path"]).read_bytes()) == rec1["sha256"])
check("manifest has one saved record", len(tc.records(SYM, root=root)) == 1)
check("a full reply is marked full", rec1["full"] is True)
check("ingesting the same bytes again is idempotent", tc.ingest(f1, root=root, fetched_utc="2024-04-02T22:00:00Z")["path"] == rec1["path"])
check("manifest still has one record", len(tc.records(SYM, root=root)) == 1)

# 2. build gives the planted sessions and the private series file
df = tc.build(SYM, root=root)
check("build keeps all 60 planted sessions (fetched after the last bar)", len(df) == 60, len(df))
check("series file exists with meta", (tc.series_dir(root) / "NASDAQ_TEST.csv").exists() and (tc.series_dir(root) / "NASDAQ_TEST.meta.json").exists())
loaded = tc.load_series(SYM, root=root)
check("load_series labels the series price_only", loaded.attrs["series_type"] == "price_only", loaded.attrs)
check("banner names the symbol and the adjustment", "NOT dividend-adjusted" in tc.banner(SYM, root=root))

# 3. a reply whose bars no longer match the MCP's own summary is refused (truncated or mis-copied file).
#    Known limit, recorded in tv_capture's docstring: the summary covers the ends, the extremes and total volume,
#    so a change to one interior price with its volume intact is not detectable from the reply alone.
bad = make_reply(SYM, "2024-01-02", 60)
bad["bars"][-1]["c"] = bad["bars"][-1]["c"] * 1.002
raises("a last close that differs from the summary is refused as not a faithful copy", lambda: tc.ingest(write_reply(inbox, "bad.json", bad), root=root, fetched_utc="2024-04-01T22:00:00Z"), "faithful copy")
trunc = make_reply(SYM, "2024-01-02", 60)
trunc["bars"] = trunc["bars"][:-3]
raises("a truncated bar list is refused", lambda: tc.ingest(write_reply(inbox, "trunc.json", trunc), root=root, fetched_utc="2024-04-01T22:00:00Z"), "faithful copy")
vol = make_reply(SYM, "2024-01-02", 60)
vol["bars"][10]["v"] += 1
raises("a changed interior volume is refused (total volume is in the summary)", lambda: tc.ingest(write_reply(inbox, "vol.json", vol), root=root, fetched_utc="2024-04-01T22:00:00Z"), "faithful copy")

# 4. weekend-dated bar, columns format, and a failed reply are refused
wk = make_reply(SYM, "2024-01-02", 10, weekend=True)
raises("weekend-dated bar is refused", lambda: tc.ingest(write_reply(inbox, "wk.json", wk), root=root, fetched_utc="2024-04-01T22:00:00Z"), "weekend")
col = make_reply("NASDAQ:COLS", "2024-01-02", 10, fmt="columns")
rec_col = tc.ingest(write_reply(inbox, "col.json", col), root=root, fetched_utc="2024-04-01T22:00:00Z")
check("columns format is accepted and counted", rec_col["bars"] == 10, rec_col)
check("a columns-format reply builds the same sessions", len(tc.build("NASDAQ:COLS", root=root, write=False)) == 10)
col_bad = make_reply("NASDAQ:COLS", "2024-01-02", 10, fmt="columns")
col_bad["bars"]["c"] = col_bad["bars"]["c"][:-1]
raises("ragged column arrays are refused", lambda: tc.ingest(write_reply(inbox, "colbad.json", col_bad), root=root, fetched_utc="2024-04-01T22:00:00Z"), "values")
nosucc = make_reply(SYM, "2024-01-02", 10)
nosucc["success"] = False
raises("success false is refused", lambda: tc.ingest(write_reply(inbox, "ns.json", nosucc), root=root, fetched_utc="2024-04-01T22:00:00Z"), "success")

# 5. a consistent top-up (10 overlapping bars, 5 new) extends the series
days = pd.bdate_range("2024-01-02", periods=65)
top = make_reply(SYM, str(days[50].date()), 15, price0=100.0 * 1.01 ** 50, has_more=True)
# make its first open equal the previous planted close so the frame is consistent (open is only sanity-checked)
rec2 = tc.ingest(write_reply(inbox, "top.json", top), root=root, fetched_utc="2024-04-08T22:00:00Z")
check("a top-up is marked not full", rec2["full"] is False)
df2 = tc.build(SYM, root=root)
check("top-up adds the 5 new sessions", len(df2) == 65, len(df2))
check("the series is still in date order with unique dates", df2.index.is_monotonic_increasing and not df2.index.duplicated().any())

# 6. a top-up at a constant 10x price ratio is a split: the build must stop and say so
split = make_reply(SYM, str(days[55].date()), 15, price0=100.0 * 1.01 ** 55, scale=10.0, has_more=True)
tc.ingest(write_reply(inbox, "split.json", split), root=root, fetched_utc="2024-04-15T22:00:00Z")
raises("constant-ratio top-up is reported as a split needing a full refetch", lambda: tc.build(SYM, root=root), "split")

# 7. captured_by hides later fetches
with captured_by("2024-04-05T00:00:00Z"):
    df3 = tc.build(SYM, root=root, write=False)
check("captured_by before the top-up gives only the full fetch's 60 sessions", len(df3) == 60, len(df3))
df4 = tc.build(SYM, root=root, cutoff="2024-04-10T00:00:00Z", write=False)
check("an explicit cutoff after the first top-up gives 65 sessions", len(df4) == 65, len(df4))
raises("a malformed cutoff is refused", lambda: tc.build(SYM, root=root, cutoff="2024-04-10"), "cutoff")

# 8. a bar dated on the fetch day is dropped as possibly unfinished
SYM2 = "NASDAQ:TEST2"
r8 = make_reply(SYM2, "2024-03-01", 20)                       # last bar is 2024-03-28
tc.ingest(write_reply(inbox, "r8.json", r8), root=root, fetched_utc="2024-03-28T18:00:00Z")   # fetched that day
df8 = tc.build(SYM2, root=root)
check("the bar dated on the fetch day is dropped", len(df8) == 19 and str(df8.index[-1].date()) == "2024-03-27", (len(df8), df8.index[-1]))

# 9. determinism: building twice gives identical bytes
p8 = tc.series_dir(root) / "NASDAQ_TEST2.csv"
b1 = p8.read_bytes()
tc.build(SYM2, root=root)
check("rebuilding writes identical bytes", p8.read_bytes() == b1)

# 10. plan: a built series asks for gap + EXTRA_BARS; an unknown symbol asks for a full fetch; closed asks nothing
tc.register_dir(root).mkdir(parents=True, exist_ok=True)
(tc.register_dir(root) / "stocks.csv").write_text("symbol,status\nNASDAQ:TEST2,live\nNASDAQ:NEW,live\nNASDAQ:OLD,closed\n", encoding="utf-8")
plan = {r["symbol"]: r for r in tc.plan(root=root, now=pd.Timestamp("2024-04-12T22:00:00Z").to_pydatetime())}
check("plan asks for gap plus extra bars for a built series", plan["NASDAQ:TEST2"]["count"] == 11 + tc.EXTRA_BARS, plan["NASDAQ:TEST2"])
check("plan asks for a full fetch for a symbol with no series", plan["NASDAQ:NEW"]["count"] == tc.MAX_BARS, plan["NASDAQ:NEW"])
check("plan asks nothing for a closed fund that has no series... (no series -> full)", plan["NASDAQ:OLD"]["count"] == tc.MAX_BARS, plan["NASDAQ:OLD"])

# 11b. a maximal window (MAX_BARS bars, has_more true) is accepted as a base and labeled incomplete
SYM3 = "NASDAQ:OLD3"
win = make_reply(SYM3, "2000-01-03", tc.MAX_BARS, step=0.0001, has_more=True)
tc.ingest(write_reply(inbox, "win.json", win), root=root, fetched_utc="2024-04-01T22:00:00Z")
dfw = tc.build(SYM3, root=root)
check("a MAX_BARS window with has_more true builds", len(dfw) == tc.MAX_BARS, len(dfw))
check("and is labeled as not the complete history", dfw.attrs["complete_history"] is False and "NOT the full listing" in tc.banner(SYM3, root=root))
short = make_reply("NASDAQ:SHORT", "2024-01-02", 30, has_more=True)
tc.ingest(write_reply(inbox, "short.json", short), root=root, fetched_utc="2024-04-01T22:00:00Z")
raises("a partial fetch that is neither full nor maximal cannot be a base", lambda: tc.build("NASDAQ:SHORT", root=root), "full-history")

# 11c. a sourced bar fix is applied at build time and recorded; the raw file is untouched
fix_day = str(pd.bdate_range("2024-03-01", periods=20)[5].date())
(tc.register_dir(root) / "bar_fixes.csv").write_text(
    "symbol,date,fields,factor,reason,source,captured_date\n"
    f"NASDAQ:TEST2,{fix_day},open|high|low|close,0.5,planted,test,2026-10-22\n", encoding="utf-8")
before = tc.load_series(SYM2, root=root)["close"][fix_day]
raw_hash_before = tc.sha256_bytes((tc.raw_dir(root) / tc.records(SYM2, root=root)[0]["path"]).read_bytes())
dff = tc.build(SYM2, root=root)
check("a bar fix scales the named fields on that day only", abs(dff["close"][fix_day] / before - 0.5) < 1e-12 and dff["close"].iloc[0] == tc.load_series(SYM2, root=root)["close"].iloc[0])
check("the fix is recorded in the series meta and banner", len(dff.attrs["fixes_applied"]) == 1 and "1 bar fix(es)" in tc.banner(SYM2, root=root))
check("the raw file is unchanged by a fix", tc.sha256_bytes((tc.raw_dir(root) / tc.records(SYM2, root=root)[0]["path"]).read_bytes()) == raw_hash_before)
(tc.register_dir(root) / "bar_fixes.csv").write_text(
    "symbol,date,fields,factor,reason,source,captured_date\n"
    f"NASDAQ:TEST2,{fix_day},close|nonsense,0.5,planted,test,2026-10-22\n", encoding="utf-8")
raises("a fix naming an unknown field is refused", lambda: tc.build(SYM2, root=root), "unknown fields")
(tc.register_dir(root) / "bar_fixes.csv").unlink()
tc.build(SYM2, root=root)

# 11. a raw file changed on disk is refused at build time
p_raw = tc.raw_dir(root) / tc.records(SYM2, root=root)[0]["path"]
p_raw.write_bytes(p_raw.read_bytes().replace(b'"success": true', b'"success": true '))
raises("a raw file whose hash changed is refused", lambda: tc.build(SYM2, root=root), "hash")

shutil.rmtree(root, ignore_errors=True)
