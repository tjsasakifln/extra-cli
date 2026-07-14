---
story_id: B2G-INFRA-02
title: "Configurar PostgreSQL + migrations + seeds na VPS"
status: ready
priority: P0
risk_level: STANDARD
effort: S
agent: "@data-engineer"
epic: EPIC-MASTER-B2G-READINESS
phase: 1
depends_on: [B2G-INFRA-01, B2G-FIX-04]
blocks: [B2G-BACKFILL-01, B2G-DB-01]
---

# Story B2G-INFRA-02: PostgreSQL + Migrations + Seeds

## Problema

A VPS provisionada por B2G-INFRA-01 tem PostgreSQL instalado mas o banco está vazio. É preciso aplicar migrations (41 arquivos) e seeds (2.085 entidades) para deixar o schema pronto para crawlers.

## Escopo

**IN:** Aplicar `db/setup_db.sh` na VPS, validar schema, verificar constraints e índices, carregar seeds.
**OUT:** Correção de schema (B2G-FIX-04), migration unificada (B2G-DB-01).

## Acceptance Criteria

1. **AC1:** `db/setup_db.sh` executa limpo na VPS — zero erros em todas as 41 migrations + seed
2. **AC2:** `psql -c "\dt"` mostra todas as tabelas esperadas (pncp_raw_bids, sc_public_entities, entity_coverage, etc.)
3. **AC3:** `SELECT COUNT(*) FROM sc_public_entities` retorna 2.085
4. **AC4:** `scripts/schema/diagnostics.py` (de B2G-FIX-04) reporta schema alinhado
5. **AC5:** `pg_dump --schema-only` gera dump limpo sem warnings

## Tasks

- [ ] Task 1: Copiar `db/` para VPS via scp
- [ ] Task 2: Executar `bash db/setup_db.sh` com DSN correto
- [ ] Task 3: Verificar cada tabela e view esperada
- [ ] Task 4: Executar diagnostics.py
- [ ] Task 5: Gerar schema dump para referência

## Definition of Done

- [ ] 41 migrations aplicadas sem erro
- [ ] 2.085 entidades carregadas
- [ ] diagnostics.py reporta zero divergências
- [ ] schema dump armazenado em `docs/schema/`

## Arquivos Afetados

- `db/setup_db.sh` (possíveis ajustes de DSN)
- `docs/schema/current-schema.sql` (atualizado)
