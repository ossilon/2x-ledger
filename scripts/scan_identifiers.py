#!/usr/bin/env python3
"""Refuse to publish personal identifiers, secrets, clock times or data files. Run before every commit:

    py -I scripts\\scan_identifiers.py          (must print "0 problem(s)")

It checks every file that git would publish (everything .gitignore does not exclude, matched the way git matches):
1. personal terms from the PRIVATE list identifiers_local.txt (git-ignored, so the list itself is never published),
   in file contents and file names. The author's public handle may appear only where attribution needs it: the
   LICENSE copyright line, the CITATION.cff author line, the README citation line and the repository URL. The scan
   reads the handle and the URL from CITATION.cff, so this code never names them;
2. generic leaks: Windows/Unix home-directory paths, email addresses, strings that look like API keys or tokens,
   clock-time stamps in public documents and data (public files carry dates, never the hour of the author's work;
   a cutoff at the end of a UTC day is allowed), plus British spellings (the public style rule is American English);
3. data files that must never be published: CSV/JSON/JSONL/XLS/PDF/Parquet outside docs/ and the allowed public
   tables (ledger.csv, register.csv, register_leverage.csv, results/<month>/windows.csv, results/manifests/*.json,
   forward/hypotheses.jsonl, reference/DFF.csv), each of which must have the shape the project's tools write; image
   files; text files with 5 or more dated numeric rows (a daily series pasted into a document).
The checks are heuristics: they catch the project's own output shapes and common leaks, not every possible one.

tests/test_scan_identifiers.py runs the same scan, so the test suite fails before any data can reach a commit.
Adapted from the author's target_funds scanner (October 2026).
"""
import functools
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".py", ".md", ".txt", ".json", ".jsonl", ".toml", ".cfg", ".ini", ".yml", ".yaml", ".html", ".js",
                 ".css", ".csv", ".gitignore", ".gitattributes", ".cff", ".svg", ""}
GENERIC = {
    # one or two backslashes: JSON doubles every backslash in a Windows path
    "home directory path": re.compile(r"[A-Za-z]:\\{1,2}Users\\{1,2}[^\\\s]+|/home/[a-z0-9_-]+|/Users/[A-Za-z0-9_-]+"),
    "email address": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "possible secret": re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]{8,}"),
    # public text credits "an independent audit", never the model or vendor that performed it (project rule)
    "named AI model or vendor": re.compile(r"(?i)\b(astra|gpt-?\d?|openai|chatgpt|anthropic|claude|gemini|opus|sonnet|copilot)\b"),
    "British spelling": re.compile(r"(?i)\b\w*(behaviour|licence|organis|recognis|summaris|centre|neighbour|favour"
                                   r"|colour|programme|labell|modell|cancell|catalogue|whilst|towards|realis|vectoris"
                                   r"|itemis|minimis|maximis|optimis|prioritis|parallelis|annualis|normalis|winsoris"
                                   r"|analys(?:e\b|ed|ing|er))\w*"),
}
# Public documents and data carry dates only. A stamp at the end of a UTC day (a chosen cutoff) is not a work time.
CLOCK_TIME = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?Z?\b")
CLOCK_ALLOWED = re.compile(r"T(?:23:59:59|00:00:00)Z?$")
CLOCK_SUFFIXES = {".md", ".csv", ".json", ".jsonl", ".cff", ".txt"}
ALLOWED_EMAILS = set()
DATA_SUFFIXES = {".csv", ".json", ".jsonl", ".xls", ".xlsx", ".pdf", ".parquet"}
ALLOWED_DATA_DIRS = ("docs/",)
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
ALLOWED_IMAGE_DIRS = ("docs/img/",)
# Public tables and records. Each must have the shape the project's tools write, so a pasted price series cannot pass.
ALLOWED_DATA_FILES = {"ledger.csv", "register.csv", "register_leverage.csv", "forward/hypotheses.jsonl", "reference/DFF.csv"}
LEVERAGE_HEAD = "symbol,ticker,target_leverage,effective_from,effective_to"
WINDOWS_FILE = re.compile(r"^results/\d{4}-\d{2}/windows\.csv$")
MANIFEST_FILE = re.compile(r"^results/manifests/\d{4}-\d{2}\.json$")
LEDGER_HEAD = "schema_version,asof,run_date_utc,ticker,symbol,issuer,underlying,status,target_leverage,inception_date,"
REGISTER_HEAD = "symbol,ticker,exchange,issuer,fund_name,underlying,inception_date,status,close_date,"
WINDOWS_HEADER = ("asof,ticker,window,start,end,fund_pct,stock_pct,naive_pct,ideal_pct,fedfunds_pct,bh_pct,compounding_pp,"
                  "rebalance_pp,residual_pp,L_start")
