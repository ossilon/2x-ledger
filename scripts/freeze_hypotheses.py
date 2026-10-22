#!/usr/bin/env python3
"""Freeze the approved hypotheses into the hash-chained ledger and render HYPOTHESES.md.

    py -I scripts\\freeze_hypotheses.py            shows what it would freeze; changes nothing
    py -I scripts\\freeze_hypotheses.py --freeze   appends every draft entry not already in the ledger

Run --freeze only after the wording in forward/hypotheses_draft.json (private) is approved. After the first public
commit, never edit frozen entries: add results later as verdict entries. After a freeze, copy the printed line
count and SHA-256 into tests/test_ledger.py (FROZEN_LINES, FROZEN_SHA256) so a later change to those bytes fails.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))
import _paths  # noqa: E402,F401
import ledger  # noqa: E402

DRAFT = ROOT / "forward" / "hypotheses_draft.json"


def main(argv):
    draft = json.loads(DRAFT.read_text(encoding="utf-8"))
    have = {e["id"] for e in ledger.read() if e["kind"] != "verdict"}
    todo = [e for e in draft if e["id"] not in have]
    for e in todo:
        label = e.get("claim") or f"{len(e.get('rules', []))} rules"
        print(f"{'FREEZE' if '--freeze' in argv else 'would freeze'} {e['kind']:<10} {e['id']}: {label[:90]}")
    if "--freeze" in argv:
        for e in todo:
            ledger.append(e)
        (ROOT / "HYPOTHESES.md").write_text(ledger.render(), encoding="utf-8", newline="\n")
        raw = ledger.DEFAULT_PATH.read_bytes()
        print(ledger.verify())
        print(f"lines {len(raw.splitlines())}  sha256 {hashlib.sha256(raw).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
