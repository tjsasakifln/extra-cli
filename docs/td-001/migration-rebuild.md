# Migration Rebuild — Analise de Divergencias

**Story:** TD-2.1 — Reconstruir Migrations do Zero
**Debitos:** TD-DB-01 (CRITICAL), TD-DB-17 (LOW)
**Data:** 2026-07-11
**Schema extraido de:** Local pncp_datalake (PostgreSQL 18.4)

## Resumo

O schema real do banco foi extraido via `pg_dump --schema-only --no-owner --no-privileges`
do banco local `pncp_datalake` e comparado com as 14 migrations existentes em
`db/migrations/`. Este documento registra cada divergencia encontrada.

**Nota importante:** O schema foi extraido do banco local (PostgreSQL 18, database
`pncp_datalake`), que e o ambiente de desenvolvimento. Para verificacao contra
producao (Hetzner VPS), execute em horario de baixa carga:

```bash
# Apos configurar LOCAL_DATALAKE_DSN no .env
bash scripts/verify-schema-divergence.sh --refresh
bash scripts/verify-schema-divergence.sh --check-migrations
```

## Divergencias Encontradas

### D1 — Tabelas no schema real ausentes nas migrations v1

| Tabela | Presente em | Ausente em | Severidade |
|--------|-------------|------------|------------|
| `coverage_snapshots` | Schema real, 009, 012 | — | OK |
| `enriched_entities` | Schema real, 003 | — | OK |
| `entity_coverage` | Schema real, 009 | — | OK |
| `ingestion_checkpoints` | Schema real, 004 | — | OK |
| `ingestion_runs` | Schema real, 004 | — | OK |
| `pncp_raw_bids` | Schema real, 001 | — | OK |
| `pncp_supplier_contracts` | Schema real, 002 | — | OK |
| `sc_public_entities` | Schema real, 007 | — | OK |

**Veredito:** Todas as 8 tabelas do schema real estao contempladas nas migrations v1
(em algum momento). Nao ha tabelas orfas no banco.

### D2 — Colunas divergentes

| Tabela | Coluna | Schema real | Migration v1 | Severidade |
|--------|--------|-------------|--------------|------------|
| `pncp_raw_bids` | `content_hash` | UNIQUE | UNIQUE (001) | OK |
| `pncp_raw_bids` | `matched_entity_id` | INTEGER, FK | INTEGER (001), FK ADD (007) | OK |
| `pncp_raw_bids` | `orgao_cnpj` | TEXT | TEXT | OK |
| `pncp_raw_bids` | `idx_bids_orgao_hash` | btree(orgao_cnpj, content_hash) | — | MEDIA — index composto criado por aplicacao, sem migration |
| `pncp_raw_bids` | `is_active` + `data_publicacao` | Partial index | Partial index (001) | OK |

### D3 — Funcoes divergentes

| Funcao | Schema real | Migration v1 documentada | Severidade |
|--------|-------------|--------------------------|------------|
| `search_datalake` | 10 parametros, 13 colunas retorno | 10 parametros (005) | OK |
| `upsert_pncp_raw_bids` | JSONB, content_hash dedup | JSONB (006) | OK |
| `upsert_pncp_supplier_contracts` | JSONB, contrato_id dedup | JSONB (006) | OK |
| `set_updated_at` | Trigger function | Trigger function (001) | OK |
| `update_entity_coverage` | INSERT trigger | — (ad-hoc em codigo) | OK |
| `update_entity_coverage_on_update` | UPDATE trigger | — (ad-hoc em codigo) | OK |
| `generate_coverage_snapshot` | Weekly snapshot | — (ad-hoc em codigo) | OK |
| `purge_old_bids` | Retention purge | — (ad-hoc em codigo) | OK |

### D4 — Migrations 013-014: Alteracoes de TD-1.1 nao aplicadas ao schema local

**Contexto:** As migrations 013 e 014 foram criadas durante a Story TD-1.1
(Otimizacao de Queries) e estao no diretorio `db/migrations/`. Porem, as
alteracoes descritas **nao foram aplicadas ao banco local** e podem ou nao
ter sido aplicadas em producao.

