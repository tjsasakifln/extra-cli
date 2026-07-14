---
story_id: B2G-FIX-04
title: "Alinhar schema código↔banco — 10 tabelas fantasmas e colunas divergentes"
status: InProgress
priority: P0
risk_level: HIGH-RISK
effort: M
agent: "@data-engineer"
epic: EPIC-MASTER-B2G-READINESS
phase: 0
depends_on: []
blocks: [B2G-DB-01, B2G-INFRA-02]
---

# Story B2G-FIX-04: Alinhar schema código↔banco

## Problema

Auditoria confirmou divergência crítica entre o schema que o código referencia e o schema real do PostgreSQL:

### 10 tabelas referenciadas no código que NÃO existem no banco

```
coverage_evidence, engineering_opportunities, entity_hierarchy,
opportunity_intel, opportunity_checkpoints, opportunity_runs,
opportunity_coverage, pncp_enrichment_cache, sc_municipalities,
sc_dados_abertos_backfill_log
```

### Colunas em queries que não existem nas tabelas reais

Queries referenciam colunas que o schema real não possui. Exemplo: queries usam `match_method`, `match_score`, `match_confidence` mas `pncp_raw_bids` não tem essas colunas (foram adicionadas via ALTER TABLE ad-hoc durante o coverage assessment).

### Causa Raiz

41 migrations foram aplicadas em ordem cronológica, mas:
- Algumas migrations foram substituídas (ex: 025 → 026)
- Nem todas as migrations foram aplicadas no banco local
- O código evoluiu mais rápido que as migrations
- Não existe migration de validação (schema fingerprint)

## Valor de Negócio

Sem alinhamento schema↔código, qualquer operação de crawler ou pipeline pode falhar em runtime com erros de "column does not exist" ou "relation does not exist". Isso é bloqueante para produção.

## Escopo

### IN
- Auditar TODAS as queries no código e comparar com schema real
- Para cada tabela fantasma: decidir se cria a tabela (migration) ou remove a referência (código)
- Para cada coluna fantasma: decidir se adiciona a coluna (migration) ou corrige a query
- Criar migrations corretivas (040+) para adicionar tabelas/colunas faltantes
- Criar `scripts/schema/diagnostics.py` que compara schema real vs esperado
- Atualizar `db/current-schema.sql` e `db/current-schema.sha256`

### OUT
- Migration unificada do zero (B2G-DB-01)
- Redesign de schema (B2G-DB-01)
- Correção de dados (B2G-DB-03)

## Acceptance Criteria

### AC1: Diagnóstico automatizado
**Given** `scripts/schema/diagnostics.py`
**When** executado contra o banco local
**Then** reporta exatamente quais tabelas e colunas esperadas faltam no schema real
**And** sai com código 0 se schema está alinhado, 1 se há divergências

### AC2: Zero tabelas fantasmas
**Given** as correções aplicadas
**When** `diagnostics.py` executa
**Then** zero tabelas referenciadas no código que não existem no banco

### AC3: Zero colunas fantasmas
**Given** as correções aplicadas
**When** queries no código são executadas
**Then** zero erros "column does not exist"

### AC4: Migration apply limpo
**Given** um banco PostgreSQL vazio
**When** `bash db/setup_db.sh` executa
**Then** todas as migrations aplicam sem erro
**And** `diagnostics.py` reporta schema alinhado

### AC5: Teste de integração passa
**Given** schema alinhado
**When** `pytest tests/integration/test_migration_fresh_install.py` executa
**Then** todos os testes passam (incluindo `test_canonical_views_exist`)

## Tasks

- [ ] Task 1: Executar auditoria completa de queries vs schema real
- [ ] Task 2: Criar `scripts/schema/diagnostics.py`
- [ ] Task 3: Criar migrations corretivas para tabelas e colunas faltantes
- [ ] Task 4: Corrigir queries com colunas fantasmas
- [ ] Task 5: Atualizar `current-schema.sql` e SHA256
- [ ] Task 6: Testar `setup_db.sh` em banco vazio
- [ ] Task 7: Corrigir `test_canonical_views_exist`

## Definition of Done

- [ ] diagnostics.py funcional e reportando zero divergências
- [ ] setup_db.sh funcional em banco vazio
- [ ] test_canonical_views_exist passa
- [ ] Nenhuma query referencia tabela ou coluna inexistente
- [ ] current-schema.sql e SHA256 atualizados

## Arquivos Afetados

- `db/migrations/` (novas migrations 040+)
- `scripts/schema/diagnostics.py` (novo)
- `scripts/opportunity_intel/schema.py`
- `scripts/consulting_readiness.py`
- `scripts/coverage_truth.py`
- `scripts/crawl/monitor.py`
- `db/current-schema.sql`
