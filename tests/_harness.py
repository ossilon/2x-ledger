"""Shared test helpers. No pytest needed. Same contract as target_funds/tests/_harness.py (copied as scaffolding).

CONTRACT for every tests/test_*.py module (and tests/*_local.py cross-checks):

    from _harness import check, raises

    check("what must be true, in plain words", condition, detail_shown_only_on_failure)
    raises("what must be refused", lambda: some_call(...), "text the error message must contain")

- Test code sits at module level and runs when the runner imports the module.
- check() prints "ok   <name>" or "FAIL <name>  (<detail>)" and records failures in `failures`.
- raises() passes only if the call raises AND the message contains `must_contain` (case-insensitive).
- tests/run_tests.py imports every test module in name order, then counts `failures` once at the end.
- Importing this module puts twox_ledger/ and twox_ledger/code on sys.path and loads code/_paths.py, so every
  project module imports by bare name from any test. The project has no imports outside itself (code/port.py
  holds the helpers ported from the author's sibling kits; tests/port_local.py checks them against the originals).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # twox_ledger/
for p in (ROOT, ROOT / "code"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
import _paths  # noqa: E402,F401  (project code folders on sys.path)

failures = []


def check(name, cond, detail=""):
    """Record one test: `cond` must be truthy."""
    cond = bool(cond)
    detail = str(detail)
    print(("ok   " if cond else "FAIL ") + name + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        failures.append(name)


def raises(name, fn, must_contain):
    """Record one test: fn() must raise an exception whose message contains `must_contain`."""
    try:
        fn()
    except Exception as err:  # noqa: BLE001
        check(name, must_contain.lower() in str(err).lower(), f"wrong error: {type(err).__name__}: {err}")
        return
    check(name, False, "did not raise")