WINDOW_LABEL = re.compile(r"^(Y\d{4}|T1M|T3M|T12M)$")
MANIFEST_KEYS = {"asof", "run_date_utc", "schema_version", "funds", "cutoff", "inputs", "inputs_sha256", "ledger_sha256",
                 "windows_sha256"}
LEDGER_KINDS = {"protocol", "hypothesis", "parked", "verdict"}
# Attribution: where the handle may stand, per file (the handle must follow this prefix directly).
ATTRIBUTION_PREFIX = {"LICENSE": r"^Copyright \(c\) \d{4} ",
                      "CITATION.cff": r"^\s*-\s*(?:name|alias):\s*\"?",
                      "README.md": r"^> "}
URL_FILES = {"CITATION.cff", "README.md"}                 # files that may carry the repository URL


def allowed_data(rel):
    return rel in ALLOWED_DATA_FILES or bool(WINDOWS_FILE.match(rel)) or bool(MANIFEST_FILE.match(rel))


def shape_problems(rel, text):
    """Problems with an allowed public table or record whose shape is not what the project's tools write."""
    lines = text.splitlines()
    if rel == "ledger.csv":
        if not lines or not lines[0].startswith(LEDGER_HEAD):
            return [f"{rel}: header is not the ledger schema"]
        bad = [i for i, l in enumerate(lines[1:], 2) if l.strip() and not re.match(r"^\d+,\d{4}-\d{2}-\d{2},\d{4}-\d{2}-\d{2},", l)]
        return [f"{rel}:{i}: not a ledger row" for i in bad[:5]]
    if rel == "register.csv":
        return [] if lines and lines[0].startswith(REGISTER_HEAD) else [f"{rel}: header is not the register schema"]
    if rel == "register_leverage.csv":
        if not lines or not lines[0].startswith(LEVERAGE_HEAD):
            return [f"{rel}: header is not the leverage-period schema"]
        bad = [i for i, l in enumerate(lines[1:], 2) if l.strip() and not re.match(r"^[A-Z]+:[A-Z]+,[A-Z]+,\d(\.\d+)?,\d{4}-\d{2}-\d{2},(\d{4}-\d{2}-\d{2})?(,|$)", l)]
        return [f"{rel}:{i}: not a leverage-period row" for i in bad[:5]]
    if rel == "reference/DFF.csv":
        return [] if lines and lines[0] == "observation_date,DFF" else [f"{rel}: header is not the FRED DFF file"]
    if WINDOWS_FILE.match(rel):
        if not lines or lines[0] != WINDOWS_HEADER:
            return [f"{rel}: header is not the windows schema"]
        bad = [i for i, l in enumerate(lines[1:], 2) if l.strip() and not WINDOW_LABEL.match(l.split(",")[2] if l.count(",") >= 2 else "")]
        return [f"{rel}:{i}: window label is not a year or trailing window (a daily row?)" for i in bad[:5]]
    try:
        if rel == "forward/hypotheses.jsonl":
            rows = [json.loads(l) for l in lines if l.strip()]
            bad = [i for i, r in enumerate(rows, 1) if not isinstance(r, dict) or r.get("kind") not in LEDGER_KINDS]
            return [f"{rel}:{i}: not a ledger entry" for i in bad]
        rec = json.loads(text)
    except ValueError:
        return [f"{rel}: not valid JSON"]
    ok = (isinstance(rec, dict) and set(rec) <= MANIFEST_KEYS and {"asof", "inputs", "inputs_sha256"} <= set(rec)
          and all(isinstance(i, dict) and set(i) == {"kind", "path", "sha256"} for i in rec.get("inputs", [])))
    return [] if ok else [f"{rel}: not a run manifest (unexpected keys)"]


def attribution(repo=REPO):
    """(handle, repository URL) from CITATION.cff; (None, None) if the file is missing."""
    path = Path(repo) / "CITATION.cff"
    if not path.exists():
        return None, None
    text = path.read_text(encoding="utf-8")
    h = re.search(r"^\s*-\s*(?:name|alias):\s*\"?([^\"\n]+?)\"?\s*$", text, re.MULTILINE)
    u = re.search(r"^repository-code:\s*\"?([^\"\n]+?)\"?\s*$", text, re.MULTILINE)
    return (h.group(1) if h else None), (u.group(1) if u else None)


def without_attribution(rel, line, handle, url):
    """The line with only the permitted attribution removed, so a personal term anywhere else still counts."""
    if url and rel in URL_FILES:
        line = line.replace(url, "")
    if handle and rel in ATTRIBUTION_PREFIX:
        line = re.sub(f"({ATTRIBUTION_PREFIX[rel]}){re.escape(handle)}", r"\1", line)
    return line


def ignore_patterns(repo=REPO):
    pats = []
    for line in (Path(repo) / ".gitignore").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            pats.append(line)
    return pats


