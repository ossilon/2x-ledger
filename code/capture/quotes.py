#!/usr/bin/env python3
"""Monthly quote snapshot from the TradingView MCP tool mcp-tv-get-symbol-data-batch, stored raw.

One reply per month covers every fund and stock in the register: expense ratio, AUM, NAV, premium/discount, fund
flows (1M, 3M, YTD, 1Y), average volumes, distribution yield, close. The reply is saved as it arrived under
data/raw/quotes/<UTC date>/ and listed in manifest.jsonl with SHA-256 and fetch time. Only derived columns are
published (ledger.csv); the raw snapshot never leaves data/.

    py -I code\\capture\\quotes.py ingest REPLY.json [--fetched-utc 2026-10-22T20:15:00Z]
    py -I code\\capture\\quotes.py show [--cutoff 2026-10-31T23:59:59Z]

In code: quotes.latest(cutoff=None) -> (record, DataFrame indexed by EXCHANGE:TICKER with the reply's columns).
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _paths  # noqa: E402,F401
import captured_by as pit  # noqa: E402

ROOT = _paths.ROOT


def raw_dir(root=ROOT):
    return Path(root) / "data" / "raw" / "quotes"


def read_manifest(root=ROOT):
    p = raw_dir(root) / "manifest.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def records(root=ROOT, cutoff=None):
    if cutoff is not None:
        pit._check(cutoff)
    recs = [r for r in read_manifest(root) if r.get("result") == "saved" and pit.allowed(r["fetched_utc"], cutoff)]
    return sorted(recs, key=lambda r: (r["fetched_utc"], r["path"]))


def parse_reply(raw_bytes, source="reply"):
    data = json.loads(raw_bytes.decode("utf-8"))
    if data.get("success") is not True:
        raise ValueError(f"{source}: reply has success={data.get('success')!r}")
    rows = data.get("data")
    if not isinstance(rows, dict) or not rows:
        raise ValueError(f"{source}: reply has no data map")
    if data.get("count") is not None and int(data["count"]) != len(rows):
        raise ValueError(f"{source}: count {data['count']} differs from {len(rows)} symbols in data")
    for sym in rows:
        if ":" not in sym:
            raise ValueError(f"{source}: symbol {sym!r} is not EXCHANGE:TICKER")
    return data


def ingest(src, root=ROOT, fetched_utc=None):
    src = Path(src)
    raw_bytes = src.read_bytes()
    data = parse_reply(raw_bytes, src.name)
    fetched_utc = fetched_utc or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    pit._check(fetched_utc)
    digest = hashlib.sha256(raw_bytes).hexdigest()
    for r in read_manifest(root):
        if r.get("sha256") == digest:
            return r
    day = fetched_utc[:10]
    folder = raw_dir(root) / day
    folder.mkdir(parents=True, exist_ok=True)
    dest, k = folder / f"quotes_{day}.json", 2
    while dest.exists():
        dest, k = folder / f"quotes_{day}-{k}.json", k + 1
    dest.write_bytes(raw_bytes)
    rec = {"path": dest.relative_to(raw_dir(root)).as_posix(), "symbols": len(data["data"]),
           "missing": list(data.get("missing", [])), "fetched_utc": fetched_utc, "sha256": digest, "result": "saved"}
    with (raw_dir(root) / "manifest.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")
    return rec


def latest(root=ROOT, cutoff=None):
    recs = records(root, cutoff)
    if not recs:
        raise FileNotFoundError("no quote snapshot saved (under the cutoff)")
    rec = recs[-1]
    raw = (raw_dir(root) / rec["path"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != rec["sha256"]:
        raise ValueError(f"{rec['path']}: file hash differs from the manifest; raw files must never change")
    data = json.loads(raw)["data"]
    df = pd.DataFrame.from_dict(data, orient="index")
    df.index.name = "symbol"
    df.attrs.update(source=rec["path"], fetched_utc=rec["fetched_utc"])
    return rec, df


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_in = sub.add_parser("ingest")
    p_in.add_argument("file")
    p_in.add_argument("--fetched-utc", default=None)
    p_s = sub.add_parser("show")
    p_s.add_argument("--cutoff", default=None)
    a = ap.parse_args(argv)
    if a.cmd == "ingest":
        r = ingest(a.file, fetched_utc=a.fetched_utc)
        print(f"saved {r['symbols']} symbols -> {r['path']} (missing: {r['missing']})")
    else:
        rec, df = latest(cutoff=a.cutoff)
        cols = [c for c in ("brand", "expense_ratio", "aum", "nav_discount_premium", "dividends_yield", "fund_flows.1M") if c in df]
        print(f"snapshot {rec['path']} fetched {rec['fetched_utc']}")
        print(df[cols].to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
