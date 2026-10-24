"""Small helpers ported from the author's sibling kits so a public clone runs on its own.

The Ledger's rule is "import, never copy". Two private kits of the author (the LETF kit and the price library) hold
the helpers below, but a public clone has neither, so the few functions the engine needs are ported here, each with
its source named. They stay in step through tests/port_local.py (git-ignored): on the author's machine it imports
both versions and checks them against each other, so a change on either side fails.

Ported on 2026-10-22 from:
- the price library, marketdata.py: PRICE_COLS, MIN_OVERLAP, EXTRA_BARS, PRICE_TOL, MCP_MAX_BARS, _verify_summary,
  _bars_to_frame, _bar_problems, _write_table
- the LETF kit, data_io.py: load_fred (reads reference/DFF.csv here), rate_on, accrual_fraction
- the LETF kit, letf.py: _align, synth
- the LETF kit, metrics.py: underwater_spells
- the LETF kit, fetch_yahoo.py: url_for, fetch, validate (END is a parameter here)
Ported on 2026-10-24 from:
- the target-fund kit, forward/fetch.py: http_get, sha256, read_manifest, _append_manifest, last_saved, capture,
  new_file, pause (data_dir reads TWOX_LEDGER_DATA here; USER_AGENT names this project)
"""
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "reference"

# ---------- the price library: marketdata.py ----------
PRICE_COLS = ["open", "high", "low", "close"]
MIN_OVERLAP = 5        # fetched bars that must match stored bars before anything is appended
EXTRA_BARS = 10        # extra bars to request beyond the gap, so there is an overlap to check
PRICE_TOL = 5e-4       # 0.05% relative difference allowed between stored and fetched prices
MCP_MAX_BARS = 5000


def _day(ts):
    return str(pd.Timestamp(ts).date())


def verify_summary(data):
    """Recompute the MCP's own summary from the saved bars. A mismatch means the fetch file was copied wrongly."""
    bars, s = data["bars"], data["summary"]
    expected = {
        "count": (data.get("count"), len(bars)),
        "first_t": (s.get("first_t"), bars[0]["t"]),
        "last_t": (s.get("last_t"), bars[-1]["t"]),
        "first_open": (s.get("first_open"), bars[0]["o"]),
        "last_close": (s.get("last_close"), bars[-1]["c"]),
        "high": (s.get("high"), max(b["h"] for b in bars)),
        "low": (s.get("low"), min(b["l"] for b in bars)),
        "total_volume": (s.get("total_volume"), sum(b.get("v") or 0 for b in bars)),
    }
    if s.get("total_volume") is None and all(b.get("v") is None for b in bars):
        del expected["total_volume"]
    wrong = [f"{k}: summary {a} vs bars {b}" for k, (a, b) in expected.items()
             if a is None or not np.isclose(float(a), float(b), rtol=1e-9, atol=1e-9)]
    if wrong:
        raise ValueError("saved bars do not match the MCP's own summary, so the fetch file is not a faithful copy. "
                         "Re-fetch. " + "; ".join(wrong))


def bars_to_frame(bars, tz, source, shift_hours=0):
    """MCP bars carry unix seconds (UTC). Convert to the session date in the exchange timezone."""
    utc = pd.to_datetime([b["t"] for b in bars], unit="s", utc=True) + pd.Timedelta(hours=shift_hours)
    dates = utc.tz_convert(tz).tz_localize(None).normalize()
    df = pd.DataFrame({
        "open": [b["o"] for b in bars], "high": [b["h"] for b in bars],
        "low": [b["l"] for b in bars], "close": [b["c"] for b in bars],
        "volume": [b.get("v") for b in bars], "source": source,
    }, index=pd.DatetimeIndex(dates, name="date"))
    if df.index.duplicated().any():
        raise ValueError(f"fetch has duplicate session dates {sorted({_day(d) for d in df.index[df.index.duplicated()]})}; wrong timezone?")
    if not df.index.is_monotonic_increasing:
        raise ValueError("fetch bars are not in date order")
    weekend = df.index[df.index.dayofweek >= 5]
    if len(weekend):
        raise ValueError(f"fetch has weekend-dated bars {[_day(d) for d in weekend[:3]]}; the timezone in the manifest is probably wrong")
    return df


