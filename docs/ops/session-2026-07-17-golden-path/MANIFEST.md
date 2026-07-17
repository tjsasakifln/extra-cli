# Golden path PNCP health — honest degraded capture

**Story:** `ROI-cand-golden-path-pncp-health`  
**Date:** 2026-07-17  
**Branch:** `extra-roi/cand-golden-path-pncp-health`

## AC

| AC | Result |
|----|--------|
| Reproducible golden path result (pass or honest degraded) | **MET** — exit **1** when PostgreSQL unavailable; ledger `status=failed` |
| No success claim on timeout/DB fail | **MET** — `GOLDEN_EXIT=1`; process does not return 0 |

## Run evidence

```text
Command: python3 scripts/golden_path.py --skip-freshness --skip-reports
Exit: 1
Log: PostgreSQL NAO respondeu / fe_sendauth: no password supplied (port 54399)
Ledger: output/golden-path/ledger-slice2.json
```

## Notes

- Live crawl path blocked without local PG (`make db-up`) and network sources.
- This slice records **fail-closed** behavior as source health signal, not operational green.
- 14 golden_path unit tests pass (`pytest -k golden_path`).

## Non-claims

- NOT full golden path green
- NOT PNCP live health OK
- NOT PRE_VPS_FINAL_READY
