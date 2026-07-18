# Evidence — DoD §12.2 analytical reports (8)

**Story:** `ROI-cand-dyn-slice-19ce6ecf8869`  
**Module:** `scripts/reports/operational_reports.py`

| Item | Artifact | Notes |
|------|----------|-------|
| contratos por ente | relatorio_contratos_por_ente.csv | empty/schema-limited if no contracts |
| contratos por fornecedor | relatorio_contratos_por_fornecedor.csv | honest empty |
| concorrentes | relatorio_concorrentes.csv | may be orgao fallback (limitation) |
| concentração | relatorio_concentracao.csv | HHI only with caveats |
| referências de valores | relatorio_referencias_valores.csv | valor_total_estimado semantics labeled |
| completude | relatorio_completude.csv | per-field % |
| coverage | relatorio_coverage.csv | presence/signal; operational explicit 0% |
| recall | relatorio_recall.csv | status=NOT_READY without gold sample |

## Commands
```bash
export LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/extra_test
python3 -m pytest tests/test_operational_reports.py -q --no-cov -o addopts=
python3 -m scripts.reports.operational_reports --dsn "$LOCAL_DATALAKE_DSN" --out docs/ops/session-2026-07-18-operational-reports/reports --json
```

## Non-claims
LOCAL_READY, 95% operational, 95% recall, PRE_VPS, PROJECT_DONE
