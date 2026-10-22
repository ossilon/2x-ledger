"""Point-in-time cutoff for every loader in the Ledger.

    from captured_by import captured_by
    with captured_by("2026-10-31T23:59:59Z"):
        df = tv_capture.build("NASDAQ:TSLL")      # sees only files fetched at or before the cutoff

Every raw file carries the UTC time it was fetched (manifest `fetched_utc`). Inside the block, loaders ignore files
fetched after the cutoff, so a re-run for an old month uses exactly the data that existed then. Same idea as
target_funds/definedtarget/forward/parse.py captured_by (protocol P2: "each review uses the data captured by its
review date").
"""
from contextlib import contextmanager

_CUTOFF = [None]          # None = every saved file


@contextmanager
def captured_by(cutoff_utc):
    """Inside this block, loaders see only files with fetched_utc <= cutoff_utc ('YYYY-MM-DDTHH:MM:SSZ')."""
    _check(cutoff_utc)
    old = _CUTOFF[0]
    _CUTOFF[0] = cutoff_utc
    try:
        yield
    finally:
        _CUTOFF[0] = old


def cutoff():
    """The active cutoff, or None."""
    return _CUTOFF[0]


def allowed(fetched_utc, explicit=None):
    """True if a file fetched at `fetched_utc` is visible under the explicit cutoff, else the active one."""
    c = explicit if explicit is not None else _CUTOFF[0]
    return c is None or fetched_utc <= c


def _check(stamp):
    if not (isinstance(stamp, str) and len(stamp) == 20 and stamp[10] == "T" and stamp.endswith("Z")):
        raise ValueError(f"cutoff must look like 2026-10-31T23:59:59Z, got {stamp!r}")
