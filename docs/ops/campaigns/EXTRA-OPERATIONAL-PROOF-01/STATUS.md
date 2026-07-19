# STATUS — EXTRA-OPERATIONAL-PROOF-01

**Atualizado:** 2026-07-19  
**Commit campanha:** `54f6fe1`  
**Veredito de campanha:** `PARTIAL` (bloqueado por aceite humano AC10 + full suite residual)

## Checklist de fases

| Fase | Status | Notas |
|------|--------|-------|
| A — Higiene | DONE | Baseline medida; PR#28 CLOSED; branch limpa de main |
| B — Contrato execução | DONE | `scripts/collect/run_contract.py` + persist `pipeline_runs` |
| C — Ciclo semanal E2E | DONE | `make extra-weekly` / `scripts.ops.weekly_cycle` |
| D — CI | PARTIAL | Critical+expanded no PR; full suite ainda dispatch |
| E — Execução real + humano | PARTIAL | Ciclo real exit 0; **PENDING_HUMAN** |

## Acceptance criteria

| AC | Status |
|----|--------|
| AC1 Entry point único | **PASS** — `make extra-weekly` |
| AC2 E2E real | **PASS** — collect/reuse + process + quality + intel + delivery |
| AC3 Rastreabilidade | **PASS** — claims_provenance + run/collection ids |
| AC4 Separação métricas | **PASS** — indicator catalog fail-closed |
| AC5 Produto utilizável | **PASS** — MD+Excel+CSV reais (não fixture) |
| AC6 Fonte e freshness | **PASS** — source_health no pacote |
| AC7 Identidade CNPJ | **PASS** — pick_match rejeita cross-root (teste) |
| AC8 CI | **PARTIAL** — checks novos verdes localmente; full suite não gate PR |
| AC9 PR controlável | **PASS esperado** — diff pequeno focado |
| AC10 Aceite humano | **PENDING_HUMAN** |

## Execução canônica (evidência)

```text
comando: make extra-weekly
         WEEKLY_FLAGS="--skip-collect --limit 50 --output-dir output/weekly/PROOF-01-canonical"
exit_code: 0
duration_seconds: ~2.0
collection_id: col-extra-weekly-20260719T192008Z-0142869a
cycle_id: weekly-20260719T192008Z-853988a39f
runs:
  pncp_opportunities → reused_fresh (SLA 48h)
  pncp_contracts → reused_fresh (SLA 168h)
counts: opportunities=50, contracts=50, competitors=50, orgaos=50
produtos: output/weekly/PROOF-01-canonical/
evidência copiada: docs/ops/campaigns/EXTRA-OPERATIONAL-PROOF-01/evidence/
```

### Live force-collect (adicional)

```text
comando: python -m scripts.ops.weekly_cycle --strict --force-collect --lookback-days 3
exit_code: 0
pncp_opportunities → success_zero (HTTP 204 por modalidade no recorte; opportunity_runs.completion_reason=http_204_complete)
pncp_contracts → reused_fresh
nota: inventário de oportunidades abertas no lake permanece disponível no produto
```

## Dívida residual CI (explícita)

| Item | Causa | Owner | Condição de remoção |
|------|-------|-------|---------------------|
| `Test All (full suite)` só `workflow_dispatch` | testes legados dependem de schema/serviços não provisionados em todo PR | @devops | full suite verde em CI com serviços + lista de skips=0 injustificados |
| cov global 10% no critical | histórico; não vendido como qualidade | @dev | thresholds por módulo crítico (weekly já 35% no expanded job) |
| Integration weekly offline | requer Postgres no job critical | @dev | service container no job critical ou manter expanded |

## Human accept

```text
status: PENDING_HUMAN
owner: Tiago
required: executive_summary, opportunities, contracts sample, competitors, values, limitations
```
