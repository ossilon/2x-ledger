"""Put this project's flat code folders on sys.path. Import this module first in every file under code/.

The project's own code lives in flat folders under code/ (engine, domain, capture, forward, product) with no
package __init__; each folder goes on sys.path so modules import each other by bare name. The few helpers the
engine once imported from the author's sibling kits (the LETF kit and the price library) are ported into
code/port.py so a public clone runs on its own; tests/port_local.py (git-ignored) keeps the copies in step.
"""
import sys
from pathlib import Path

CODE = Path(__file__).resolve().parent          # twox_ledger/code
ROOT = CODE.parent                              # twox_ledger
MODELS = ROOT.parent                            # the folder that holds this project (sibling kits, when present)

for p in (CODE, CODE / "engine", CODE / "domain", CODE / "capture", CODE / "forward", CODE / "product"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
