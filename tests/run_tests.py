#!/usr/bin/env python3
"""Run every test. From twox_ledger/:   py -I tests\\run_tests.py         (must end with "0 failure(s)")

Optional: name parts to run a subset, e.g.  py -I tests\\run_tests.py capture   (runs test_capture.py only).

1. Imports each tests/test_*.py in name order. Test code runs on import and records results through _harness.
2. Imports each tests/*_local.py (private cross-checks; git-ignored). Prints a note if there are none.
3. Prints "N failure(s)" and exits 1 if anything failed.
"""
import importlib
import sys
import time
import traceback
from pathlib import Path

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS))
import _harness  # noqa: E402


def run_module(path):
    print(f"\n===== {path.name} =====")
    t0 = time.perf_counter()
    try:
        importlib.import_module(path.stem)
    except Exception:  # noqa: BLE001
        print(traceback.format_exc())
        _harness.check(f"{path.name} ran to the end without crashing", False, "see traceback above")
    print(f"----- {path.name}: {time.perf_counter() - t0:.2f} s")


def main(selectors):
    def wanted(p):
        return not selectors or any(s in p.stem for s in selectors)

    t0 = time.perf_counter()
    for path in sorted(TESTS.glob("test_*.py")):
        if wanted(path):
            run_module(path)
    local = [p for p in sorted(TESTS.glob("*_local.py")) if wanted(p)]
    if local:
        for path in local:
            run_module(path)
    elif not selectors:
        print("\nlocal cross-check: skipped (file absent)")
    n = len(_harness.failures)
    if n:
        print("\nFailed:\n  " + "\n  ".join(_harness.failures))
    print(f"\ntotal time {time.perf_counter() - t0:.1f} s")
    print(f"\n{n} failure(s)")
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
