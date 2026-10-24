#!/usr/bin/env python3
"""Daily capture of the issuers' public fund files for the whole universe (v0.2 plan, D3).

What it does, in plain words
- Each issuer has an adapter module (issuer_corgi.py, issuer_tradr.py, ...). An adapter lists the files to fetch
  today as "specs": a name, a URL, how the body must start to count as valid, how often to fetch it (daily, weekly,
  monthly, or dated: one file per day named by date), and what kind of file it is (nav, holdings, page, list,
  history). Some adapters add "follow-ups" that depend on a file fetched earlier in the same run (the fund pages
  named in a list page; the holdings request that needs the NAV date from the product record).
- Every fetch goes through `store`, which keeps the raw bytes unchanged in <root>/raw/<source>/<UTC date>/ and
  appends one JSON line to <root>/raw/manifest.jsonl (the same layout and record fields as the ported
  `port.capture`, plus `kind`, `cadence`, `method`, `date` for dated files and, for compressed files,
  `encoding: gzip` and `stored_bytes`). Bodies above GZIP_MIN bytes are stored gzip-compressed; the manifest's
  `sha256` and `bytes` always describe the uncompressed body, so a reader can verify a file after decompressing it.
- Cadence is self-healing: a weekly file is due on Friday, on the last weekday of the month, and whenever no copy
  was saved in the last 7 days; a monthly file is due whenever no copy was saved in the last 25 days. A dated file
  is due for every recent weekday that has no saved copy yet, once the time the issuer publishes it has passed
  (`ready_utc`), so a missed day comes back on the next run; a date that keeps failing is given up after
  GIVE_UP_DAYS (a market holiday never gets a file).
- `run` returns the records plus STOP lines and notes. STOP: a daily file failed or changed its header, or a dated
  source published nothing for more than DARK_WEEKDAYS weekdays. The CLI (scripts/daily_capture.py) writes a
  status file and exits 1 on a STOP, so a scheduled job reports failure.
- The manifest is indexed once per run (`Index`), so a run costs one pass over the manifest, not one per file.

Public use of these files: aggregates only (v0.2 plan, D3). Nothing under raw/ is published.
"""
import csv
import gzip
import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _paths  # noqa: E402,F401
import port  # noqa: E402

ISSUERS = ["corgi", "leverage_shares", "tradr", "defiance", "graniteshares", "direxion", "proshares", "kraneshares", "trex"]
GZIP_MIN = 64 * 1024            # bodies above this size are stored compressed
GIVE_UP_DAYS = 7                # a dated file still absent this long after its date is not asked for again
WEEKLY_MAX_AGE = 7
MONTHLY_MAX_AGE = 25
RECENT_DATED_DAYS = 5           # dated files: look back this many calendar days for missing weekdays
DARK_WEEKDAYS = 4               # a dated source with no file for more than this many weekdays is a STOP (3 would
                                # fire on a holiday plus a late file; 4 still catches a dead source within a week)
BAD = ("http_error", "network_error", "invalid", "invalid_repeat")


def spec(name, url, prefix, cadence="daily", kind="nav", method="GET", body=None, ticker=None, valid=None, date=None, ready_utc=None):
    """One file to fetch. `prefix`: bytes the body must start with (None = any). `valid`: an optional callable
    (body) -> bool used instead of the prefix (HTML pages whose doctype varies in case). `date`: the file's own date
    for cadence "dated"; `ready_utc`: the earliest UTC time the issuer publishes that file (not due before it)."""
    if cadence == "dated" and date is None:
        raise ValueError(f"{name}: a dated spec needs its date")
    return dict(name=name, url=url, prefix=prefix, cadence=cadence, kind=kind, method=method, body=body,
                ticker=ticker, valid=valid, date=date, ready_utc=ready_utc)


def is_html(body):
    head = body.lstrip(b"\xef\xbb\xbf \r\n\t")[:60].lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html")


