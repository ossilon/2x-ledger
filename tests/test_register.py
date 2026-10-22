"""Register tables: synthetic register in a temp folder (gaps, inception mismatches, leverage by date, events)."""
import shutil
import tempfile
from pathlib import Path

import pandas as pd

from _harness import check, raises
import register as rg

root = Path(tempfile.mkdtemp(prefix="ledger_register_"))
reg = root / "data" / "register"
reg.mkdir(parents=True)


def write(name, text):
    (reg / name).write_text(text, encoding="utf-8")


write("funds.csv", "symbol,ticker,exchange,issuer,fund_name,underlying,inception_date,inception_source,status,close_date,"
      "close_reason,close_source,expense_ratio_pct,expense_asof,expense_source,distributions_url,swap_counterparties,"
      "swap_terms,swap_source,options_note,notes,captured_date\n"
      "NASDAQ:AAA,AAA,NASDAQ,Issuer,Fund A,NASDAQ:A,2022-08-09,src,live,,,,0.95,2026-01-01,src,,,,,,,2026-10-22\n"
      "NASDAQ:BBB,BBB,NASDAQ,Issuer,Fund B,NASDAQ:B,2024-03-04,src,closed,2026-07-14,negative NAV,src,1.15,2026-01-01,src,,,,,,,2026-10-22\n")
write("stocks.csv", "symbol,ticker,exchange,name,yahoo,tv_first_bar,complete_history,pays_dividends,notes,captured_date\n"
      "NASDAQ:A,A,NASDAQ,A Inc,A,2006-12-05,no,yes,,2026-10-22\nNASDAQ:B,B,NASDAQ,B Inc,B,2020-01-02,yes,no,,2026-10-22\n")
write("leverage_timeline.csv", "symbol,effective_from,effective_to,target_leverage,source,note\n"
      "NASDAQ:AAA,2022-08-09,2024-04-02,1.5,src,\nNASDAQ:AAA,2024-04-02,,2.0,src,\n"
      "NASDAQ:BBB,2024-03-04,2026-07-14,2.0,src,\n")
write("expense_timeline.csv", "symbol,effective_from,effective_to,expense_total_pct,basis,source,note\n"
      "NASDAQ:AAA,2022-08-09,,0.95,total,src,\nNASDAQ:BBB,2024-03-04,2026-07-14,1.15,total,src,\n")
write("events.csv", "symbol,date,type,value,status,source,note,captured_date\n"
      "NASDAQ:AAA,2022-08-09,inception,,VERIFIED,src,,2026-10-22\n"
      "NASDAQ:AAA,2024-04-02,leverage_change,1.5->2.0,VERIFIED,src,,2026-10-22\n"
      "NASDAQ:BBB,2024-03-04,inception,,VERIFIED,src,,2026-10-22\n"
      "NASDAQ:BBB,2026-07-14,closure,negative NAV,VERIFIED,src,,2026-10-22\n")

check("a consistent register validates with no problems", rg.validate(root) == [], rg.validate(root))
funds = rg.load_funds(root)
check("funds are indexed by symbol with parsed dates", funds.at["NASDAQ:BBB", "close_date"] == pd.Timestamp("2026-07-14"))

idx = pd.bdate_range("2024-03-28", "2024-04-05")
L = rg.target_leverage_series("NASDAQ:AAA", idx, root)
check("target leverage is 1.5 before the change date", float(L[pd.Timestamp("2024-04-01")]) == 1.5)
check("target leverage is 2.0 from the change date on", float(L[pd.Timestamp("2024-04-02")]) == 2.0 and float(L[pd.Timestamp("2024-04-05")]) == 2.0)
raises("a date before inception has no target leverage", lambda: rg.target_leverage_series("NASDAQ:AAA", pd.bdate_range("2022-08-01", "2022-08-05"), root), "no target leverage")
raises("an unknown symbol has no timeline", lambda: rg.target_leverage_series("NASDAQ:ZZZ", idx, root), "no leverage timeline")

pub = rg.public_register(root)
check("public register has one row per fund and only public columns", len(pub) == 2 and list(pub.columns) == rg.PUBLIC_FUND_COLS)
check("public register carries the current target leverage", float(pub.set_index("symbol").at["NASDAQ:AAA", "target_leverage_now"]) == 2.0)
check("public register shows the close date of a closed fund", pub.set_index("symbol").at["NASDAQ:BBB", "close_date"] == "2026-07-14")
check("public register has no swap or note columns", not any(c in pub.columns for c in ("swap_counterparties", "notes", "options_note")))

# gaps, overlaps and mismatches are reported
write("leverage_timeline.csv", "symbol,effective_from,effective_to,target_leverage,source,note\n"
      "NASDAQ:AAA,2022-08-09,2024-04-02,1.5,src,\nNASDAQ:AAA,2024-04-03,,2.0,src,\n"
      "NASDAQ:BBB,2024-03-05,2026-07-14,2.0,src,\n")
probs = rg.validate(root)
check("a one-day gap in a leverage timeline is reported", any("ends 2024-04-02" in p for p in probs), probs)
check("a timeline that starts after inception is reported", any("BBB" in p and "inception" in p for p in probs), probs)
write("leverage_timeline.csv", "symbol,effective_from,effective_to,target_leverage,source,note\n"
      "NASDAQ:AAA,2022-08-09,2024-04-02,1.5,src,\nNASDAQ:AAA,2024-04-02,,2.0,src,\n"
      "NASDAQ:BBB,2024-03-04,2026-07-14,2.0,src,\n")
write("events.csv", "symbol,date,type,value,status,source,note,captured_date\n"
      "NASDAQ:AAA,2022-08-10,inception,,VERIFIED,src,,2026-10-22\nNASDAQ:BBB,2024-03-04,inception,,VERIFIED,src,,2026-10-22\n")
probs = rg.validate(root)
check("an inception event that differs from funds.csv is reported", any("AAA" in p and "inception event" in p for p in probs), probs)
check("a closed fund without a closure event is reported", any("BBB" in p and "closure event" in p for p in probs), probs)
write("events.csv", "symbol,date,type,value,status,source,note,captured_date\nNASDAQ:AAA,2022-08-09,wizardry,,VERIFIED,src,,2026-10-22\n")
raises("an unknown event type is refused", lambda: rg.events(root), "unknown event types")

shutil.rmtree(root, ignore_errors=True)
