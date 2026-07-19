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
| AC3 Rastreabilidade | **PASS** — claims: opp+contract+competitor com `collection_id` + `cycle_run_id` do ciclo (source_record_run_id separado) |
| AC4 Separação métricas | **PASS** — indicator catalog fail-closed |
| AC5 Produto utilizável | **PASS** — MD+Excel+CSV reais (não fixture) |
| AC6 Fonte e freshness | **PASS** — source_health no pacote |
| AC7 Identidade CNPJ | **PASS** — pick_match rejeita cross-root (teste) |
| AC8 CI | **PASS local** — critical path `-m not integration` + skip REQUIRE_REAL_DB; full suite ainda dispatch |
| AC9 PR controlável | **PASS esperado** — diff pequeno focado |
| AC10 Aceite humano | **PENDING_HUMAN** |

## Skeptic fixes (2026-07-19)

1. **CI mock:** integration test skips unless `REQUIRE_REAL_DB=1`; critical job uses `-m "not integration..."`.
2. **AC3 claims:** opportunity + contract + competitor rows carry this cycle `collection_id` + `cycle_run_id`.
3. **Extra scope:** contracts/competitors require `uf='SC' AND orgao_cnpj_8 ∈ universe raio_200km`.

## PR review reliability fixes (REQUEST CHANGES)

1. **`partial` never fresh / never reused_fresh** — `classify_opportunity_freshness`; only complete success-class statuses within SLA.
2. **`--strict` real** — partial critical → exit 2; Excel missing → exit 1 (strict) / 2; delivery must be `ok` with `excel_ok` + checksums file.
3. **Checksums external** — `checksums.json` hashes products only; manifest written once, not self-hashed.
4. **Excel obrigatório** for `delivery=ok`.
5. **Contratos:** `source_record_run_id=null`; `source_record_id` holds record id (not run).
6. **Adversarial tests** for the above (24 unit passed + 1 skipped).

## Execução canônica (evidência pós-fix)

```text
comando: python -m scripts.ops.weekly_cycle --strict --skip-collect --limit 50
         --output-dir output/weekly/PROOF-01-fix2
exit_code: 0
duration_seconds: ~0.9
collection_id: col-extra-weekly-20260719T193016Z-73a489a8
cycle_id: weekly-20260719T193016Z-978721b174
runs:
  pncp_opportunities → reused_fresh
  pncp_contracts → reused_fresh
counts: opportunities=50, contracts=50 (UF SC only), competitors=50, orgaos=50
claims: opportunity=50, contract=50, competitor=50 (+ runs + freshness)
produtos: output/weekly/PROOF-01-fix2/
evidência: docs/ops/campaigns/EXTRA-OPERATIONAL-PROOF-01/evidence/
tests: default weekly 17p+1s; REQUIRE_REAL_DB=1 integration passed; expanded 143p
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
