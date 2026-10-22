"""Reference series store: content-addressed copies keep every version replayable under its own cutoff."""
import shutil
import tempfile
from pathlib import Path

import pandas as pd

from _harness import check, raises
import benchmark as bm
from captured_by import captured_by

root = Path(tempfile.mkdtemp(prefix="ledger_bench_"))
src = root / "s.csv"
pd.DataFrame({"date": ["2024-01-02", "2024-01-03"], "close": [100.0, 101.0]}).to_csv(src, index=False)
r1 = bm.import_csv(src, "2024-01-15T00:00:00Z", "v1", root=root, copied_utc="2024-01-15T01:00:00Z")
pd.DataFrame({"date": ["2024-01-02", "2024-01-03"], "close": [100.0, 102.0]}).to_csv(src, index=False)
r2 = bm.import_csv(src, "2024-02-15T00:00:00Z", "v2", root=root, copied_utc="2024-02-15T01:00:00Z")
check("two imports write two files named by their content hash", r1["path"] != r2["path"] and r1["sha256"][:12] in r1["path"] and (root / "data" / "reference" / r1["path"]).exists())
jan = bm.spx_closes(root, cutoff="2024-01-31T23:59:59Z")
feb = bm.spx_closes(root, cutoff="2024-02-28T23:59:59Z")
check("a January cutoff replays the first copy after a February import (audit D05)", jan.iloc[-1] == 101.0 and feb.iloc[-1] == 102.0, (jan.iloc[-1], feb.iloc[-1]))
with captured_by("2024-01-31T23:59:59Z"):
    check("the active captured_by cutoff selects the same copy", bm.spx_closes(root).iloc[-1] == 101.0)
raises("no copy under an early cutoff is a clear error", lambda: bm.spx_closes(root, cutoff="2024-01-01T00:00:00Z"), "no reference copy")
# the same content imported again reuses the file and adds a record
r3 = bm.import_csv(src, "2024-03-15T00:00:00Z", "v2 again", root=root, copied_utc="2024-03-15T01:00:00Z")
check("re-importing identical content reuses the file", r3["path"] == r2["path"] and len(bm.read_manifest(root)) == 3)
shutil.rmtree(root, ignore_errors=True)
