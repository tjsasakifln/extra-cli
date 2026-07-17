# DoD unit-test evidence pack — §13.1 / §3

**Story:** `ROI-cand-dod-unit-test-evidence-pack`  
**Date:** 2026-07-17  
**Pytest:** `511 passed, 12 skipped, exit 0`  
**Log:** `pytest-pack.log` / `pytest-pack.exit`

## Rule

Only mark DoD `[x]` when (1) mapping below says HIGH confidence, (2) pack re-run exit 0, (3) independent QA PASS. No 95% ops claims.

## Mapping (checkbox → proof)

| DoD item | Proof (shipped code via pytest files in pack) |
|----------|-----------------------------------------------|
| Normalização de CNPJ | test_universe (normalize_cnpj8), test_common (digits/extract), test_entity_resolver |
| Normalização de coordenadas | test_geocode ValidateCoords + Haversine |
| Cálculo de identidade de ente | test_official_acts_reconcile deterministic_entity_hash; test_qw01 seed identity |
| Cálculo de cobertura | test_coverage_calculator, test_coverage_truth, test_coverage_contract |
| Regra de success_zero | test_coverage_states, test_contract_intel_crawl |
| Freshness | test_freshness_gate, test_coverage_states EvaluateFreshness, test_freshness |
| Paginação | test_qw01_radar pagination, test_local_resilience partial pagination |
| Retry | test_base_client RetryConfig, test_qw01 429, test_local_resilience HTTP policy |
| Backoff | test_base_client exponential delay, test_dlq Backoff, test_qw01 conservative backoff |
| Checkpoint | test_checkpoint, test_contract_intel_crawl Checkpoint |
| Resume | test_local_resilience checkpoint resume + 429 resume |
| Deduplicação | test_opportunity_dedup |
| Classificação de status | test_opportunity_status, test_commercial_status |
| Classificação AEC (parcial) | test_pncp_contract engineering class, test_commercial_status sector |
| Regras de score | test_opportunity_ranking, test_qw01 score dimensions |
| Encadeamento edital-contrato (parcial) | test_official_acts_reconcile match rules |
| Geração de manifest | test_coverage_manifest |
| Geração de relatórios | test_commercial_sample_sc build_report, test_coverage_calculator print |
| Baseline 1093 / CSV seed | test_universe constant, test_builder 1093 records, test_coverage_contract denominator |
| Dups CNPJ8 preservadas | test_contract_intel_target cnpj8 duplicates |
| Entes sem coords excluídos do raio | test_contract_intel_target without coordinates |

## Explicitly NOT marked this pack

- Normalização de IBGE (sem teste de pad/normalize)
- Importação idempotente planilha / 0 changes 2ª import
- Detecção novos/alterados/removidos
- Semântica de valores completa
- Hash planilha registrado (assert)
- Reconciliação snapshot (precisa PG)
- capability_monitoring_coverage >= 95%
- Qualquer item §8–12 operacional live

## Commands

```bash
pytest -o addopts='' -q \
  tests/test_universe.py tests/test_common.py tests/test_geocode.py \
  tests/test_coverage_calculator.py tests/test_coverage_states.py \
  tests/test_coverage_truth.py tests/test_freshness.py tests/test_freshness_gate.py \
  tests/test_qw01_radar.py tests/test_contract_intel_crawl.py \
  tests/test_base_client.py tests/test_dlq.py tests/test_local_resilience.py \
  tests/test_checkpoint.py tests/test_opportunity_dedup.py \
  tests/test_opportunity_status.py tests/test_opportunity_ranking.py \
  tests/test_commercial_status.py tests/test_pncp_contract.py \
  tests/test_official_acts_reconcile.py tests/test_coverage_manifest.py \
  tests/test_commercial_sample_sc.py tests/unit/coverage/test_coverage_contract.py \
  tests/unit/source_registry/test_builder.py tests/test_contract_intel_target.py \
  tests/test_entity_resolver.py
# → 511 passed, 12 skipped, exit 0
```
