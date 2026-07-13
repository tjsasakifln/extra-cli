---
story_id: B2G-5
status: draft
priority: P1
epic: EPIC-MASTER-B2G-READINESS
agent: @data-engineer
depends_on: [TD-2.1, TD-2.2, TD-2.4]
---

# Story B2G-5: Schema Final + Supabase Path

## Context

O DataLake Extra Consultoria atualmente roda em PostgreSQL local (porta 5433 ou 54399, dependendo da configuracao). O PRD preve migracao futura para Hetzner VPS com PostgreSQL 17, e eventualmente Supabase self-hosted no mesmo Hetzner.

Problemas atuais:

1. **Multiplos schemas**: Migrations 001-026 aplicadas em ordem cronologica, mas algumas foram substituidas (ex: 025->026). Schema real e diferente do esperado em alguns casos.
2. **SQLite vs PostgreSQL**: Alguns testes rodam em SQLite com schema adaptado — diferencas semanticas entre SQLite e PostgreSQL nao documentadas.
3. **Supabase path**: Documentar como exportar dados do PostgreSQL local para Supabase self-hosted em Hetzner.
4. **Migration unificada**: Criar migration 006-v3 que representa o schema final desejado, consolidando todas as alteracoes das migrations 001-026.

### Abordagem

1. **Diagnostico**: Inspecionar schema real do PostgreSQL vs migrations aplicadas. Identificar discrepancias.
2. **Migration unificada (006-v3)**: Criar migration do zero que aplica schema final completo, sem dependencia das migrations anteriores.
3. **Documentacao**: Schema documentado em `docs/schema/final-schema.md` com todas as tabelas, colunas, tipos, constraints, indices, e views.
4. **Export script**: `scripts/migration/export_to_supabase.py` que exporta dados do PostgreSQL local para Supabase self-hosted.
5. **Diferencas SQLite vs PostgreSQL**: Documentado em `docs/schema/sqlite-vs-postgresql.md`.

## Acceptance Criteria

1. **AC1: Diagnostico de schema** — Script `scripts/schema/diagnostics.py` que compara schema real do PostgreSQL com migrations aplicadas e reporta discrepancias (tabelas faltando, colunas extras, tipos diferentes, constraints faltando)
2. **AC2: Migration unificada 006-v3** — `db/migrations/006_v3_unified_schema.sql` contem CREATE TABLE + CREATE VIEW + CREATE INDEX para TODO o schema final. Nao depende de migrations anteriores. Inclui: `sc_public_entities`, `pncp_raw_bids`, `pncp_supplier_contracts`, `entity_coverage`, `enriched_entities`, `ingestion_runs`, `ingestion_checkpoints`, `contract_values_disambiguated`, views analiticas da contract_intel e competitors
3. **AC3: Indices** — Migration unificada inclui indices para queries frequentes: `orgao_cnpj`, `cnpj_8`, `ni_fornecedor`, `data_assinatura`, `data_publicacao`, `modalidade`, `matched_entity_id`, `valor_global`
4. **AC4: Schema documentation** — `docs/schema/final-schema.md` gerado automaticamente ou manualmente com: diagrama ER (ASCII), lista de tabelas com colunas/tipos/descricao, lista de views com SQL e descricao, lista de indices, relacoes de foreign key
5. **AC5: SQLite vs PostgreSQL diff** — `docs/schema/sqlite-vs-postgresql.md` documenta: tipos que diferem (INTEGER vs SERIAL, TEXT vs VARCHAR, etc.), funcoes diferentes (datetime vs NOW(), etc.), strategies de testing com SQLite vs PostgreSQL
6. **AC6: Export script funcional** — `scripts/migration/export_to_supabase.py` conecta no PostgreSQL local, exporta todas as tabelas para SQL, e gera script de import para Supabase. Inclui: export full, export incremental (ultimos N dias), compressao (gzip), progress bar
7. **AC7: Supabase path documentado** — `docs/schema/supabase-migration-path.md` com: requisitos (Hetzner VPS, Docker, Supabase stack), passo a passo de instalacao, configuracao de auth (single user), configuracao de backup, rollback plan
8. **AC8: ADR-003 atualizado** — `docs/decisions/adr-003-supabase-self-hosted.md` atualizado com resultados do diagnostico e decisoes tomadas
9. **AC9: Migration apply limpo** — `psql -f db/migrations/006_v3_unified_schema.sql` aplica sem erros em um banco vazio (testado)
10. **AC10: Testes** — Testes de schema: `pytest tests/test_schema.py -v` verifica que o schema real corresponde ao esperado (colunas, tipos, constraints)