def bar_problems(df):
    """Rows whose prices are impossible: non-positive, or open/close outside the high-low range."""
    d = df.dropna(subset=PRICE_COLS)
    eps = 1e-6
    bad = (
        (d[PRICE_COLS] <= 0).any(axis=1)
        | (d["low"] > d[["open", "close"]].min(axis=1) * (1 + eps))
        | (d["high"] < d[["open", "close"]].max(axis=1) * (1 - eps))
    )
    return [_day(i) for i in d.index[bad]]


def write_table(df, path):
    tmp = Path(path).with_suffix(".tmp")
    df.to_csv(tmp, index_label="date", date_format="%Y-%m-%d")
    tmp.replace(path)


# ---------- the LETF kit: data_io.py ----------

def load_fred(name="DFF", folder=REFERENCE):
    """FRED CSV reference/<name>.csv (date, value in PERCENT) -> Series of DECIMAL rates (0.05 = 5%)."""
    df = pd.read_csv(Path(folder) / f"{name}.csv")
    s = pd.Series(pd.to_numeric(df.iloc[:, 1], errors="coerce").values / 100, index=pd.to_datetime(df.iloc[:, 0])).dropna()
    s.name = name
    return s


def accrual_fraction(index, basis=365):
    """Calendar-day accrual per row (days since previous row / basis). First row 0. Weekends/holidays accrue.

    The LETF kit uses 365 for everything; this project passes 360 for the money-market rate (rates.accrual) and 365
    for the expense ratio (rates.fee_accrual)."""
    gaps = pd.Series(index, index=index).diff().dt.days.fillna(0.0)
    return gaps / float(basis)


def rate_on(index, rate, lag_rows=1):
    """Rate known BEFORE each row: value dated on or before the previous row's date (no same-day look-ahead)."""
    src = rate.sort_index()
    out = src.reindex(src.index.union(index)).ffill().reindex(index)
    out = out.shift(lag_rows)
    return out


# ---------- the LETF kit: letf.py ----------

def _align(x, index, name, initial=None):
    """Float, or Series forward-filled onto index using only values dated on or before each target date."""
    if not isinstance(x, pd.Series):
        return pd.Series(float(x), index=index)
    src = x.sort_index()
    out = src.reindex(src.index.union(index)).ffill().reindex(index)
    if out.isna().any():
        if initial is None:
            raise ValueError(f"{name}: no value available on or before {out[out.isna()].index[0].date()}; "
                             "pass initial= with a documented assumption")
        out = out.fillna(initial)
    return out


def synth(index_price, L, rate=0.0, spread=0.0091, fee=0.0091, div_yield=0.0, lend_spread=0.0,
          day_count="calendar", max_gap_days=7, allow_gaps=False, rate_initial=None, div_initial=None):
    """Daily-reset L-times fund NAV from an index price series (letf.synth, ported). Pass spread and fee explicitly:
    the defaults (0.91%) are the LETF kit's and mean nothing for a single-stock fund."""
    if L < 0:
        raise ValueError("L must be >= 0 (inverse funds need their own model)")
    px = index_price.sort_index().astype(float)
    if not np.isfinite(px.values).all() or (px.values <= 0).any():
        raise ValueError("index prices must be finite and positive")
    idx = px.index
    gaps = pd.Series(idx, index=idx).diff().dt.days
    if not allow_gaps and (gaps > max_gap_days).any():
        first = gaps[gaps > max_gap_days].index[0]
        raise ValueError(f"gap of {int(gaps.max())} days (first at {first.date()}): daily-reset math needs daily data; "
                         "pass allow_gaps=True only if the gaps are market closures")
    if day_count == "calendar":
        a = gaps.fillna(0.0) / 365.0
    elif day_count == "trading":
        a = pd.Series(1 / 252, index=idx)
        a.iloc[0] = 0.0
    else:
        raise ValueError("day_count must be 'calendar' or 'trading'")
    rt = _align(rate, idx, "rate", rate_initial)
    dy = _align(div_yield, idx, "div_yield", div_initial)
    ret = px.pct_change().fillna(0.0)
    if L >= 1:
        carry = -(L - 1) * (rt + spread) * a
    else:
        carry = (1 - L) * (rt + lend_spread) * a
    d = L * (ret + dy * a) + carry - fee * a
    d.iloc[0] = 0.0
    nav = np.empty(len(d))
    level, terminated = 1.0, None
    for i, x in enumerate(d.values):
        if level > 0:
            level = level * (1 + x)
            if level <= 0:
                level, terminated = 0.0, idx[i]
        nav[i] = level
    out = pd.Series(nav, index=idx, name=f"synthetic_{L}x")
    out.attrs["terminated"] = terminated
    out.attrs["model"] = dict(L=L, spread=spread, fee=fee, lend_spread=lend_spread, day_count=day_count)
    return out


