"""The identifier scan: gitignore matching, data-file rules, shape checks, clock times, and the repository itself."""
import json
import sys
import tempfile
from pathlib import Path

from _harness import check, ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import scan_identifiers as si  # noqa: E402

pats = si.ignore_patterns()
check("data files are ignored", si.ignored("data/raw/tradingview/2026-10-21/x.json", pats))
check("data/README.md is published (negated pattern)", not si.ignored("data/README.md", pats))
check("local cross-checks are ignored", si.ignored("tests/port_local.py", pats))
check("the hypothesis draft is ignored", si.ignored("forward/hypotheses_draft.json", pats))
check("the frozen ledger is published", not si.ignored("forward/hypotheses.jsonl", pats))
check("ledger.csv is published", not si.ignored("ledger.csv", pats))
check("the private identifier list is ignored", si.ignored("identifiers_local.txt", pats))

series = "\n".join(f"2024-01-{d:02d},100.{d},101.{d}" for d in range(1, 8))
check("seven dated numeric rows look like a daily series", si.daily_series_rows(series) == 7)
check("a one-column dated series counts too (audit U04)", si.daily_series_rows("\n".join(f"2024-01-{d:02d},0.0{d}" for d in range(1, 8))) == 7)
check("a leverage-period table passes the shape check",
      si.shape_problems("register_leverage.csv", si.LEVERAGE_HEAD + ",source,note\nNASDAQ:TSLL,TSLL,1.5,2022-08-09,2024-04-02,src,\nNASDAQ:TSLL,TSLL,2.0,2024-04-02,,src,\n") == [])
check("a leverage table with a price-like row fails", si.shape_problems("register_leverage.csv", si.LEVERAGE_HEAD + "\n2024-01-02,TSLL,100.5,2024-01-02,\n") != [])
check("a windows table is an allowed data file", si.allowed_data("results/2026-09/windows.csv"))
check("a manifest is an allowed data file", si.allowed_data("results/manifests/2026-09.json"))
check("a stray CSV is not", not si.allowed_data("results/2026-09/daily.csv"))

good_w = si.WINDOWS_HEADER + "\n2026-09-30,TSLL,Y2024,2023-12-29,2024-12-31,1.0,2.0,3.0,4.0,5.0,6.0,0.1,0.2,0.3,2.0\n"
bad_w = si.WINDOWS_HEADER + "\n2026-09-30,TSLL,D20240102,2024-01-01,2024-01-02,1.0,2.0,3.0,4.0,5.0,6.0,0.1,0.2,0.3,2.0\n"
check("a windows table with year and trailing labels passes the shape check", si.shape_problems("results/2026-09/windows.csv", good_w) == [])
check("a windows table with a daily label fails the shape check", len(si.shape_problems("results/2026-09/windows.csv", bad_w)) == 1)
man = {"asof": "2026-09-30", "run_date_utc": "2026-10-22", "schema_version": 1, "funds": 21, "cutoff": "2026-10-21T23:59:59Z",
       "inputs": [{"kind": "tradingview", "path": "a.json", "sha256": "0" * 64}], "inputs_sha256": "0" * 64,
       "ledger_sha256": "0" * 64, "windows_sha256": "0" * 64}
check("a run manifest passes the shape check", si.shape_problems("results/manifests/2026-09.json", json.dumps(man)) == [])
check("a manifest with an extra key fails", si.shape_problems("results/manifests/2026-09.json", json.dumps({**man, "bars": []})) != [])
check("a manifest whose input carries extra fields fails",
      si.shape_problems("results/manifests/2026-09.json", json.dumps({**man, "inputs": [{"kind": "x", "path": "p", "sha256": "s", "close": 1.0}]})) != [])
check("ledger rows must start with the schema version and two dates",
      si.shape_problems("ledger.csv", si.LEDGER_HEAD + "x\n1,2026-09-30,2026-10-22,TSLL\n") == []
      and si.shape_problems("ledger.csv", si.LEDGER_HEAD + "x\n2026-09-30,1.0,2.0,TSLL\n") != [])
check("a clock time is flagged, an end-of-day cutoff is not",
      si.clock_times("run 2026-10-22T02:09:47Z") == ["2026-10-22T02:09:47Z"] and si.clock_times("cutoff 2026-10-21T23:59:59Z") == [])
check("the LICENSE copyright line keeps the handle out of the personal-term check",
      si.without_attribution("LICENSE", "Copyright (c) 2026 handle", "handle", None) == "Copyright (c) 2026 ")
check("the handle elsewhere in the file still counts",
      si.without_attribution("LICENSE", "written by handle", "handle", None) == "written by handle")

with tempfile.TemporaryDirectory() as tmp:
    t = Path(tmp)
    (t / "notes.md").write_text("see C:\\" + "Users\\someone\\x and mail me at a.b" + "@example.com\n" + series + "\n", encoding="utf-8")
    probs = si.scan([("notes.md", t / "notes.md")], personal=[], handle=None, url=None)
    kinds = " ".join(probs)
    check("the scan finds a home path, an email and a pasted series in one file",
          "home directory path" in kinds and "email address" in kinds and "daily series" in kinds, probs)

# the repository itself: the gate every commit must pass. The private term list exists only on the author's machine;
# a public clone runs the generic checks (paths, emails, secrets, clock times, data files, spellings) without it.
personal = si.personal_terms()
if personal is None:
    print("     identifiers_local.txt absent (a public clone): personal-term check skipped, generic checks run")
problems = si.scan(personal=personal or [])
check("the files git would publish carry no identifier, secret, clock time or data file", problems == [], "\n".join(problems[:15]))
