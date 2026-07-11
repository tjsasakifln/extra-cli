# Migrations Adaptadas — TD-2.2

**Story:** TD-2.2 — Aplicar Migrations 009-012 Adaptadas
**Debitos:** TD-DB-02a (HIGH), TD-DB-02b (LOW)
**Data:** 2026-07-11
**Schema base:** 001-v2_initial_schema.sql (TD-2.1 baseline)

## Resumo

As migrations v1 009-012 foram analisadas e adaptadas para o schema v2 baseline.
A analise mostrou que a maior parte do conteudo destas migrations ja esta incluida
no baseline 001-v2. Apenas dois itens estavam efetivamente ausentes:

1. **match_logging** (v1 010): Colunas `match_method`, `match_score`, `match_confidence`
   e indexes relacionados nao existiam no schema real nem no baseline.
2. **v_unmatched_bids** (v1 011): View para debugging de bids sem match estava ausente.

## Verificacao Realizada

### AC1: match_logging no schema baseline

**Resultado:** As colunas `match_method`, `match_score`, `match_confidence` **NAO existem**
no schema baseline 001-v2. A tabela `pncp_raw_bids` foi criada sem estas colunas.

**Decisao:** Migration adaptada criada: `005-v2-td-2.2_match_logging.sql`

### AC2: entity_coverage

**Resultado:** A tabela `entity_coverage` **JA EXISTE** no baseline 001-v2
(Section 2.3), incluindo triggers, funcoes e chave estrangeira.

**Decisao:** Migration adaptada criada como verificacao idempotente:
`002-v2-td-2.2_entity_coverage.sql`

### AC3: v_coverage_summary

**Resultado:** A view `v_coverage_summary` **JA EXISTE** no baseline 001-v2
(Section 4.3).

**Decisao:** Incluida na migration de coverage views:
`003-v2-td-2.2_coverage_views.sql`

### AC4: v_unmatched_bids

**Resultado:** A view `v_unmatched_bids` **NAO EXISTE** no baseline 001-v2.

**Decisao:** Migration adaptada criada com a view:
`003-v2-td-2.2_coverage_views.sql`

### AC5: coverage_snapshots

**Resultado:** A tabela `coverage_snapshots` **JA EXISTE** no baseline 001-v2
(Section 2.6), incluindo indexes, funcao `generate_coverage_snapshot`, e as
views `v_coverage_gaps`, `v_coverage_gaps_by_municipio`, `v_coverage_trend`.

**Decisao:** Migration adaptada criada como verificacao idempotente:
`004-v2-td-2.2_coverage_snapshots.sql`

### AC6: match_logging adaptado

**Resultado:** Migration 010 adaptada e criada como `005-v2-td-2.2_match_logging.sql`.

## Migrations Criadas

| Versao | Arquivo | Origem v1 | Conteudo | Tipo |
|--------|---------|-----------|----------|------|
| 002-v2 | `td-2.2_entity_coverage.sql` | 009 | entity_coverage (idempotente), triggers, indexes | VERIFICACAO |
| 003-v2 | `td-2.2_coverage_views.sql` | 009 + 011 | v_coverage_summary, v_unmatched_bids (NOVA) | ADAPTADA + NOVA |
| 004-v2 | `td-2.2_coverage_snapshots.sql` | 012 | coverage_snapshots (idempotente), gap/trend views, generate_coverage_snapshot | VERIFICACAO |
| 005-v2 | `td-2.2_match_logging.sql` | 010 | match_method, match_score, match_confidence, indexes | NOVA |

### Legenda

| Tipo | Descricao |
|------|-----------|
| **VERIFICACAO** | Objeto ja existe no baseline; migration garante IF NOT EXISTS e registro em _migrations |
| **ADAPTADA** | Objeto adaptado da versao v1 com alteracoes para o schema v2 |
| **NOVA** | Objeto que NAO existia no baseline, criado a partir do zero |

## Divergencias entre v1 e v2

### Migration 009 (indexes_and_coverage)

| Item v1 | Status v2 | Observacao |
|---------|-----------|------------|
| `entity_coverage` table | Ja existe (Section 2.3) | IF NOT EXISTS |
| `update_entity_coverage()` function | Ja existe (Section 3.5) | OR REPLACE |
| `trg_bids_coverage` trigger | Ja existe (Section 6) | DROP IF EXISTS + CREATE |
| `update_entity_coverage_on_update()` function | Ja existe (Section 3.6) | OR REPLACE |
| `trg_bids_coverage_update` trigger | Ja existe (Section 6) | DROP IF EXISTS + CREATE |
| Indexes (idx_cov_*) | Ja existem (Section 5) | IF NOT EXISTS |
| `v_coverage_summary` | Ja existe (Section 4.3) | OR REPLACE |
| Seed data inserts | OMITIDO | Aplicacao gerencia |

### Migration 010 (match_logging)

| Item v1 | Status v2 | Observacao |
|---------|-----------|------------|
| `match_method` column | NOVO | ADD COLUMN IF NOT EXISTS |
| `match_score` column | NOVO | ADD COLUMN IF NOT EXISTS |
| `match_confidence` column | NOVO | ADD COLUMN IF NOT EXISTS |
| `idx_bids_match_method` index | NOVO | IF NOT EXISTS |
| `idx_bids_match_coverage` index | NOVO | IF NOT EXISTS |

