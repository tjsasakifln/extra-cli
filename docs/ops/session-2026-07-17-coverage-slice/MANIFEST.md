# Coverage slice — pending_collection → strict operational (N>0)

**Story:** `ROI-cand-coverage-slice-pending-collection`  
**Cycle:** `cyc-2026-07-17T230924Z`  
**Date:** 2026-07-17  
**Branch:** `extra-roi/cand-coverage-slice-pending-collection`

## Result

| Metric | Value | Kind |
|--------|------:|------|
| **operational_source_coverage (M2)** | **5 / 1093 (0.46%)** | coverage |
| entities_with_recent_commercial_signal (M1) | 116 / 1093 (10.61%) | commercial_signal (NOT coverage) |
| source_mapping_coverage | 1093 / 1093 (100%) | coverage |
| Claims 95% operational? | **NO** | forbidden |

## AC mapping

| AC | Result |
|----|--------|
| N>0 entities advanced with run_id/raw/sha | **MET** — 5 entities `verified` + `is_strict_operational=True` |
| Report does not claim 95% | **MET** — M2=0.46%; `claims_95_reached=false` |
| commercial_signal separate | **MET** — headline remains commercial; kind≠coverage |

## Provenance (each of 5)

- `run_id` / `pipeline_run_id`: `pncp-sc-20260717T110800Z-9d6dd91153`
- `raw_uri`: `output/pncp_sc/pncp-sc-20260717T110800Z-9d6dd91153/contratacoes.jsonl`
- `raw_sha256`: `2b737ff8d5a9b166be2fbe40f81c67cfcb17e67a70b94ef9d111040dfc9f46af`
- `normalized_record_ids`: PNCP control numbers from jsonl
- `reconciliation_id`: stable `recon-*` from canonical_id|source|last_seen
- `dry_run`: false
- stages: mapped/accessible/collected/normalized/reconciled/verified_within_sla = true

## Sample entities

1. `82562893:MUNICIPIO_DE_CANELINHA`
2. `83102798:MUNICIPIO_DE_INDAIAL`
3. `00394452:COMANDO_DO_EXERCITO`
4. `10635424:INSTITUTO_FEDERAL_DE_EDUCACAO_CIENCIA_E_TECNOLOGIA_CATARINENSE`
5. `15126437:EMPRESA_BRASILEIRA_DE_SERVICOS_HOSPITALARES_EBSERH`

## Code change

- `scripts/source_registry/acquisition/promote_from_evidence.py`
  - Fail-closed without provenance
  - Attach run/raw/sha from crawl `evidence.json`
  - Align `sla_hours` with promote window
  - Offline path: `promote_from_crawl_artifacts`

## Commands

```bash
pytest -o addopts='' -q tests/unit/source_registry/test_promote_from_evidence.py
python3 -c "from scripts.source_registry... promote_from_crawl_artifacts ..."
python -m scripts.coverage.coverage_contract_cli report --offline --format json \
  --output output/coverage/contract-report-slice.json
```

## Non-claims

- NOT 95% operational coverage
- NOT PRE_VPS_FINAL_READY / LOCAL_RESILIENCE_READY
- NOT commercial signal as coverage
- NOT full universe promote (only N=5 slice)

## Artifacts

- `slice-result.json`
- `output/coverage/contract-report-slice.json`
- `data/entity_source_registry.jsonl` (updated)
