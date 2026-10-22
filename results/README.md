# results/

One folder per month, plus the manifests.

| Path | Content |
|---|---|
| `<YYYY-MM>/windows.csv` | Returns of each fund by calendar year and by trailing window (1, 3 and 12 months), with the layers and the effects in percentage points. `DATA_DICTIONARY.md` defines each column. |
| `manifests/<YYYY-MM>.json` | The run's input list: the kind, path and SHA-256 hash of every raw file the run read, and the cutoff. Also the hashes of the output files. Dates only, no clock times. |

The folder holds aggregates only. No price level, no daily return series and no issuer file appears here.
