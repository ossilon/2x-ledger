#!/usr/bin/env python3
"""Run the issuer capture once (the scheduled job and the user run the same command). Standard library only.

    py -I scripts\\daily_capture.py                                  data root data/, universe data/register/universe.csv
    py -I scripts\\daily_capture.py --root <dir> --universe <csv>    the cloud job: root twox_ledger/ in the capture repository
    py -I scripts\\daily_capture.py --only tradr                      one issuer (the morning pass for Tradr's ICE file)
    py -I scripts\\daily_capture.py --plan                            list what would be fetched now, fetch nothing

Writes one status block to <root>/status.md (newest first) and prints it. Exit code 1 when the run has a STOP
line (a daily file failed or changed its header), so a scheduled job reports failure and its owner gets mail.
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
import _paths  # noqa: E402,F401
import issuer_capture as ic  # noqa: E402

ROOT = _paths.ROOT


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT / "data"), help="data root holding raw/ and manifest.jsonl")
    ap.add_argument("--universe", default=None, help="universe.csv (default <root>/register/universe.csv, else <root>/universe.csv)")
    ap.add_argument("--only", nargs="*", default=None, help="issuer keys to run")
    ap.add_argument("--status", default=None, help="status file (default <root>/status.md)")
    ap.add_argument("--now", default=None, help="UTC time to run as, ISO 8601 (tests)")
    ap.add_argument("--plan", action="store_true", help="print the due specs and exit")
    ap.add_argument("--no-pause", action="store_true")
    a = ap.parse_args(argv)
    root = Path(a.root)
    uni = Path(a.universe) if a.universe else next((p for p in (root / "register" / "universe.csv", root / "universe.csv") if p.exists()), None)
    if uni is None or not uni.exists():
        print("universe file not found; pass --universe", file=sys.stderr)
        return 2
    now = datetime.fromisoformat(a.now.replace("Z", "+00:00")) if a.now else datetime.now(timezone.utc)
    universe = ic.load_universe(uni)
    if a.plan:
        records = ic.port.read_manifest(root)
        index = ic.Index(records)
        n = 0
        for key in ic.ISSUERS:
            if a.only and key not in a.only:
                continue
            mod = ic.adapter(key)
            ctx = SimpleNamespace(now=now, today=now.date(), funds=universe.get(key, []), records=records, root=root, source=mod.SOURCE, notes=[])
            for sp in mod.plan(ctx):
                if ic.due(index, mod.SOURCE, sp, now):
                    print(f"{mod.SOURCE:16s} {sp['cadence']:7s} {sp['kind']:8s} {sp['name']}")
                    n += 1
        print(f"{n} files due (follow-ups not counted)")
        return 0
    sleep = (lambda: None) if a.no_pause else ic.port.pause
    records, stops, notes = ic.run(root, universe, now=now, only=a.only, sleep=sleep)
    block = ic.summary(records, stops, notes, now)
    status = Path(a.status) if a.status else root / "status.md"
    status.parent.mkdir(parents=True, exist_ok=True)
    old = status.read_text(encoding="utf-8") if status.exists() else "# twox_ledger issuer capture status\n"
    head, _, rest = old.partition("\n")
    status.write_text(head + "\n\n" + "\n".join(block) + "\n" + rest.lstrip("\n"), encoding="utf-8")
    print("\n".join(block))
    return 1 if stops else 0


if __name__ == "__main__":
    sys.exit(main())
