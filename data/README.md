# data/ (private; git-ignored except this file)

This folder holds the inputs. The repository does not contain them.

| Folder | Content | Source | License |
|---|---|---|---|
| `raw/tradingview/<UTC date>/` | Daily bars, one JSON file per fund or stock, as the TradingView MCP returned them. `manifest.jsonl` lists each file with its SHA-256 hash and fetch time. | TradingView (`mcp-tv-get-ohlcv`, interval 1D, split-adjusted only) | Display only. Not for redistribution. |
| `raw/yahoo/<UTC date>/` | Dividend, distribution and split events, and adjusted closes, one JSON file per symbol. | Yahoo Finance chart endpoint | Personal use. |
| `raw/quotes/<UTC date>/` | Monthly quote snapshot: expense ratio, AUM, NAV, premium, flows. | TradingView (`mcp-tv-get-symbol-data-batch`) | Display only. |
| `register/` | Fund facts with sources: funds, leverage timeline, expense timeline, events, stocks. | Issuer pages, SEC EDGAR, press | Facts. The run publishes them as `register.csv` after review. |
| `series/` | Daily series that the run rebuilds from `raw/`, one CSV per symbol. | Derived from raw | Not published. |
| `pins/` | Real-data test pins (input hashes and metric values). | Derived | Not published. |
| `reference/` | The daily close of the S&P 500 (`SP_SPX_close.csv`: date, close) for the column `beta_spx_under`. `manifest.jsonl` records the SHA-256, the fetch time of the bars, the copy time and the source. | A copy of the author's price library (a TradingView CSV export with MCP top-ups). `py -I code\domain\benchmark.py import` loads any daily close file with the same two columns. | Display only. Not for redistribution. |
| `papers/` | Papers and books for `docs/CANON.md`. Each PDF has a `.txt` from `scripts/extract_papers.py` and a `manifest.jsonl` line (PDF hash, text hash, pages, pages without text, extractor version, date). The texts are private copies. They never leave `data/`. | SSRN, arXiv, publishers | Copyright of the authors. |

Rules:

- Nobody edits a raw file. A new fetch is a new file.
- The run rebuilds the series from raw files each time.
- A review as of a date sees only files fetched by that date (`captured_by`).