# ---------- the LETF kit: metrics.py ----------

def underwater_spells(series):
    """Underwater spells with the actual prior peak date (dicts with peak, trough, recovery, depth, durations)."""
    spells = []
    peak_val, peak_date = series.iloc[0], series.index[0]
    in_spell, trough_val, trough_date = False, None, None
    for d, v in series.iloc[1:].items():
        if not in_spell:
            if v >= peak_val:
                peak_val, peak_date = v, d
            else:
                in_spell, trough_val, trough_date = True, v, d
        else:
            if v < trough_val:
                trough_val, trough_date = v, d
            if v >= peak_val:
                spells.append(dict(peak_date=peak_date, trough_date=trough_date, recovery_date=d,
                                   depth=float(trough_val / peak_val - 1) if peak_val > 0 else -1.0,
                                   peak_to_trough_days=(trough_date - peak_date).days,
                                   trough_to_recovery_days=(d - trough_date).days,
                                   peak_to_recovery_days=(d - peak_date).days, censored=False))
                in_spell, peak_val, peak_date = False, v, d
    if in_spell:
        end = series.index[-1]
        spells.append(dict(peak_date=peak_date, trough_date=trough_date, recovery_date=None,
                           depth=float(trough_val / peak_val - 1) if peak_val > 0 else -1.0,
                           peak_to_trough_days=(trough_date - peak_date).days, trough_to_recovery_days=None,
                           peak_to_recovery_days=(end - peak_date).days, censored=True))
    return spells


# ---------- the LETF kit: fetch_yahoo.py ----------

def yahoo_url(sym, end):
    return ("https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(sym)
            + f"?period1=0&period2={int(end)}&interval=1d&events=div%2Csplits")


def yahoo_fetch(sym, end):
    req = urllib.request.Request(yahoo_url(sym, end), headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=60).read()


def yahoo_validate(raw_bytes, sym):
    """Strict checks on a Yahoo chart reply: daily bars, sorted unique dates, positive prices, no long gaps."""
    j = json.loads(raw_bytes)
    res = j["chart"]["result"][0]
    gran = res["meta"].get("dataGranularity")
    if gran != "1d":
        raise ValueError(f"{sym}: granularity {gran}, expected 1d")
    ix = pd.to_datetime(res["timestamp"], unit="s", utc=True).tz_convert(res["meta"]["exchangeTimezoneName"]).normalize().tz_localize(None)
    q = res["indicators"]["quote"][0]["close"]
    adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose")
    s = pd.Series(adj if adj else q, index=ix, dtype="float64").dropna()
    if s.index.duplicated().any() or not s.index.is_monotonic_increasing:
        raise ValueError(f"{sym}: duplicate or unsorted dates")
    if not (s > 0).all():
        raise ValueError(f"{sym}: non-positive prices")
    gaps = s.index.to_series().diff().dt.days.dropna()
    if (gaps > 10).sum() > 5:
        raise ValueError(f"{sym}: {int((gaps > 10).sum())} gaps over 10 days: not daily data")
    return s, bool(adj)


# ---------- the target-fund kit: forward/fetch.py (raw-file capture with an append-only manifest) ----------
# What it does, in plain words: download a file once, save the bytes UNCHANGED under <data>/raw/<source>/<UTC
# date>/<name>, and record every fetch (failures too) as one JSON line in <data>/raw/manifest.jsonl. Identical
# bytes to the last saved copy are recorded as "unchanged" and not saved again, so a second run is harmless. A
# body that does not start with the expected header is saved for inspection but marked "invalid".