def http_request(url, method="GET", body=None, timeout=120):
    """Like port.http_get, with POST support (JSON body). Returns (status, headers, bytes)."""
    import urllib.error
    import urllib.request
    headers = {"User-Agent": port.USER_AGENT}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as err:
        return err.code, dict(err.headers or {}), err.read() or b""


# ---------- the manifest index ----------

class Index:
    """Manifest records grouped for the two lookups the run needs: by (url, request body) and by (source, name)."""

    def __init__(self, records):
        self.by_request = {}
        self.by_file = {}
        for r in records:
            self.add(r)

    def add(self, r):
        self.by_request.setdefault((r.get("url"), r.get("body")), []).append(r)
        self.by_file.setdefault((r.get("source"), r.get("name")), []).append(r)

    def same_request(self, sp):
        body = sp["body"].decode("utf-8", "replace") if sp["body"] is not None else None
        return self.by_request.get((sp["url"], body), [])

    def file(self, source, name):
        return self.by_file.get((source, name), [])


# ---------- cadence ----------

def weekdays_back(today, days=RECENT_DATED_DAYS):
    """Weekdays from `days` calendar days ago up to today, oldest first."""
    out = []
    for back in range(days, -1, -1):
        d = today - timedelta(days=back)
        if d.weekday() < 5:
            out.append(d)
    return out


def last_weekday_of_month(d):
    nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    last = nxt - timedelta(days=1)
    while last.weekday() >= 5:
        last -= timedelta(days=1)
    return d == last


