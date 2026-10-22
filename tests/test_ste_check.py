"""The STE linter: each rule fires on a planted sentence and stays quiet on a correct one; the public files pass."""
import sys

from _harness import check, ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import ste_check as ste  # noqa: E402

ok = ste.check_sentence("The engine computes the cost of each fund from daily closes.")
check("a short active sentence has no problem", ok == [], ok)
check("a 30-word sentence is too long", any("words" in p for p in ste.check_sentence(" ".join(["word"] * 30) + ".")))
check("an instruction of 22 words is too long", any("limit 20" in p for p in ste.check_sentence("Run " + " ".join(["the"] * 21) + ".")))
check("a descriptive sentence of 22 words passes", ste.check_sentence("The " + " ".join(["fund"] * 21) + ".") == [])
check("passive voice is flagged", any("passive" in p for p in ste.check_sentence("The cost is computed by the engine.")))
check("an adjective participle is not passive", ste.check_sentence("The fund is based in Delaware.") == [])
check("a progressive tense is flagged", any("progressive" in p for p in ste.check_sentence("The fund is paying the rate.")))
check("a technical -ing name after 'by' passes", ste.check_sentence("The fund grows by borrowing one turn.") == [])
check("an unlisted gerund after 'by' is flagged", any("-ing" in p for p in ste.check_sentence("The fund grows by multiplying the stock.")))
check("a technical -ing name passes", ste.check_sentence("The rebalancing effect is small.") == [])
check("a banned Latin abbreviation is flagged", any("banned" in p for p in ste.check_sentence("Costs vary, e.g. by issuer.")))
check("a British spelling is flagged", any("British" in p for p in ste.check_sentence("The analyser models the behaviour.")))

md = ["# Title", "", "| A | B |", "|---|---|", "| The cost is computed. | Fine. |", "", "- Run it.", "- Read the file.", "",
      "```", "code with passive voice is skipped", "```", "", "One. Two. Three. Four. Five. Six. Seven."]
blocks = list(ste.blocks(md))
check("tables give one block per cell (header cells included) and lists one per item",
      sum(1 for b in blocks if b[1] == "cell") == 4 and sum(1 for b in blocks if b[1] == "para") == 3)
import tempfile
from pathlib import Path
with tempfile.TemporaryDirectory() as tmp:
    p = Path(tmp) / "t.md"
    p.write_text("\n".join(md) + "\n", encoding="utf-8")
    probs = ste.check_file(p)
    whys = [w for _, w, _ in probs]
    check("a file check finds the passive cell and the seven-sentence paragraph, and skips the code block",
          any("passive" in w for w in whys) and any("paragraph of 7" in w for w in whys) and len(probs) == 2, whys)

# the gate: every public Markdown file passes
total = 0
for f in ste.public_files():
    probs = ste.check_file(f)
    total += len(probs)
    if probs:
        print(f"   {f.relative_to(ROOT).as_posix()}: {len(probs)} problem(s), first: line {probs[0][0]} {probs[0][1]}")
check("the public Markdown files pass the STE lint", total == 0, f"{total} problem(s)")
