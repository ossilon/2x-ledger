#!/usr/bin/env python3
"""Extract every PDF in data/papers/ to a text file and record what was extracted from what.

    py -I scripts\\extract_papers.py            extract new or changed PDFs, verify, update the manifest
    py -I scripts\\extract_papers.py --check    re-extract everything in memory and compare with the stored text

For each PDF the script writes <name>.txt next to it and one line in data/papers/manifest.jsonl:
pdf sha256, txt sha256, pages, characters, pages without text, pypdf version, extraction date. A text file is
trusted only while its hash matches the manifest and the manifest's pdf hash matches the PDF on disk.

Checks: the page count of the text equals the PDF's; every page yielded text (a page with none is an image or
a scan and is listed, because the knowledge on it is missing from the text); extracting twice gives identical
bytes (deterministic), so a later --check can prove the stored text is the one this PDF produces.

Known limits of text extraction, stated here so nobody mistakes the text for the page: pypdf keeps the words in
reading order for prose but often breaks equations into fragments, repeats glyphs in some fonts, and keeps
ligatures (fi, fl) as single characters. For a formula, read the PDF page itself. The text files are derived
copies for private use in data/ (git-ignored) and never leave it.
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import pypdf
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    sys.exit("pypdf is not installed; install it (verify the genuine package first) and rerun")

ROOT = Path(__file__).resolve().parents[1]
PAPERS = ROOT / "data" / "papers"
MANIFEST = PAPERS / "manifest.jsonl"
PAGE_MARK = "<<PAGE {n}>>"


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def extract(pdf_path):
    """Return (text, pages, empty_pages) for one PDF; the text carries a <<PAGE n>> line before every page."""
    reader = PdfReader(str(pdf_path))
    pages, empty = [], []
    for i, page in enumerate(reader.pages, start=1):
        t = page.extract_text() or ""
        if not t.strip():
            empty.append(i)
        pages.append(f"{PAGE_MARK.format(n=i)}\n{t}")
    return "\n\n".join(pages), len(reader.pages), empty


def read_manifest():
    if not MANIFEST.exists():
        return {}
    recs = [json.loads(l) for l in MANIFEST.read_text(encoding="utf-8").splitlines() if l.strip()]
    return {r["pdf"]: r for r in recs}


def write_manifest(recs):
    lines = [json.dumps(recs[k], sort_keys=True) for k in sorted(recs)]
    MANIFEST.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def run(check_only=False):
    recs = read_manifest()
    problems = []
    for pdf in sorted(PAPERS.glob("*.pdf")):
        pdf_hash = sha256_bytes(pdf.read_bytes())
        txt_path = pdf.with_suffix(".txt")
        old = recs.get(pdf.name)
        text, pages, empty = extract(pdf)
        text2, _, _ = extract(pdf)
        if text2 != text:
            problems.append(f"{pdf.name}: extraction is not deterministic; do not trust the text")
            continue
        txt_hash = sha256_bytes(text.encode("utf-8"))
        if check_only:
            if old is None:
                problems.append(f"{pdf.name}: not in the manifest")
            elif old["pdf_sha256"] != pdf_hash:
                problems.append(f"{pdf.name}: the PDF changed since extraction")
            elif not txt_path.exists() or sha256_bytes(txt_path.read_bytes()) != old["txt_sha256"]:
                problems.append(f"{pdf.name}: the stored text differs from the manifest")
            elif txt_hash != old["txt_sha256"]:
                problems.append(f"{pdf.name}: re-extraction differs from the stored text (pypdf {pypdf.__version__} vs {old['pypdf']})")
            else:
                print(f"ok   {pdf.name}: {pages} pages, text matches the manifest")
            continue
        if old and old["pdf_sha256"] == pdf_hash and txt_path.exists() and sha256_bytes(txt_path.read_bytes()) == old["txt_sha256"]:
            print(f"kept {pdf.name}: unchanged")
            continue
        txt_path.write_text(text, encoding="utf-8", newline="\n")
        recs[pdf.name] = {"pdf": pdf.name, "txt": txt_path.name, "pdf_sha256": pdf_hash, "txt_sha256": txt_hash,
                          "pages": pages, "chars": len(text), "pages_without_text": empty, "pypdf": pypdf.__version__,
                          "extracted_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        flag = f"  WARNING {len(empty)} page(s) without text: {empty[:10]}" if empty else ""
        print(f"saved {pdf.name}: {pages} pages, {len(text)} chars -> {txt_path.name}{flag}")
    if not check_only:
        write_manifest(recs)
    for p in problems:
        print("PROBLEM " + p)
    print(f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    sys.exit(run(check_only=ap.parse_args().check))