### Migration 011 (unmatched_bids_view)

| Item v1 | Status v2 | Observacao |
|---------|-----------|------------|
| `v_unmatched_bids` view | NOVO | CREATE OR REPLACE |
| Referencia a match_method/match_score/match_confidence | NOVO | Colunas criadas em 005-v2 |
| Referencia a `e.uf` (comentada na v1) | OMITIDO | Coluna uf nao existe em sc_public_entities |

### Migration 012 (coverage_snapshots)

| Item v1 | Status v2 | Observacao |
|---------|-----------|------------|
| `coverage_snapshots` table | Ja existe (Section 2.6) | IF NOT EXISTS |
| Indexes (idx_cov_snap_*) | Ja existem (Section 5) | IF NOT EXISTS |
| `v_coverage_gaps` view | Ja existe (Section 4.1) | OR REPLACE |
| `v_coverage_gaps_by_municipio` view | Ja existe (Section 4.2) | OR REPLACE |
| `v_coverage_trend` view | Ja existe (Section 4.4) | OR REPLACE |
| `generate_coverage_snapshot()` function | Ja existe (Section 3.7) | OR REPLACE |

## Aplicacao no Banco Local

**Status da aplicacao:** APLICADA (pncp_datalake via postgres local)

### Resultados

| Migration | Status | Objetos Criados |
|-----------|--------|-----------------|
| 002-v2 | APLICADA | entity_coverage (ja existia, IF NOT EXISTS), triggers recriados, indexes verificados |
| 003-v2 | APLICADA | v_coverage_summary (ja existia, OR REPLACE), **v_unmatched_bids (NOVA, criada)** |
| 004-v2 | APLICADA | coverage_snapshots (ja existia, IF NOT EXISTS), views recriadas, generate_coverage_snapshot recriada |
| 005-v2 | APLICADA | match_method/match_score/match_confidence (ja existiam, ADD COLUMN IF NOT EXISTS), indexes criados |

### Descoberta Importante

As colunas `match_method`, `match_score`, `match_confidence` **JA EXISTIAM** no schema real do banco pncp_datalake, mesmo nao estando presentes no baseline 001-v2. Isto indica que foram adicionadas diretamente ao banco (provavelmente pelo script monitor.py) sem migration correspondente.

A migration 005-v2 formaliza estas colunas na cadeia de migrations v2, garantindo que ambientes novos as tenham.

**Comando para aplicar em novo ambiente:**
```bash
# Apos configurar LOCAL_DATALAKE_DSN no .env:
psql "$LOCAL_DATALAKE_DSN" -f supabase/migrations/002-v2-td-2.2_entity_coverage.sql
psql "$LOCAL_DATALAKE_DSN" -f supabase/migrations/003-v2-td-2.2_coverage_views.sql
psql "$LOCAL_DATALAKE_DSN" -f supabase/migrations/004-v2-td-2.2_coverage_snapshots.sql
psql "$LOCAL_DATALAKE_DSN" -f supabase/migrations/005-v2-td-2.2_match_logging.sql
```

**Ordem de aplicacao obrigatoria:**
1. 002-v2 (entity_coverage)
2. 004-v2 (coverage_snapshots) — depende de entity_coverage
3. 005-v2 (match_logging) — independente
4. 003-v2 (coverage_views) — depende de match_logging (v_unmatched_bids referencia match_method)

## Verificacao Pos-Aplicacao

```sql
-- Verificar colunas match_logging
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'pncp_raw_bids' AND column_name IN ('match_method', 'match_score', 'match_confidence');

-- Verificar views
SELECT viewname, definition FROM pg_views
WHERE viewname IN ('v_coverage_summary', 'v_unmatched_bids', 'v_coverage_gaps', 'v_coverage_trend');

-- Verificar migrations registradas
SELECT * FROM _migrations ORDER BY version;

-- Testar v_unmatched_bids (deve retornar bids sem match)
SELECT COUNT(*) FROM v_unmatched_bids;

-- Testar generate_coverage_snapshot
SELECT generate_coverage_snapshot(CURRENT_DATE);
```

## Checklist

- [x] AC1: Verificado que match_logging NAO existe no baseline. Migration 005-v2 criada.
- [x] AC2: Verificado que entity_coverage ja existe no baseline. Migration 002-v2 adaptada.
- [x] AC3: Verificado que v_coverage_summary ja existe. Incluida em 003-v2.
- [x] AC4: v_unmatched_bids NAO existe. Criada em 003-v2.
- [x] AC5: Verificado que coverage_snapshots ja existe. Migration 004-v2 adaptada.
- [x] AC6: match_logging adaptado em 005-v2 (ADD COLUMN IF NOT EXISTS).
- [x] AC7: Todas as 4 migrations registradas em _migrations (002-v2 a 005-v2).
- [x] AC8: Views e triggers funcionando com dados existentes:
  - v_unmatched_bids: 989 registros retornados
  - v_coverage_summary: 5 linhas com dados de cobertura
  - v_coverage_gaps: 1864 entes com gap
  - v_coverage_gaps_by_municipio: aggregado por municipio
  - generate_coverage_snapshot: 2 snapshots gerados
  - v_coverage_trend: funcional (depende de snapshots)
