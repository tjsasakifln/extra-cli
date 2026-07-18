# Evidence — DoD §25 indicator catalog fields

**Story:** `ROI-cand-dyn-slice-cad02f320cc4`  
**Cycle:** `cyc-2026-07-18T125038Z`  
**Branch:** `extra-roi/cand-indicator-catalog`  
**Date:** 2026-07-18  

## DoD items covered

| Item | Proof |
|------|-------|
| Todo indicador possui definição | `MetricDefinition.definition` + catalog export |
| Todo indicador possui fórmula | `MetricDefinition.formula` |
| Todo indicador possui denominador | `MetricDefinition.denominator_policy` + `MetricResult.denominator` |
| Todo indicador possui data de corte | `as_of_policy` + report `as_of` |
| Todo indicador possui fonte | `source_policy` |
| Todo indicador possui status de prontidão | `MetricResult.status` / `MetricStatus` |
| `READY` significa executado e validado | `READY_SEMANTICS` constant + tests |

## Artifacts

- `scripts/coverage/coverage_contract.py` — catalog schema + `validate_indicator_catalog` / `export_indicator_catalog`
- `tests/test_indicator_catalog.py` — 6 passed
- `indicator-catalog.json`, `catalog-validation.json`

## Commands

```bash
python3 -c "from scripts.coverage.coverage_contract import export_indicator_catalog; import json; print(json.dumps(export_indicator_catalog(), indent=2))"
python3 -m pytest tests/test_indicator_catalog.py -q -o addopts=
```

## Non-claims

- Not claiming operational coverage ≥95%
- Not claiming freshness/recall READY for all entities
- Empty DoD bullet under §25 (orphan line) not flipped
