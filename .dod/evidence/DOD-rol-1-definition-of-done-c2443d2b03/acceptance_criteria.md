# Acceptance criteria — O backfill cobre no mínimo os últimos três anos.

**Item:** `DOD-rol-1-definition-of-done-c2443d2b03`  
**DOD line:** 752  
**Campaign:** HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01

## Requirement

O backfill de contratos históricos PNCP cobre no mínimo os últimos três anos calendário (janela contínua auditável).

## Given / When / Then

1. **Given** checkpoint `data/contracts_checkpoints/hc_closure_3y/contracts_full.json`  
   **When** total_windows_completed e completed_windows são lidos  
   **Then** 37/37 planned windows estão completed e o span min(start)→max(end) ≥ 3.0 anos.

2. **Given** suite de janela de contratos  
   **When** `pytest tests/test_contracts_window_complete.py tests/test_contracts_per_window_persist.py`  
   **Then** todos os testes passam (sem skip de gate).

3. **Given** cutover VPS  
   **When** `pncp_supplier_contracts` é contado em produção  
   **Then** contagem operacional ~4.4M alinhada ao backfill (evidência cutover/soak).

## Non-claims

- Não afirma `LOCAL_READY`, `VPS_OPERATIONAL`, `PROJECT_DONE`.
- Não afirma off-site backup nem soak 7d.
- Não afirma open_tenders ≥ 95%.

## Evidence refs

- `data/contracts_checkpoints/hc_closure_3y/contracts_full.json`
- `artifacts/campaigns/HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/cutover.json`
- `artifacts/campaigns/HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/dual-coverage.json`
