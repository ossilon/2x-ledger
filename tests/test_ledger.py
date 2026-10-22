"""Hash-chained hypothesis ledger: appends, verifies, and catches any later edit."""
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from _harness import check, raises
import ledger

T = datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)
with tempfile.TemporaryDirectory() as tmp:
    q = Path(tmp) / "protocol.jsonl"
    ledger.append({"kind": "protocol", "id": "P1", "rules": ["rule one", "rule two"]}, q, now=T)
    check("a protocol entry is accepted and rendered at the top", "## Protocol P1" in ledger.render(q) and "- rule two" in ledger.render(q))
    raises("a protocol with rules as plain text (not a list) is refused",
           lambda: ledger.append({"kind": "protocol", "id": "P2", "rules": "one long string"}, q), "list of sentences")

with tempfile.TemporaryDirectory() as tmp:
    p = Path(tmp) / "hypotheses.jsonl"
    h = {"kind": "hypothesis", "id": "H99", "claim": "c", "test": "t", "pass_if": "x", "review_on": "2027-01-01"}
    e1 = ledger.append(h, p, now=T)
    check("first entry links to the all-zero genesis hash", e1["prev_hash"] == ledger.GENESIS)
    check("the record stamp is a date, never a clock time", e1["recorded_utc"] == "2026-10-22")
    e2 = ledger.append({"kind": "parked", "id": "H98", "claim": "c", "why_parked": "w", "better_test": "b"}, p, now=T)
    check("second entry links to the first entry's hash", e2["prev_hash"] == e1["row_hash"])
    check("an untouched ledger verifies", ledger.verify(p) == (True, "chain intact"))
    raises("re-freezing the same hypothesis is refused", lambda: ledger.append(h, p, now=T), "already in the ledger")
    raises("a verdict on an unknown hypothesis is refused",
           lambda: ledger.append({"kind": "verdict", "id": "H1", "result": "r", "evidence": "e"}, p), "no frozen")
    raises("a hypothesis without a pass rule is refused",
           lambda: ledger.append({"kind": "hypothesis", "id": "H97", "claim": "c", "test": "t", "review_on": "d"}, p), "missing fields")
    v = ledger.append({"kind": "verdict", "id": "H99", "result": "holds", "evidence": "e"}, p, now=T)
    check("a verdict is appended, never edited in", v["prev_hash"] == e2["row_hash"])
    md = ledger.render(p)
    check("rendered table shows the verdict as the status", "| holds |" in md and "chain intact" in md)
    lines = p.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["claim"] = "edited later"
    lines[0] = json.dumps(first, sort_keys=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, msg = ledger.verify(p)
    check("editing an earlier entry is detected", not ok and "line 1" in msg, msg)
    raises("nothing can be appended to a tampered ledger",
           lambda: ledger.append({"kind": "parked", "id": "H96", "claim": "c", "why_parked": "w", "better_test": "b"}, p), "refusing to append")
    check("an empty ledger renders without error", "0 entries" in ledger.render(p.parent / "none.jsonl"))

with tempfile.TemporaryDirectory() as tmp:
    crlf, lf = Path(tmp) / "crlf.jsonl", Path(tmp) / "lf.jsonl"
    ledger.append({"kind": "protocol", "id": "P1", "rules": ["r"]}, lf, now=T)
    ledger.append({"kind": "protocol", "id": "P2", "rules": ["r"]}, lf, now=T)
    check("a new ledger uses LF line endings", b"\r\n" not in lf.read_bytes() and lf.read_bytes().count(b"\n") == 2)
    crlf.write_bytes(lf.read_bytes().split(b"\n")[0] + b"\r\n")
    before = crlf.read_bytes()
    ledger.append({"kind": "protocol", "id": "P2", "rules": ["r"]}, crlf, now=T)
    after = crlf.read_bytes()
    check("an append keeps a CRLF ledger's earlier bytes and its CRLF ending", after.startswith(before) and after.endswith(b"\r\n") and after.count(b"\r\n") == 2)

# The project's own ledger, once frozen: FROZEN_* are filled in by scripts/freeze_hypotheses.py --freeze and then
# never change. Until the freeze, this block only checks that the file (if any) verifies.
FROZEN_LINES = 7                     # P1, H1-H4, H5-H6 parked; frozen 2026-10-22 before the first public commit
FROZEN_SHA256 = "120e53d156b0fbd52f4cfbf1ebb499acb1c0b7d37c92bb543dff782e894f363f"
real = ledger.DEFAULT_PATH
if real.exists():
    check("the project's hypothesis ledger verifies", ledger.verify(real)[0], ledger.verify(real)[1])
    if FROZEN_LINES:
        import hashlib
        raw = real.read_bytes().splitlines(keepends=True)
        check(f"the ledger still holds the {FROZEN_LINES} frozen entries", len(raw) >= FROZEN_LINES, len(raw))
        got = hashlib.sha256(b"".join(raw[:FROZEN_LINES])).hexdigest()
        check("the frozen entries' bytes match the pinned SHA-256", got == FROZEN_SHA256, got)
    rendered = (ledger.ROOT / "HYPOTHESES.md")
    check("HYPOTHESES.md is the current rendering of the ledger", rendered.exists() and rendered.read_text(encoding="utf-8") == ledger.render(real))
