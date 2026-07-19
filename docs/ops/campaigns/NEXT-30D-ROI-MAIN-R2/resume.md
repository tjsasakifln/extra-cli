# Resume protocol — NEXT-30D-ROI-MAIN-R2

**UTC:** 2026-07-19 wave2 final

## Policy: SmartLic DEFERRED_STALE_SOURCE

No SmartLic data on critical path / Extra-ROI / gates.

## Quick start

```bash
cd "$(git rev-parse --show-toplevel)"
export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}"
cat docs/ops/campaigns/NEXT-30D-ROI-MAIN-R2/PLAN-30D.md
cat docs/ops/campaigns/NEXT-30D-ROI-MAIN-R2/evidence/N06c-wave/entity-coverage-delta-wave2.json
# Next Extra-ROI: N01 golden path live
python3 -m scripts.golden_path --dsn "$LOCAL_DATALAKE_DSN"
```

## Status

| ID | Status |
|----|--------|
| N06c | **DONE** — either 406/1093 (37,2%) Extra-only |
| SmartLic | DEFERRED_STALE_SOURCE |
| Next ROI | **N01** |

## Evidence

- `evidence/N06c-wave/entity-coverage-delta-wave2.json`
- `evidence/N06c-wave/contracts-180d.json` (success, 6 windows, GO 3y criteria)
- `extra-consultoria-plano-executivo.html` (painel R2)
