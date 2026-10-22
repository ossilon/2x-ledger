"""Real-data pins: recompute three funds for each pinned as-of date and compare with data/pins/<asof>.json.

Skips (with a note) when the private data or the pin files are absent, as in a public clone. Repinning is a
deliberate act (scripts/make_pins.py --repin), never a tolerance change.
"""
import json
import math
from pathlib import Path

from _harness import check, ROOT

pins = sorted((ROOT / "data" / "pins").glob("*.json")) if (ROOT / "data" / "pins").exists() else []
have_data = (ROOT / "data" / "raw" / "tradingview" / "manifest.jsonl").exists()

if not pins or not have_data:
    print("pins: skipped (no private pins or raw data on this machine)")
else:
    import run_monthly as rm
    import register as rg
    funds = rg.load_funds()
    sym_of = {r["ticker"]: s for s, r in funds.iterrows()}
    for p in pins:
        pin = json.loads(p.read_text(encoding="utf-8"))
        asof = pin["asof"]
        for ticker in pin["pin_funds"]:
            row, _ = rm.fund_row(sym_of[ticker], asof, funds, "test", reps=1000)
            pinned = pin["rows"][ticker]
            worst, worst_col = 0.0, None
            for col, want in pinned.items():
                got = row.get(col)
                if col in ("schema_version",) or got is None:
                    continue
                try:
                    got = float(got)
                except (TypeError, ValueError):
                    continue
                if math.isnan(want) and math.isnan(got):
                    continue
                # the pin is rounded to 6 decimals, so allow that rounding plus 1e-6 relative
                diff = abs(got - want) - 5e-7
                rel = max(diff, 0.0) / max(abs(want), 1e-9)
                if rel > worst:
                    worst, worst_col = rel, col
            check(f"pin {asof} {ticker}: every pinned column reproduces (1e-6 relative beyond the pin rounding)", worst <= 1e-6, f"{worst_col}: {worst:.2e}")
        check(f"pin {asof}: inputs hash recorded", len(pin["inputs_sha256"]) == 64)
