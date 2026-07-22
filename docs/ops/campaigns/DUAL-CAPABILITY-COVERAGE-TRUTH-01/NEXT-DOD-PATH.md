# NEXT-DOD-PATH — após verdade dual de cobertura

**Campaign:** `DUAL-CAPABILITY-COVERAGE-TRUTH-01`  
**Base commit (pre-merge):** `5a19df7` (origin/main at branch cut)  
**Implementation branch:** `campaign/dual-capability-coverage-truth`

## Estado comprovado (reproof local)

| Campo | Valor |
|-------|-------|
| Method | `dual_capability_coverage` |
| Universe | den aplicável 1093 (seed planilha; set equality via identity stamps) |
| open_tenders coverage | **0 / 1093 = 0,0%** gate FAIL |
| historical_contracts coverage | **0 / 1093 = 0,0%** gate FAIL |
| data_presence editais | 0,0% (DB extra_test vazio de evidência mapeada) |
| data_presence contratos | 0,0% |
| fresh / stale / unknown(applicability) / blocked | 0 / 0 / 0 / 0 (sem evidência → pending, não covered) |
| measurement_success | **true** |
| coverage_gate_pass | **false** |
| legacy 19,5791% | **SUPERSEDED** (ERRATA-19-5791.md) |
| 95% live claim | **NÃO** |

### Comandos de reproof

```bash
export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}"
python3 -m scripts.ops.apply_migrations --dsn "$LOCAL_DATALAKE_DSN"
python3 -m scripts.coverage.dual_capability_coverage --capability both --output-dir output/coverage
python3 -m scripts.golden_path --execute-dual-coverage-only --capability both
python3 -m pytest tests/test_dual_capability_coverage.py tests/test_golden_path_coverage.py -q -o addopts=
```

### Artefatos

* `output/coverage/dual-capability-coverage-summary.json`
* `output/coverage/dual-coverage-gaps-open_tenders.csv`
* `output/coverage/dual-coverage-gaps-historical_contracts.csv`
* Spec: `specs/001-dual-capability-coverage-truth/`
* ADR-029

## Itens DOD aceitos / reclassificados nesta campanha

| Item | Estado |
|------|--------|
| §12.1 golden path calcula cobertura | **PARTIAL dual measurement** (método canônico; sem 95%) |
| média entre coberturas não mascara | **DONE** (código + testes) |
| contratos ≠ prova editais | **DONE** (testes) |
| stale/unknown não no numerador | **DONE** (código + testes; unknown=applicability) |
| data_presence nunca chamada cobertura | **DONE** (engine + claims_forbidden) |
| capability_monitoring_coverage ≥95% (ambas) | **OPEN** (medição 0% no reproof local) |
| LOCAL_READY / PROJECT_DONE | **NÃO** |

## Dependency graph (caminho crítico)

| DOD item | status | prerequisites | blocker | owner | evidence necessária | comando reproof | próxima ação |
|----------|--------|---------------|---------|-------|---------------------|-----------------|--------------|
| Popular coverage_evidence por ente×pncp×open_tenders | OPEN | dual engine DONE | janela crawl + rate limits | @dev ops | run_id + success_* frescos ≤24h | dual CLI after crawl | backfill PNCP editais por cnpjOrgao no raio |
| Popular coverage_evidence historical_contracts ≥3y | OPEN | dual engine DONE | backfill tempo/API | @dev ops | queried_start/end span≥3y + incremental≤7d | dual CLI | contracts backfill + watermark |
| Mapear entity_id DB ↔ canonical entity_id | OPEN | seed + sc_public_entities | ambiguidade cnpj8 | @data-engineer | map coverage ≥ gate identity | dual report unknown unmapped | improve map_db_entities / identity resolve |
| capability_monitoring_coverage(open_tenders)≥95% | OPEN | evidência fresca ≥1039 entes | dados | ops | dual summary gate PASS | dual CLI --require-gate | operacional após backfill |
| capability_monitoring_coverage(historical_contracts)≥95% | OPEN | idem contratos | dados | ops | dual summary gate PASS | dual CLI --require-gate | operacional após backfill |
| Acceptance pack dual no controller ROI | OPEN | CI merge | @qa independente | @qa/@po | register_acceptance + pack | force-next / campaign.py | após merge main |
| §15 TestSprite black-box | OPEN se tocado | dual CLI estável | TestSprite/DeepSeek config | @qa | sanitizado | testsprite plan | só se §15 no escopo de aceite |
| Fontes complementares (DOM/DOE) | OPEN | não substituem PNCP | credenciais/SLA | ops | evidence applicable | source health | complementar após PNCP |

## Caminho crítico priorizado

1. **Merge** desta campanha em `main` + CI verde.  
2. **Reproof dual em main** (mesmos comandos).  
3. **Backfill PNCP open_tenders** com `coverage_evidence` completo (pagination, run_id, freshness≤24h).  
4. **Backfill historical_contracts** com janela ≥3 anos + incremental ≤7d.  
5. **Re-medir dual** — publicar números reais (sem mediação).  
6. **Só então** candidatar gates 95% via acceptance pack + QA independente.  
7. Continuação DOD: recall, fontes complementares, VPS — **depois** da verdade de cobertura estável.

### Imediatamente implementável

* Merge PR dual coverage  
* Melhorar join identidade se unmapped >0 em DB populado  
* Relatórios operacionais lendo summary dual

### Dependente de fonte externa

* PNCP rate limits / 429  
* DOM/DOE/CIGA SLA e credenciais  

### Dependente de Tiago

* Ratificação subjetiva §15 “fluxo útil”  
* Prioridade comercial de backfill vs outras waves  

### Dependente de VPS

* Crawl contínuo 24h e timers systemd  

### Janela temporal

* Freshness 24h/7d só prova após runs reais no SLA  

## Non-claims

* Não há cobertura 95%.  
* Não há LOCAL_READY.  
* 0% no extra_test **não** é falha de medição — é ausência de evidência operacional no DB de teste.
