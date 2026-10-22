"""README.md's data blocks are the current rendering of ledger.csv (the gate: run render.py after each monthly run)."""
from _harness import check, ROOT
import render

readme = ROOT / "README.md"
if (ROOT / "ledger.csv").exists():
    fresh = render.render(readme)
    check("README.md holds the current rendering of ledger.csv", fresh == readme.read_text(encoding="utf-8"),
          "run  py -I code\\product\\render.py")
    asof, R = render.latest()
    check("the rendering covers every ranked fund of the latest as-of date", len(R) >= 1 and all(t in fresh for t in R["ticker"]))
    check("the ten questions table has ten rows", fresh.count("\n| 1 |") == 1 and fresh.count("\n| 10 |") == 1)
