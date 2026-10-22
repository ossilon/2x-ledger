#!/usr/bin/env python3
"""The one market series outside the fund universe: the S&P 500 close, for the column beta_spx_under.

The series lives in data/reference/<name>_<sha12>.csv (private, git-ignored), two columns: date, close. Each
import writes a new file named by its content hash, so earlier copies stay replayable; the record in
data/reference/manifest.jsonl carries the file's SHA-256, the time the bars were fetched from their feed
(fetched_utc), the time of the copy (copied_utc) and a note on the source. The fetch time is the point-in-time
stamp: captured_by(cutoff) hides a copy whose bars were fetched after the cutoff, like every other input. The author's copy comes from a private price library (a TradingView CSV export topped up through the
TradingView MCP); a public clone can import any daily close series with the same two columns.

    py -I code\\domain\\benchmark.py import <source.csv> --fetched-utc 2026-01-31T21:00:00Z --source "..."
    py -I code\\domain\\benchmark.py status
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
SPX = "SP_SPX_close"


def reference_dir(root=ROOT):
    return Path(root) / "data" / "reference"


def read_manifest(root=ROOT):
    p = reference_dir(root) / "manifest.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def records(name=SPX, root=ROOT, cutoff=None):
    """Saved copies of `name` whose bars were fetched by the cutoff (explicit, else the active captured_by)."""
    if cutoff is not None:
        pit._check(cutoff)
    recs = [r for r in read_manifest(root) if r.get("result") == "saved" and r["name"] == name
            and pit.allowed(r["fetched_utc"], cutoff)]
    return sorted(recs, key=lambda r: (r["fetched_utc"], r["copied_utc"]))


def import_csv(src, fetched_utc, source, name=SPX, root=ROOT, copied_utc=None):
    """Copy the date and close columns of `src` into data/reference/<name>.csv and record it in the manifest."""
    pit._check(fetched_utc)
    df = pd.read_csv(src)
    cols = {c.lower(): c for c in df.columns}
    if "date" not in cols or "close" not in cols:
        raise ValueError(f"{src}: needs 'date' and 'close' columns, has {list(df.columns)}")
    out = pd.DataFrame({"close": pd.to_numeric(df[cols["close"]], errors="coerce").values},
                       index=pd.to_datetime(df[cols["date"]])).dropna()
    out.index.name = "date"
    if out.index.duplicated().any() or not out.index.is_monotonic_increasing:
        raise ValueError(f"{src}: duplicate or unsorted dates")
    if (out["close"] <= 0).any():
        raise ValueError(f"{src}: non-positive closes")
    folder = reference_dir(root)
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / f"{name}.tmp"
    out.to_csv(tmp, date_format="%Y-%m-%d", float_format="%.6f")
    sha = hashlib.sha256(tmp.read_bytes()).hexdigest()
    # content-addressed file name: a later import never overwrites an earlier copy, so a replay under an earlier
    # cutoff still finds its bytes (audit 2026-10-22, D05)
    dest = folder / f"{name}_{sha[:12]}.csv"
    if dest.exists() and dest.read_bytes() != tmp.read_bytes():
        raise ValueError(f"{dest.name}: exists with different bytes (hash collision?)")
    tmp.replace(dest)
    now = copied_utc or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    pit._check(now)
    rec = {"name": name, "path": dest.name, "rows": int(len(out)), "first": str(out.index[0].date()),
           "last": str(out.index[-1].date()), "sha256": sha,
           "fetched_utc": fetched_utc, "copied_utc": now, "source": source, "result": "saved"}
    with (folder / "manifest.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")
    return rec


def closes(name=SPX, root=ROOT, cutoff=None):
    """The latest copy under the cutoff as a float Series indexed by date; attrs carry the manifest record."""
    recs = records(name, root, cutoff)
    if not recs:
        raise FileNotFoundError(f"{name}: no reference copy whose bars were fetched by the cutoff; "
                                f"run  py -I code\\domain\\benchmark.py import <csv> --fetched-utc ...")
    rec = recs[-1]
    path = reference_dir(root) / rec["path"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != rec["sha256"]:
        raise ValueError(f"{path.name}: file hash differs from the manifest; reference copies must never change")
    s = pd.read_csv(path, index_col="date", parse_dates=True)["close"].astype(float)
    s.attrs.update(record=rec)
    return s


def spx_closes(root=ROOT, cutoff=None):
    return closes(SPX, root, cutoff)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    imp = sub.add_parser("import")
    imp.add_argument("src")
    imp.add_argument("--fetched-utc", required=True, help="when the bars were fetched from their feed, YYYY-MM-DDTHH:MM:SSZ")
    imp.add_argument("--source", required=True, help="one line on where the file came from")
    imp.add_argument("--name", default=SPX)
    sub.add_parser("status")
    a = ap.parse_args(argv)
    if a.cmd == "import":
        rec = import_csv(a.src, a.fetched_utc, a.source, name=a.name)
        print(f"saved {rec['path']}: {rec['rows']} rows {rec['first']} .. {rec['last']}  fetched {rec['fetched_utc']}  sha256 {rec['sha256'][:12]}")
    else:
        for r in read_manifest():
            print(f"{r['name']:14s} {r['rows']:6d} rows {r['first']} .. {r['last']}  fetched {r['fetched_utc']}  copied {r['copied_utc']}  {r['source']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