## Technical Design

### Migration unificada (006-v3)

```sql
-- db/migrations/006_v3_unified_schema.sql
-- Schema final unificado para Extra Consultoria DataLake
-- Compatível com PostgreSQL 17
-- Nao depende de migrations anteriores

BEGIN;

-- Tabelas
CREATE TABLE IF NOT EXISTS sc_public_entities (
    id SERIAL PRIMARY KEY,
    razao_social VARCHAR(500) NOT NULL,
    cnpj_8 VARCHAR(8),
    municipio VARCHAR(200),
    codigo_ibge VARCHAR(7),
    natureza_juridica VARCHAR(200),
    cod_natureza VARCHAR(10),
    latitude NUMERIC(10, 7),
    longitude NUMERIC(10, 7),
    distancia_fk NUMERIC(10, 2),
    raio_200km BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pncp_raw_bids (
    id SERIAL PRIMARY KEY,
    orgao_cnpj VARCHAR(14),
    orgao_nome VARCHAR(500),
    uf VARCHAR(2),
    municipio VARCHAR(200),
    modalidade VARCHAR(100),
    objeto TEXT,
    data_publicacao DATE,
    data_abertura DATE,
    valor_estimado NUMERIC(18,2),
    valor_homologado NUMERIC(18,2),
    matched_entity_id INTEGER REFERENCES sc_public_entities(id),
    source VARCHAR(50),
    content_hash VARCHAR(64),
    ingested_at TIMESTAMP DEFAULT NOW()
);

-- ... (demais tabelas e views)
COMMIT;
```

### Export script

```python
# scripts/migration/export_to_supabase.py
# Uso: python scripts/migration/export_to_supabase.py --mode full --output /backup/export.sql.gz
```

### Diagnostico

```python
# scripts/schema/diagnostics.py
# Uso: python scripts/schema/diagnostics.py --report
# Saida: output/schema/diagnostics.json + output/schema/discrepancias.md
```

## Files to Create/Modify

- **CREATE** `db/migrations/006_v3_unified_schema.sql` — Migration unificada
- **CREATE** `scripts/schema/diagnostics.py` — Diagnostico de schema
- **CREATE** `scripts/migration/export_to_supabase.py` — Export script
- **CREATE** `docs/schema/final-schema.md` — Schema documentation
- **CREATE** `docs/schema/sqlite-vs-postgresql.md` — Diferencas SQLite vs PostgreSQL
- **CREATE** `docs/schema/supabase-migration-path.md` — Supabase path
- **CREATE** `tests/test_schema.py` — Testes de schema
- **MODIFY** `docs/decisions/adr-003-supabase-self-hosted.md` — Atualizar com resultados

## Rollback

- Migration unificada e idempotente (CREATE IF NOT EXISTS) — aplicar em banco novo nao afeta banco existente
- Export script nao modifica dados — apenas le

## Observability

- Diagnostico de schema gera relatorio em `output/schema/`
- Export script loga progresso: "Exportando tabela X (Y linhas)..."
- Logs em `logs/migration-{timestamp}.log`

## Security Considerations

- Export script pode conter dados publicos de licitacoes — sem dados sensiveis
- Supabase path documenta configuracao de auth single-user
- Backup do export deve ser armazenado em local seguro

## Tests

- `test_schema_columns` — Verifica colunas esperadas em cada tabela
- `test_schema_types` — Verifica tipos das colunas
- `test_schema_constraints` — Verifica primary keys, foreign keys, not null, unique
- `test_schema_views` — Verifica que views existem e compilam
- `test_migration_apply` — Aplica migration 006-v3 em banco vazio e verifica schema

## Definition of Done

- [ ] AC1 a AC10 implementados e verificados
- [ ] Migration 006-v3 aplicada limpa em banco PostgreSQL vazio
- [ ] `scripts/schema/diagnostics.py` executa sem erro
- [ ] `docs/schema/final-schema.md` revisado e completo
- [ ] `scripts/migration/export_to_supabase.py` funcional
- [ ] `pytest tests/test_schema.py -v` retorna all passed
- [ ] ADR-003 atualizado
