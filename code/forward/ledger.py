"""Pre-registered hypotheses: an append-only, hash-chained ledger (forward/hypotheses.jsonl).

Plain words
- A forward test means something only if the hypotheses go on record BEFORE the data that tests them.
- Each entry is one JSON line. It stores the SHA-256 fingerprint of the previous line ("prev_hash") and of itself
  ("row_hash"). A change to an earlier entry changes its fingerprint and breaks every later link, so `verify()`
  catches a careless edit. It cannot catch a deliberate rewrite: anyone can recompute every later hash, and an
  empty or shortened file also verifies. Proof of WHEN the entries existed comes from outside the file: the public
  git history and a test that pins the frozen entries' fingerprint (tests/test_ledger.py).
- Never edit or delete an entry. To resolve a hypothesis, append a "verdict" entry that names it.
- Appends keep the file's existing line endings, so the bytes of earlier lines never change.

Kinds: "protocol" (the shared rules every test follows), "hypothesis" (frozen, with a test rule and a review
date), "parked" (written down, not yet testable), "verdict" (the result, appended later).

Same design as the author's target_funds ledger (definedtarget/ledger.py, October 2026), ported here so this
repository stands alone.
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _paths  # noqa: E402,F401

ROOT = _paths.ROOT
DEFAULT_PATH = ROOT / "forward" / "hypotheses.jsonl"
GENESIS = "0" * 64
KINDS = {"protocol", "hypothesis", "parked", "verdict"}
REQUIRED = {"protocol": ("id", "rules"),
            "hypothesis": ("id", "claim", "test", "pass_if", "review_on"),
            "parked": ("id", "claim", "why_parked", "better_test"),
            "verdict": ("id", "result", "evidence")}


def _hash(prev_hash, body):
    canonical = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()


def read(path=DEFAULT_PATH):
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def verify(path=DEFAULT_PATH):
    """(ok, message): every line links to the one before and its own fingerprint matches its content."""
    prev = GENESIS
    for i, e in enumerate(read(path), 1):
        body = {k: v for k, v in e.items() if k not in ("prev_hash", "row_hash")}
        if e.get("prev_hash") != prev:
            return False, f"line {i}: chain broken (prev_hash does not match line {i - 1})"
        if _hash(prev, body) != e.get("row_hash"):
            return False, f"line {i}: content changed after it was written"
        prev = e["row_hash"]
    return True, "chain intact"


def append(entry, path=DEFAULT_PATH, now=None):
    """Append one entry (validated), returning it with its hashes. Refuses a broken chain or a duplicate."""
    kind = entry.get("kind")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {sorted(KINDS)}")
    missing = [k for k in REQUIRED[kind] if not entry.get(k)]
    if missing:
        raise ValueError(f"missing fields for a {kind}: {missing}")
    ok, msg = verify(path)
    if not ok:
        raise ValueError(f"refusing to append: {msg}")
    existing = read(path)
    if kind == "protocol" and not isinstance(entry.get("rules"), list):
        raise ValueError("a protocol's rules must be a list of sentences")
    if kind != "verdict" and any(e["id"] == entry["id"] and e["kind"] != "verdict" for e in existing):
        raise ValueError(f"{entry['id']} is already in the ledger (resolve it with a verdict, never re-freeze)")
    if kind == "verdict" and not any(e["id"] == entry["id"] and e["kind"] == "hypothesis" for e in existing):
        raise ValueError(f"no frozen hypothesis {entry['id']} to give a verdict on")
    body = dict(entry)
    body["recorded_utc"] = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")   # the date only, never the hour
    prev = existing[-1]["row_hash"] if existing else GENESIS
    full = {**body, "prev_hash": prev, "row_hash": _hash(prev, body)}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    eol = "\r\n" if path.exists() and b"\r\n" in path.read_bytes() else "\n"
    with open(path, "a", encoding="utf-8", newline="") as fh:
        fh.write(json.dumps(full, ensure_ascii=False, sort_keys=True) + eol)
    return full


def render(path=DEFAULT_PATH):
    """Markdown view of the ledger (for HYPOTHESES.md). Written in short sentences for a general reader."""
    entries = read(path)
    ok, msg = verify(path)
    verdicts = {}
    for e in entries:
        if e["kind"] == "verdict":
            verdicts.setdefault(e["id"], []).append(e)
    L = ["# Hypotheses on record", "",
         "A script (`code/forward/ledger.py`) makes this page from `forward/hypotheses.jsonl`. Do not edit it by hand.",
         f"Chain check: **{msg}** ({len(entries)} entries). Each entry carries the hash of the entry before it. "
         "The git history shows when each entry went on record.", ""]
    for e in entries:
        if e["kind"] == "protocol":
            L += [f"## Protocol {e['id']} (on record {e['recorded_utc'][:10]})", ""] + [f"- {r}" for r in e["rules"]] + [""]
    hyps = [e for e in entries if e["kind"] == "hypothesis"]
    L += ["## Hypotheses", "", "| ID | On record | Claim | Review on | Status |", "|---|---|---|---|---|"]
    for e in hyps:
        status = "; ".join(v["result"] for v in verdicts.get(e["id"], [])) or "open"
        L.append(f"| {e['id']} | {e['recorded_utc'][:10]} | {e['claim']} | {e['review_on']} | {status} |")
    for e in hyps:
        L += ["", f"### {e['id']}: {e['claim']}", "", f"- **Test:** {e['test']}", f"- **Pass if:** {e['pass_if']}"]
        if e.get("if_fail_means"):
            L.append(f"- **If it fails:** {e['if_fail_means']}")
        if e.get("exploratory"):
            L.append(f"- **Before the freeze (shaped the band, tests nothing):** {e['exploratory']}")
        L.append(f"- **Review on:** {e['review_on']}")
    parked = [e for e in entries if e["kind"] == "parked"]
    if parked:
        L += ["", "## Parked (on record, not yet testable)", "", "| ID | On record | Claim | Why parked | Better test |",
              "|---|---|---|---|---|"]
        for e in parked:
            L.append(f"| {e['id']} | {e['recorded_utc'][:10]} | {e['claim']} | {e['why_parked']} | {e['better_test']} |")
    if verdicts:
        L += ["", "## Verdicts", ""]
        for e in entries:
            if e["kind"] == "verdict":
                L.append(f"- **{e['id']}** ({e['recorded_utc'][:10]}): {e['result']}. {e['evidence']}")
    return "\n".join(L) + "\n"
