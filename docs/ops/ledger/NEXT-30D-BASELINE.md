# NEXT-30D Baseline — Estado inicial da campanha

**Campanha:** `NEXT-30D-MULTIAGENT`  
**Capturado em:** 2026-07-17T00:04:45Z  
**Branch inicial:** `main` → criada `epic/next-30d-multiagent-execution`  
**SHA inicial:** `77ff8a8cdaca110753f808bdcf44f99e0b6efced`  
**Working tree:** limpa (0 arquivos dirty)  

## Comandos de captura

```bash
git rev-parse HEAD
git status --porcelain
ls db/migrations/*.sql | wc -l
# DB metrics via psycopg2 → postgresql://test:test@127.0.0.1:5433/pncp_datalake
pytest tests/ -q --collect-only
```

## Git / branch

| Campo | Valor |
|-------|-------|
| SHA full | `77ff8a8cdaca110753f808bdcf44f99e0b6efced` |
| SHA short | `77ff8a8` |
| Branch | `epic/next-30d-multiagent-execution` (from main) |
| Dirty files | 0 |

## Testes obrigatórios existentes

| Métrica | Valor |
|---------|-------|
| Tests collected | **1575** (10 deselected) |
| Collect duration | 37.02s |
| Suite crítica prévia (Q5.1 baseline) | 82 PASS documentados |
| Regressão ampla | **não** reexecutada nesta baseline (só collect) |

## Migrations / schema

| Métrica | Valor |
|---------|-------|
| Arquivos SQL em `db/migrations/` | **54** |
| Linhas em `_migrations` (runtime DB) | **53** |
| Status de algumas migrations | mistura `applied` / `failed` (ex.: 007/009 “already exists”) |
| Fresh install documentado (GATE-1) | 54/54 em ambiente limpo (HEAD anterior) |
| Divergência | runtime DB ≠ fresh clean; **schema audit obrigatório na Wave 1** |

## Contagens de dados (DB local :5433 / `pncp_datalake`)

| Tabela / métrica | Valor |
|------------------|-------|
| `pncp_raw_bids` | 346 |
| `pncp_supplier_contracts` | **0** |
| `opportunity_intel` | 5 (fixtures `test_batch`) |
| `entity_aliases` (active) | 459 |
| `dedup_cross_source` | **0** |
| `target_universe_entities` | 2085 |
| `entity_coverage` | 18765 |
| `capability_coverage` | **0** |
| `coverage_evidence` | **0** |
| `coverage_snapshots` | **0** |
| `mv_entity_source_applicability` | 20850 (2085 × 10 sources) |
| `is_applicable=true` | 12728 |
| `is_applicable=false` | 8122 |
| Pares `unknown` (status column) | **N/A** — matriz usa `is_applicable` booleano, não enum `unknown` |
| `sc_compras` aplicável | 2085/2085 (regra genérica; **sem cobertura operacional**) |

## Cobertura editais / contratos (honestidade)

| Capability | Valor baseline | Fonte |
|------------|----------------|-------|
| Editais (raio) | ~**3,1%** snapshot 15/07 — **não** recalculado agora | handoff / rebaseline |
| Contratos | **0%** operacional (`pncp_supplier_contracts=0`) | SQL 2026-07-17 |
| capability_monitoring_coverage canônica | **UNKNOWN** nesta baseline (sem run coverage_truth) | — |

**Não afirmar 95%.** Presença de `entity_coverage` rows ≠ cobertura DoD.

## Golden path

| Item | Estado |
|------|--------|
| Último run documentado | `gp-20260716-200904` SUCCESS (pcp+compras_gov, `--skip-freshness`) |
| PNCP no SOURCES | `essential=False` (API degradada) |
| Fail-closed | **AUSENTE** — essential_fail → exit 2, mas success com fetched=0 possível; freshness/report fail **não** forçam exit ≠ 0 |
| Próximo passo | implementar strict fail-closed |

## DONE_PARTIAL da campanha anterior (auditoria)

| ID | Residual |
|----|----------|
| G0.4 | evidence-index stale |
| L1.4 | matriz ente×fonte agregada / partial |
| C2.1 | fórmulas documentadas; gaps HIGH-RISK de implementação |
| C2.2 | success_zero/freshness código; SLA gaps |
| L1.8 | GATE-1 partial; não LOCAL_READY |
| C2.3 | PNCP timeout residual |
| C2.8 | DedupEngine **não** no pipeline; 0 rows |
| Q5.1 | claim 21 vs 82 PASS |
| Q5.4 | snapshot lint/types; **sem remediação** |

## Blockers externos

| ID | Causa | Owner |
|----|-------|-------|
| V6.2 | Conta/pagamento VPS + SSH/backup creds | Tiago |
| DOE-SC | Credenciais `DOE_SC_LOGIN` / `DOE_SC_PASSWORD` | Tiago (se disponíveis) |
| PNCP API | Timeouts ocasionais | externo |

## Caminho crítico seguinte (PERT ceil)

```
C2.7 (15) → C2.10 (5) → C2.11 (10) = 30 dias úteis no CP
```

Paralelo: K3.2 pilot 90d (12), C2.8 wire dedup (7), C2.9 snapshot (8), Q5.4 remediate (6).

## Próximo trecho real

1. Fail-closed golden path + schema audit  
2. Ingestão real `sc_compras`  
3. Pilot contratos PNCP 90d  
4. Wire `DedupEngine`  
5. Coverage truth editais/contratos  
