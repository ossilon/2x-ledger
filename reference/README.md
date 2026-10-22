# reference/

Public reference data that the engine reads. Each file names its source and its last date.

| File | Content | Source | Last date | Notes |
|---|---|---|---|---|
| `DFF.csv` | Effective federal funds rate, daily, percent. Columns `observation_date,DFF`. | FRED series DFF, Federal Reserve Bank of St. Louis. Public domain. | 2026-10-08 | The engine charges this rate, known before each day, on the fund's borrowed turns. Days after the last date carry the last value forward. |

The S&P 500 close used for one column (`beta_spx_under`) is not public. It sits in the private folder
`data/reference/`; see `data/README.md`.
