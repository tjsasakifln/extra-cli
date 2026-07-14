---
story_id: B2G-DB-01
title: "Schema canônico final — migration baseline limpa, constraints, índices"
status: ready
priority: P0
risk_level: HIGH-RISK
effort: L
agent: "@data-engineer"
epic: EPIC-MASTER-B2G-READINESS
phase: 2
depends_on: [B2G-FIX-04, B2G-INFRA-02]
blocks: [B2G-DB-02, B2G-DB-05, B2G-BACKFILL-01]
---

# Story B2G-DB-01: Schema Canônico Final

## Problema

41 migrations acumuladas, algumas substituídas (025→026), schema real divergente do código, sem baseline limpa para novos ambientes. Setup de banco novo requer executar 41 migrations em sequência — frágil e lento.

**Não se trata de "migration unificada 006-v3" como a B2G-5 propunha.** A abordagem deve ser: gerar migration baseline a partir do schema real (pg_dump --schema-only), validar contra o código, e documentar.

## Escopo

**IN:** Gerar `db/migrations/042_baseline_schema.sql` a partir do schema real validado, documentar todas as tabelas/views/índices/constraints em `docs/schema/`, criar `scripts/schema/diagnostics.py` se ainda não existir, testar apply em banco vazio, testar upgrade do schema atual.

**OUT:** Supabase path (arquivado — decisão: PostgreSQL bare metal), SQLite vs PostgreSQL diff (backlog).

## Acceptance Criteria

1. **AC1:** `042_baseline_schema.sql` recria schema completo em banco vazio — zero erros
2. **AC2:** `docs/schema/final-schema.md` documenta TODAS as tabelas com colunas, tipos, constraints, índices e views
3. **AC3:** Índices para queries frequentes: `orgao_cnpj`, `cnpj_8`, `data_assinatura`, `data_publicacao`, `modalidade`, `matched_entity_id`, `valor_global`
4. **AC4:** `diagnostics.py` reporta zero divergências entre schema real e documentado
5. **AC5:** Teste de upgrade: aplicar 042 sobre schema existente não quebra nada
6. **AC6:** Modelo canônico documentado: entidades (órgão, licitação, contrato, fornecedor, documento) com relações

## Tasks

- [ ] Task 1: Extrair schema real via `pg_dump --schema-only`
- [ ] Task 2: Validar schema contra queries no código (usar diagnostics.py)
- [ ] Task 3: Criar `042_baseline_schema.sql`
- [ ] Task 4: Testar apply em banco vazio
- [ ] Task 5: Testar upgrade (apply sobre schema existente)
- [ ] Task 6: Documentar em `docs/schema/final-schema.md`
- [ ] Task 7: Atualizar `db/current-schema.sql` e SHA256

## Definition of Done

- [ ] 042_baseline_schema.sql funcional em banco vazio
- [ ] Documentação completa do schema
- [ ] Índices críticos criados
- [ ] diagnostics.py limpo
- [ ] Upgrade testado

## Arquivos Afetados

- `db/migrations/042_baseline_schema.sql` (novo)
- `db/current-schema.sql`
- `db/current-schema.sha256`
- `docs/schema/final-schema.md`
- `scripts/schema/diagnostics.py`