@functools.lru_cache(maxsize=None)
def _rule(pattern):
    """(regex, negated, directory_only) for one .gitignore line, following gitignore(5)."""
    negated = pattern.startswith("!")
    pat = pattern[1:] if negated else pattern
    dir_only = pat.endswith("/")
    pat = pat.rstrip("/")
    anchored = "/" in pat
    pat = pat.lstrip("/")
    out, i = "", 0
    while i < len(pat):
        if pat.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pat.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pat[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pat[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pat[i]), i + 1
    return re.compile(("" if anchored else "(?:.*/)?") + out + r"\Z"), negated, dir_only


def ignored(rel, pats):
    """True if git would ignore the file at `rel` (a path relative to the repository, with '/')."""
    rules = [_rule(p) for p in pats]
    parts = rel.split("/")
    for depth in range(1, len(parts) + 1):
        sub, is_dir = "/".join(parts[:depth]), depth < len(parts)
        state = None
        for rx, negated, dir_only in rules:
            if dir_only and not is_dir:
                continue
            if rx.match(sub):
                state = not negated
        if is_dir and state:
            return True
        if not is_dir:
            return bool(state)
    return False


def published_files(repo=REPO):
    pats = ignore_patterns(repo)
    out = []
    for path in sorted(Path(repo).rglob("*")):
        if path.is_dir() or ".git" in path.relative_to(repo).parts:
            continue
        rel = path.relative_to(repo).as_posix()
        if not ignored(rel, pats):
            out.append((rel, path))
    return out


DATED_ROW = re.compile(r"^\s*\|?\s*(19|20)\d\d-\d\d-\d\d\s*[|,;\t]")
DECIMAL = re.compile(r"-?\d+\.\d+")
MAX_DATED_ROWS = 4


def daily_series_rows(text):
    """Number of lines that look like rows of a dated numeric series: a date, then at least one decimal number
    (v0.1.0 asked for two and let a one-column series through; audit 2026-10-22, U04)."""
    return sum(1 for line in text.splitlines() if DATED_ROW.match(line) and len(DECIMAL.findall(line)) >= 1)


def clock_times(line):
    return [m.group(0) for m in CLOCK_TIME.finditer(line) if not CLOCK_ALLOWED.search(m.group(0))]


def personal_terms(repo=REPO):
    local = Path(repo) / "identifiers_local.txt"
    if not local.exists():
        return None
    out = []
    for line in local.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(re.compile(line, re.IGNORECASE))
    return out


def scan(files=None, personal=(), handle=None, url=None):
    """Problems (list of strings) in the files git would publish."""
    files = published_files() if files is None else files
    if handle is None and url is None:
        handle, url = attribution()
    problems = []
    for rel, path in files:
        for rx in personal:
            if rx.search(rel):
                problems.append(f"{rel}: personal term /{rx.pattern}/ in the file name")
        suffix = path.suffix.lower()
        allowed_file = allowed_data(rel)
        if suffix in DATA_SUFFIXES and not rel.startswith(ALLOWED_DATA_DIRS) and not allowed_file:
            problems.append(f"{rel}: data file; git would publish it")
            continue
        if suffix in IMAGE_SUFFIXES and not rel.startswith(ALLOWED_IMAGE_DIRS):
            problems.append(f"{rel}: image file; publish only images this code generates, under docs/img/")
            continue
        if suffix not in TEXT_SUFFIXES and not allowed_file:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if allowed_file:
            problems += shape_problems(rel, text)
        else:
            rows = daily_series_rows(text)
            if rows > MAX_DATED_ROWS:
                problems.append(f"{rel}: {rows} dated numeric rows; looks like a daily series")
        for n, line in enumerate(text.splitlines(), 1):
            checked = without_attribution(rel, line, handle, url)
            for rx in personal:
                if rx.search(checked):
                    problems.append(f"{rel}:{n}: personal term /{rx.pattern}/")
            for name, rx in GENERIC.items():
                if name == "British spelling" and rel in ("scripts/scan_identifiers.py", "scripts/ste_check.py", "tests/test_ste_check.py"):
                    continue                                   # these files list the spellings they look for
                if name == "named AI model or vendor" and rel == "scripts/scan_identifiers.py":
                    continue                                   # this file lists the names it looks for
                for m in rx.finditer(line):
                    if name == "email address" and m.group(0).lower() in ALLOWED_EMAILS:
                        continue
                    problems.append(f"{rel}:{n}: {name}: {m.group(0)[:40]}")
            if suffix in CLOCK_SUFFIXES or rel == "LICENSE":
                for t in clock_times(line):
                    problems.append(f"{rel}:{n}: clock time in a public file: {t}")
    return problems


def main():
    personal = personal_terms()
    if personal is None:
        print("WARNING: identifiers_local.txt not found; only generic checks run")
        personal = []
    files = published_files()
    problems = scan(files, personal)
    for p in problems:
        print(p)
    print(f"\nscanned {len(files)} publishable files; {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
