"""Register timelines: the expense ratio by date and the public leverage table (synthetic tables in a temp root)."""
import shutil
import tempfile
from pathlib import Path

import pandas as pd

from _harness import check, raises
import register as rg

root = Path(tempfile.mkdtemp(prefix="ledger_register_"))
reg = root / "data" / "register"
reg.mkdir(parents=True)
(reg / "funds.csv").write_text(
    "symbol,ticker,exchange,issuer,fund_name,underlying,inception_date,inception_source,status,close_date,close_reason,close_source,"
    "expense_ratio_pct,expense_asof,expense_source,distributions_url,swap_counterparties,swap_terms,swap_source,options_note,notes,captured_date\n"
    "NASDAQ:TST,TST,NASDAQ,Issuer,Test 2X,NASDAQ:T,2024-01-02,src,live,,,,1.00,2026-01-01,src,url,,,,,,2026-10-22\n", encoding="utf-8")
(reg / "leverage_timeline.csv").write_text(
    "symbol,effective_from,effective_to,target_leverage,source,note\n"
    "NASDAQ:TST,2024-01-02,2024-06-03,1.5,src1,\nNASDAQ:TST,2024-06-03,,2.0,src2,\n", encoding="utf-8")
(reg / "expense_timeline.csv").write_text(
    "symbol,effective_from,effective_to,expense_total_pct,basis,source,note\n"
    "NASDAQ:TST,2024-01-02,2025-03-01,0.95,total,src,\nNASDAQ:TST,2025-03-01,,1.00,total,src,\n", encoding="utf-8")

idx = pd.bdate_range("2024-01-02", "2025-06-30")
e = rg.expense_ratio_series("NASDAQ:TST", idx, root)
check("expense ratio follows the timeline: 0.95 before the change, 1.00 from the effective date", e["2025-02-28"] == 0.95 and e["2025-03-03"] == 1.00 and e.iloc[0] == 0.95)
raises("a date before the timeline is refused", lambda: rg.expense_ratio_series("NASDAQ:TST", pd.bdate_range("2023-12-01", periods=5), root), "no expense ratio")
raises("an unknown fund is refused", lambda: rg.expense_ratio_series("NASDAQ:NOPE", idx, root), "no expense timeline")

pl = rg.public_leverage(root)
check("public leverage table: one row per period with ticker, target and dates", list(pl["ticker"]) == ["TST", "TST"] and list(pl["target_leverage"]) == [1.5, 2.0]
      and list(pl["effective_from"]) == ["2024-01-02", "2024-06-03"] and pl["effective_to"].iloc[1] == "")
check("public leverage table carries the source and not the private note", "source" in pl.columns and "note" not in pl.columns)

shutil.rmtree(root, ignore_errors=True)
