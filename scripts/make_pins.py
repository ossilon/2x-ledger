#!/usr/bin/env python3
"""Pin the ledger rows of one as-of date to data/pins/<asof>.json (private), so a later engine change is noticed.

    py -I scripts\\make_pins.py --asof 2026-09-30            writes the pin file; refuses to overwrite
    py -I scripts\\make_pins.py --asof 2026-09-30 --repin    overwrites (say why in the commit message)

The pin holds the inputs hash and every numeric column of every row, rounded to 6 decimals. tests/test_pins.py
recomputes three funds and compares; it skips when the private data is absent (a public clone).
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PIN_FUNDS = ["TSLL", "MSTU", "SMCX"]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", required=True)
    ap.add_argument("--repin", action="store_true")
    a = ap.parse_args(argv)
    ledger = pd.read_csv(ROOT / "ledger.csv", dtype=str)
    rows = ledger[ledger["asof"] == a.asof]
    if rows.empty:
        sys.exit(f"no ledger rows for {a.asof}")
    rows = rows[rows["restates"].fillna("") == ""] if "restates" in rows else rows
    dest = ROOT / "data" / "pins" / f"{a.asof}.json"
    if dest.exists() and not a.repin:
        sys.exit(f"{dest} exists; pass --repin to overwrite and record why in the commit message")
    numeric = {}
    for _, r in rows.iterrows():
        vals = {}
        for c, v in r.items():
            try:
                vals[c] = round(float(v), 6)
            except (TypeError, ValueError):
                continue
        numeric[r["ticker"]] = vals
    pin = {"asof": a.asof, "inputs_sha256": rows["inputs_sha256"].iloc[0], "schema_version": int(rows["schema_version"].iloc[0]),
           "pin_funds": PIN_FUNDS, "rows": numeric}
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(pin, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"pinned {len(numeric)} rows for {a.asof} -> {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