USER_AGENT = "2x-ledger/0.2 (research; one request per file per day)"
PAUSE_SECONDS = 1.0                      # wait between requests to the same site


def data_dir(path=None):
    """Data folder: the argument, else $TWOX_LEDGER_DATA, else <repo>/data (git-ignored)."""
    if path is not None:
        return Path(path)
    env = os.environ.get("TWOX_LEDGER_DATA")
    return Path(env) if env else ROOT / "data"


def http_get(url, timeout=60):
    """Return (status, headers, body bytes). HTTP errors come back as their status code, not an exception."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as err:
        return err.code, dict(err.headers or {}), err.read() or b""


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read_manifest(root):
    """All manifest records, oldest first (empty list if none yet). root=None means the default data folder."""
    path = data_dir(root) / "raw" / "manifest.jsonl"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _append_manifest(root, record):
    path = Path(root) / "raw" / "manifest.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def last_saved(records, url):
    """The most recently downloaded record for this URL whose bytes the code saved (status 'saved'), or None.

    By download time, not manifest position (imported cloud captures may be appended out of order)."""
    saved = [rec for rec in records if rec["url"] == url and rec["result"] == "saved"]
    return max(saved, key=lambda rec: rec["fetched_utc"]) if saved else None


def capture(url, name, source, expect_prefix, root=None, now=None, getter=http_get, records=None):
    """Fetch one URL and record it. Returns the manifest record (a dict).

    expect_prefix: bytes the body must start with to count as valid (e.g. b"Date,Account"), or None for any.
    result is one of: "saved" (new bytes, valid), "unchanged" (same bytes as last saved copy),
    "invalid" (saved for inspection, but not the expected content), "invalid_repeat" (the same invalid content
    again: recorded, not saved twice), "http_error", "network_error".
    """
    root = data_dir(root)
    now = now or datetime.now(timezone.utc)
    records = read_manifest(root) if records is None else records
    rec = {"url": url, "name": name, "source": source,
           "fetched_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ")}
    try:
        status, headers, body = getter(url)
    except Exception as err:  # noqa: BLE001 - the manifest records network failures; capture never raises them
        rec.update(result="network_error", error=f"{type(err).__name__}: {err}")
        _append_manifest(root, rec)
        return rec

    rec.update(status=status, bytes=len(body), sha256=sha256(body),
               last_modified=headers.get("Last-Modified"), content_type=headers.get("Content-Type"))
    if status != 200:
        rec["result"] = "http_error"
        _append_manifest(root, rec)
        return rec

    valid = expect_prefix is None or body.lstrip(b"\xef\xbb\xbf").startswith(expect_prefix)
    if not valid and any(r["url"] == url and r.get("sha256") == rec["sha256"] and r["result"] == "invalid"
                         for r in records):
        rec["result"] = "invalid_repeat"              # the same error page again: record it, don't re-save it
        _append_manifest(root, rec)
        return rec
    prev = last_saved(records, url)
    if valid and prev is not None and prev["sha256"] == rec["sha256"]:
        rec["result"] = "unchanged"
        rec["same_as"] = prev["path"]
        _append_manifest(root, rec)
        return rec

    day_dir = root / "raw" / source / now.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    target = new_file(day_dir, name, now, body)
    rec["path"] = target.relative_to(root).as_posix()
    rec["result"] = "saved" if valid else "invalid"
    _append_manifest(root, rec)
    return rec


def new_file(folder, name, now, body):
    """Write `body` to a file that did not exist: `name`, else name__HHMMSS, else name__HHMMSS_2, _3 ... Exclusive
    creation ('xb'), so raw bytes are never overwritten, even by two captures in the same second (external audit A10)."""
    stem, dot, ext = name.rpartition(".")
    base, tail = (stem, f".{ext}") if dot else (name, "")
    base = f"{base}__{now.strftime('%H%M%S')}"
    i = 0
    while True:
        cand = name if i == 0 else f"{base}{tail}" if i == 1 else f"{base}_{i}{tail}"
        try:
            with open(folder / cand, "xb") as fh:
                fh.write(body)
            return folder / cand
        except FileExistsError:
            i += 1


def pause():
    time.sleep(PAUSE_SECONDS)