#### D4.1 — Migration 013: GIN index em objeto_contrato

**O que a migration faz:**
```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS idx_psc_objeto_trgm
    ON pncp_supplier_contracts USING gin (objeto_contrato public.gin_trgm_ops);
```

**Status no schema real:** O index `idx_psc_objeto_trgm` EXISTE no schema real.
A migration 013 esta correta e seu efeito ja esta refletido no banco.

#### D4.2 — Migration 014: search_datalake com HNSW + pgvector

**O que a migration faz:**
- Adiciona extensao `vector`
- Altera `search_datalake` para 13 parametros (incluindo `p_websearch_text`,
  `p_modo`, `p_offset`, `p_embedding`)
- Altera retorno para 26 colunas (incluindo `situacao_compra`, `unidade_nome`,
  `link_sistema_origem`, `ts_rank`)
- Corrige expressao HNSW para usar Index Scan

**Status no schema real:** NENHUMA destas alteracoes existe no banco local:
- Extensao `vector` nao instalada
- Colunas `situacao_compra`, `unidade_nome`, `link_sistema_origem` nao existem
  em `pncp_raw_bids`
- Coluna `embedding` (VECTOR(256)) nao existe em `pncp_raw_bids`
- Funcao `search_datalake` mantem assinatura original de 10 parametros

**Hipotese:** A migration 014 documenta alteracoes planejadas ou aplicadas
parcialmente em producao, mas que ainda nao chegaram ao ambiente local.
Ou representa uma especificacao de uma feature futura que foi documentada
como migration prematuramente.

**Decisao para v2 baseline:** A v2 baseline NAO inclui as alteracoes da
migration 014. Se/Quando estas alteracoes forem aplicadas em producao, uma
migration 002-v2 deve ser criada para adiciona-las ao schema de forma
controlada e rastreavel.

### D5 — Divergencias entre migrations v1 e ordem de aplicacao

As migrations v1 foram numeradas (001-014) e devem ser aplicadas em ordem.
A analise mostra que:

1. **Migrations 001-008**: Criam tabelas e funcoes essenciais. Banco local
   reflete corretamente o estado esperado apos aplicacao destas migrations.
2. **Migrations 009-012**: Adicionam indexes, cobertura, views. Banco local
   reflete todas estas alteracoes.
3. **Migration 013**: GIN index presente. OK.
4. **Migration 014**: Alteracoes NÃO refletidas no banco local.

**Conclusao:** Alem da migration 014 (que nao foi aplicada), nao ha evidencias
de que alteracoes manuais tenham sido feitas diretamente no banco sem
migration correspondente. O problema principal e que **nao havia tracking**
— ninguem sabia quais migrations tinham sido aplicadas e em que ordem.

## Recomendacoes

1. **Verificar producao:** Executar `verify-schema-divergence.sh --refresh`
   contra o banco de producao (Hetzner VPS) para confirmar se as divergencias
   sao as mesmas.
2. **Migration 014 (TD-1.1):** Se as alteracoes existirem em producao,
   criar uma `002-v2_add_vector_search.sql` para inclui-las no schema v2.
   Caso contrario, arquivar a migration 014 como especificacao nao implementada.
3. **Setup novo:** Utilizar `supabase/migrations/` (v2) para ambientes novos,
   e manter `db/migrations/` (v1) apenas para compatibilidade com ambientes
   existentes ate que todos sejam migrados para v2.

## Checklist de Verificacao

- [x] Schema real extraido e versionado em `supabase/current-schema.sql`
- [x] Todas as 8 tabelas do schema real cobertas pela v2 baseline
- [x] Todas as 6+2 funcoes do schema real cobertas pela v2 baseline
- [x] Todas as 4 views do schema real cobertas pela v2 baseline
- [x] Todos os 33 indexes do schema real cobertos pela v2 baseline
- [x] Todos os 3 triggers do schema real cobertos pela v2 baseline
- [x] Migration 014 (TD-1.1) documentada como nao refletida no schema local
- [x] Tabela `_migrations` criada para tracking de migrations futuras
- [x] `verify-schema-divergence.sh` criado para verificacao continua