def _recent_ok(index, source, name, now, max_age_days):
    """True if a saved or unchanged record of this file is at most max_age_days old."""
    cutoff = (now - timedelta(days=max_age_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return any(r.get("result") in ("saved", "unchanged") and r["fetched_utc"] >= cutoff for r in index.file(source, name))


def due(index, source, sp, now):
    """Is this spec due in a run at `now` (UTC)? `index` is an Index (or a list of records)."""
    if not isinstance(index, Index):
        index = Index(index)
    today = now.date()
    if sp["cadence"] == "daily":
        return True
    if sp["cadence"] == "weekly":
        return today.weekday() == 4 or last_weekday_of_month(today) or not _recent_ok(index, source, sp["name"], now, WEEKLY_MAX_AGE)
    if sp["cadence"] == "monthly":
        return not _recent_ok(index, source, sp["name"], now, MONTHLY_MAX_AGE)
    if sp["cadence"] == "dated":
        if sp.get("ready_utc") is not None and now < sp["ready_utc"]:
            return False                                       # the issuer has not published this day's file yet
        mine = index.file(source, sp["name"])
        if any(r.get("result") in ("saved", "unchanged") for r in mine):
            return False
        failed = any(r.get("result") in BAD for r in mine)
        return not (failed and (today - sp["date"]).days > GIVE_UP_DAYS)
    raise ValueError(f"unknown cadence {sp['cadence']!r}")


# ---------- storage ----------

def store(sp, source, root, now, records, getter=http_request, index=None):
    """Fetch one spec and record it (port.capture's rules, plus POST bodies and gzip storage). Returns the record.
    `records` is the manifest list (used to build an Index when none is passed); the new record is NOT appended to
    it or to the index here, the caller does that."""
    index = index if index is not None else Index(records)
    rec = {"url": sp["url"], "name": sp["name"], "source": source, "fetched_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "kind": sp["kind"], "cadence": sp["cadence"], "method": sp["method"]}
    if sp.get("ticker"):
        rec["ticker"] = sp["ticker"]
    if sp.get("date") is not None:
        rec["date"] = sp["date"].isoformat()
    if sp["body"] is not None:
        rec["body"] = sp["body"].decode("utf-8", "replace")
    try:
        status, headers, body = getter(sp["url"], sp["method"], sp["body"]) if sp["method"] != "GET" or sp["body"] is not None else getter(sp["url"])
    except Exception as err:  # noqa: BLE001 - the manifest records network failures; the run never raises them
        rec.update(result="network_error", error=f"{type(err).__name__}: {err}")
        port._append_manifest(root, rec)
        return rec
    rec.update(status=status, bytes=len(body), sha256=port.sha256(body),
               last_modified=headers.get("Last-Modified"), content_type=headers.get("Content-Type"))
    if status != 200:
        rec["result"] = "http_error"
        port._append_manifest(root, rec)
        return rec
    if sp.get("valid") is not None:
        valid = bool(sp["valid"](body))
    else:
        valid = sp["prefix"] is None or body.lstrip(b"\xef\xbb\xbf").startswith(sp["prefix"])
    same = index.same_request(sp)
    if not valid and any(r.get("sha256") == rec["sha256"] and r.get("result") == "invalid" for r in same):
        rec["result"] = "invalid_repeat"
        port._append_manifest(root, rec)
        return rec
    saved = [r for r in same if r.get("result") == "saved"]
    prev = max(saved, key=lambda r: r["fetched_utc"]) if saved else None
    if valid and prev is not None and prev["sha256"] == rec["sha256"]:
        rec["result"] = "unchanged"
        rec["same_as"] = prev["path"]
        port._append_manifest(root, rec)
        return rec
    day_dir = Path(root) / "raw" / source / now.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    name, payload = sp["name"], body
    if len(body) > GZIP_MIN:
        payload = gzip.compress(body, mtime=0)
        name = sp["name"] + ".gz"
        rec["encoding"] = "gzip"
        rec["stored_bytes"] = len(payload)
    target = port.new_file(day_dir, name, now, payload)
    rec["path"] = target.relative_to(root).as_posix()
    rec["result"] = "saved" if valid else "invalid"
    port._append_manifest(root, rec)
    return rec


def read_raw(root, rec):
    """The uncompressed bytes of a saved record."""
    b = (Path(root) / rec["path"]).read_bytes()
    return gzip.decompress(b) if rec.get("encoding") == "gzip" else b


def latest_bytes(root, index, source, name):
    """Uncompressed bytes of the most recently saved copy of this file, or None. `index`: Index or record list."""
    if not isinstance(index, Index):
        index = Index(index)
    saved = [r for r in index.file(source, name) if r.get("result") == "saved"]
    if not saved:
        return None
    return read_raw(root, max(saved, key=lambda r: r["fetched_utc"]))


# ---------- the run ----------

def load_universe(path):
    """universe.csv -> {issuer_key: [row dicts]} with ticker, underlying, slug (page slug or id when needed).
    Refuses an issuer_key that no adapter handles (a typo would otherwise drop those funds silently)."""
    out = {k: [] for k in ISSUERS}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("capture", "1") in ("0", "false", "False"):
                continue
            if row["issuer_key"] not in out:
                raise ValueError(f"universe.csv: unknown issuer_key {row['issuer_key']!r} for {row.get('ticker')}; known: {ISSUERS}")
            out[row["issuer_key"]].append(row)
    return out


def adapter(key):
    return importlib.import_module(f"issuer_{key}")


def run(root, universe, now=None, only=None, getter=http_request, sleep=port.pause, records=None):
    """One capture run over every issuer (or `only`, a list of issuer keys). Returns (records, stops, notes)."""
    now = now or datetime.now(timezone.utc)
    root = Path(root)
    records = port.read_manifest(root) if records is None else records
    index = Index(records)
    out, stops, notes = [], [], []
    for key in ISSUERS:
        if only and key not in only:
            continue
        mod = adapter(key)
        funds = universe.get(key, [])
        ctx = SimpleNamespace(now=now, today=now.date(), funds=funds, records=records, root=root, source=mod.SOURCE, notes=notes)
        got = {}

        def grab(sp):
            if not due(index, mod.SOURCE, sp, now):
                return
            rec = store(sp, mod.SOURCE, root, now, records, getter=getter, index=index)
            records.append(rec)
            index.add(rec)
            out.append(rec)
            if rec["result"] in ("saved", "unchanged"):
                got[sp["name"]] = read_raw(root, rec) if rec["result"] == "saved" else latest_bytes(root, index, mod.SOURCE, sp["name"])
            if rec["result"] in BAD:
                what = f"{mod.SOURCE} {sp['name']} ({rec.get('error') or rec.get('status')}{', header changed' if rec['result'].startswith('invalid') else ''})"
                # a daily file that fails is a STOP. A dated file that fails is a note (a market holiday never gets
                # one); a dated source that has published nothing for DARK_WEEKDAYS weekdays is a STOP (dark_kinds).
                # Weekly and monthly failures are notes.
                (stops if sp["cadence"] == "daily" else notes).append(("latest-day file failed: " if sp["cadence"] == "daily" else "file failed: ") + what)
            sleep()

        try:
            specs = mod.plan(ctx)
        except Exception as err:  # noqa: BLE001
            stops.append(f"{mod.SOURCE}: plan failed: {type(err).__name__}: {err}")
            continue
        for sp in specs:
            grab(sp)
        if hasattr(mod, "followups"):
            try:
                for sp in mod.followups(ctx, got):
                    grab(sp)
            except Exception as err:  # noqa: BLE001
                stops.append(f"{mod.SOURCE}: follow-ups failed: {type(err).__name__}: {err}")
        for kind, newest in dark_kinds(index, mod.SOURCE, specs, now).items():
            stops.append(f"{mod.SOURCE}: no {kind} file saved for any weekday since {newest or 'the first run'} (source dark for over {DARK_WEEKDAYS} weekdays)")
        if not funds and getattr(mod, "NEEDS_FUNDS", True):
            notes.append(f"{mod.SOURCE}: no funds in the universe file")
    return out, stops, notes


def dark_kinds(index, source, specs, now):
    """For each kind of dated file an issuer publishes, the newest saved file date when it is older than
    DARK_WEEKDAYS weekdays before today, or None when nothing was ever saved although runs on more than
    DARK_WEEKDAYS distinct days asked for it. Returns {kind: newest_date_text_or_None}; empty = all fine."""
    if not isinstance(index, Index):
        index = Index(index)
    out = {}
    dated = [sp for sp in specs if sp["cadence"] == "dated"]
    if not dated:
        return out
    limit = weekdays_back(now.date(), 14)[-(DARK_WEEKDAYS + 1)].isoformat()   # today minus DARK_WEEKDAYS weekdays
    for kind in {sp["kind"] for sp in dated}:
        mine = [r for sp in dated if sp["kind"] == kind for r in index.file(source, sp["name"])]
        mine += [r for (src, name), rs in index.by_file.items() if src == source for r in rs
                 if r.get("kind") == kind and r.get("cadence") == "dated" and r not in mine]
        saved = [r["date"] for r in mine if r.get("result") in ("saved", "unchanged") and r.get("date")]
        if saved:
            if max(saved) < limit:
                out[kind] = max(saved)
        elif len({r["fetched_utc"][:10] for r in mine}) > DARK_WEEKDAYS:
            out[kind] = None
    return out


def summary(records, stops, notes, now):
    """One status block for the run (markdown lines)."""
    counts = {}
    for r in records:
        counts[r["result"]] = counts.get(r["result"], 0) + 1
    by_source = {}
    for r in records:
        s = by_source.setdefault(r["source"], {})
        s[r["result"]] = s.get(r["result"], 0) + 1
    lines = [f"## {now.strftime('%Y-%m-%d %H:%M')} UTC: {'STOP' if stops else 'ok'}",
             "- totals: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))]
    lines += [f"- {src}: " + ", ".join(f"{k} {v}" for k, v in sorted(c.items())) for src, c in sorted(by_source.items())]
    lines += [f"- STOP: {s}" for s in stops] + [f"- note: {n}" for n in notes]
    return lines


def published_at(day, hour_utc, next_day=False):
    """UTC time from which an issuer's file for `day` exists: `hour_utc` on that day (or the next)."""
    d = day + timedelta(days=1) if next_day else day
    return datetime(d.year, d.month, d.day, hour_utc, tzinfo=timezone.utc)
