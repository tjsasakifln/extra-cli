# Legacy Impact: Consolidação dos Módulos de Alta Confiança

> Feature: `001-modulos-alta-confianca`
> Data: 2026-07-14
> Âncora: `_reversa_sdd/architecture.md` + `_reversa_sdd/domain.md`
> Base: stories 1.1→1.5 do `epic-technical-debt.md` (Done)

## Arquivos afetados

| Arquivo | Componente | Tipo | Severidade | Justificativa |
|---------|------------|------|------------|---------------|
| `docker-compose.local.yml` | Deploy | componente-novo | HIGH | Expande docker-compose.yml existente. Adiciona serviço app. Sem alterar test-db. |
| `Makefile` | Deploy | componente-novo | HIGH | Orquestração local reproduzível. Targets: run-pipeline, test, lint, clean. |
| `scripts/bootstrap_local.sh` | Deploy | componente-novo | HIGH | Bootstrap idempotente: DB → migrations → seed → verify. |
| `.coveragerc` | Tests | componente-novo | MEDIUM | Seção [coverage_gate] com 7 módulos e threshold 80%. |
| `scripts/ci_gate.sh` | CI Gates | contrato-novo | HIGH | Pipeline fail-closed: ruff→pyright→bandit→pytest→coverage_gate. |
| `scripts/coverage_gate.py` | Tests | componente-novo | HIGH | Verifica coverage por módulo via coverage.py API. Exit 2 se abaixo de 80%. |
| `scripts/opportunity_intel/reconciliation.py` | Opportunity Intel | componente-novo | HIGH | reconcile_snapshot() com dry-run, logging JSON, idempotência. |
| `scripts/opportunity_intel/competitive_intel_validation.py` | Opportunity Intel | componente-novo | MEDIUM | Validação read-only de queries competitive intel contra PostgreSQL real. |
| `scripts/opportunity_intel/ranking.py` | Opportunity Intel | regra-alterada | HIGH | URL enforcement: PRIORITARIA sem official_url → downgrade REVISAR. |
| `scripts/opportunity_intel/radar.py` | Opportunity Intel | delta-de-dados | HIGH | Etapa 12: reconcile_snapshot() no pipeline. Campo reconciliation no manifest. |
| `scripts/opportunity_intel/manifest.py` | Opportunity Intel | delta-de-dados | MEDIUM | Métricas de reconciliação no coverage e source-health. |
| `scripts/opportunity_intel/cli.py` | Opportunity Intel | contrato-novo | MEDIUM | Novo comando `reconcile --run-id --dry-run`. |
| `tests/test_snapshot_reconciliation.py` | Tests | componente-novo | MEDIUM | 7 testes unitários para reconcile_snapshot(). |
| `tests/test_competitive_intel_validation.py` | Tests | componente-novo | MEDIUM | 2 testes para validate_competitive_intel_schema(). |
| `tests/test_opportunity_ranking.py` | Tests | regra-alterada | MEDIUM | 3 novos testes para URL enforcement. |

## Diff conceitual por componente

### Deploy
**Antes:** Sem orquestração local. docker-compose.yml só com test-db. Comandos manuais. Sem Makefile. Sem bootstrap automatizado.
**Depois:** docker-compose.local.yml com serviço app. Makefile com 12 targets. bootstrap_local.sh idempotente com 4 steps.

### Tests
**Antes:** pytest-cov gera relatório mas sem gate. Sem threshold por módulo. Sem CI gate unificado.
**Depois:** coverage_gate.py verifica 7 módulos a 80%. ci_gate.sh pipeline fail-closed. .coveragerc com seção [coverage_gate].

### Opportunity Intel
**Antes:** QW-01 Radar com 11 etapas. Sem reconciliação de snapshot. PNCP-only (20.95% com link). Competitive intel com colunas não validadas.
**Depois:** 12ª etapa de reconciliação. URL enforcement (PRIORITARIA requer official_url). Validação de schema competitive intel. Dry-run e CLI reconcile.

## Preservadas

Regras do `_reversa_sdd/domain.md` que continuam intactas:

| Regra | Descrição | Status |
|-------|-----------|--------|
| R1 | Filtro de engenharia (17 keywords) | ✅ Intacta |
| R2 | Janela de cobertura 90 dias | ✅ Intacta |
| R3 | Raio de 200km (Haversine) | ✅ Intacta |
| R4 | Capacidade financeira 10× | ✅ Intacta |
| R5 | Threshold de participação 0.45 | ✅ Intacta |
| R6 | Override de recomendação (6 regras) | ✅ Intacta |
| R7 | Hard incompatible patterns CNAE | ✅ Intacta |
| R8 | Dedup cross-source SHA-256 | ✅ Intacta |
| R9 | Retenção e purge (400d+90d) | ✅ Intacta |
| MS1 | Status temporal do edital | ✅ Intacta |
| MS8 | QW-01 Radar execution (11 etapas) | ⚠️ Expandida (+1 etapa) |

## Modificadas

| Regra | Alteração | Justificativa |
|-------|-----------|---------------|
| MS8 (QW-01 Radar) | +1 etapa: snapshot reconciliation (step 12) | Fecha lacuna P0-04 do plano mestre |
| Regra de ranking (implícita) | URL enforcement: PRIORITARIA requer official_url | Fecha lacuna de qualidade (20.95% → 100% link) |
| Competitive intel (implícita) | Validação de schema adicionada (read-only) | Prepara terreno para P0-09 |

## Histórico de alterações

| Data | Alteração | Autor |
|------|-----------|-------|
| 2026-07-14 | Versão inicial gerada por `/reversa-coding` | reversa |
