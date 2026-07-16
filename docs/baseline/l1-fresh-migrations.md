# PE-L1-01 — Fresh migrations no HEAD (evidência real)

**Story:** PE-L1-01  
**Executado em:** 2026-07-16T19:11:04-03:00 → 2026-07-16T19:11:35-03:00  
**Commit HEAD:** `1f7aa7c`  
**Runner:** `bash db/setup_db.sh <DSN>`  
**Migrations no HEAD:** **54** arquivos em `db/migrations/*.sql`

## Veredito

| Cenário | Imagem | Resultado | Applied | Failed | Exit |
|---------|--------|-----------|---------|--------|------|
| A — compose default | `postgis/postgis:16-3.4` (`:5433`, DB `pe_l1_fresh`) | **BLOCKED** | 13 | 1 (`014`) | 1 |
| B — workaround pgvector | `pgvector/pgvector:pg16` (`:54397`, DB `pe_l1_fresh`) | **BLOCKED** (quase completo) | 53 | 1 (`049`) | 1 |

**Não há evidência de fresh install exit 0 com todas as 54 migrations no HEAD.**  
Sucesso total **não** foi inventado.

---

## Cenário A — `docker compose` do repositório

### Setup

```bash
docker compose up -d test-db
PGPASSWORD=test psql -h 127.0.0.1 -p 5433 -U test -d postgres \
  -c "CREATE DATABASE pe_l1_fresh OWNER test TEMPLATE template_postgis;"
# CREATE EXTENSION vector → ERROR: extension "vector" is not available
bash db/setup_db.sh 'postgresql://test:test@127.0.0.1:5433/pe_l1_fresh'
```

### Resultado

- Log: `db/log/migration-20260716_191104.log`
- Summary: **Applied: 13 / Failed: 1 / Total: 54**
- Primeira falha: `014_td-1.1_fix_hnsw_expression`

```text
ERROR:  extension "vector" is not available
DETAIL:  Could not open extension control file
  "/usr/share/postgresql/16/extension/vector.control": No such file or directory.
```

**Causa raiz:** imagem `postgis/postgis:16-3.4` não inclui pgvector; `setup_db.sh` e migration 014 exigem `vector`.

Migrations aplicadas com sucesso antes da falha: `001` … `013`.

---

## Cenário B — fresh DB com `pgvector/pgvector:pg16`

### Setup

```bash
docker run -d --name pe-l1-pgvector \
  -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=pe_l1_fresh \
  -p 54397:5432 pgvector/pgvector:pg16

PGPASSWORD=test psql -h 127.0.0.1 -p 54397 -U test -d pe_l1_fresh -c \
  "CREATE EXTENSION IF NOT EXISTS vector;
   CREATE EXTENSION IF NOT EXISTS pg_trgm;
   CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";"

bash db/setup_db.sh 'postgresql://test:test@127.0.0.1:54397/pe_l1_fresh'
```

### Resultado

- Log: `db/log/migration-20260716_191121.log`
- Summary: **Applied: 53 / Failed: 1 / Total: 54**
- Falha: `049_pncp_resumable_backfill`

```text
psql:.../049_pncp_resumable_backfill.sql:24: ERROR:
  cannot alter type of a column used by a view or rule
DETAIL: rule _RETURN on view v_open_opportunities_canonical depends on column "esfera_id"
```

Trecho problemático (migration 049):

```sql
ALTER TABLE public.pncp_raw_bids
    ALTER COLUMN esfera_id TYPE TEXT USING esfera_id::TEXT,
    ALTER COLUMN data_publicacao TYPE TIMESTAMPTZ USING data_publicacao::TIMESTAMPTZ,
    ALTER COLUMN data_abertura TYPE TIMESTAMPTZ USING data_abertura::TIMESTAMPTZ,
    ALTER COLUMN data_encerramento TYPE TIMESTAMPTZ USING data_encerramento::TIMESTAMPTZ;
```

**Causa raiz:** views criadas em migrations anteriores (ex.: `030_schema_contract_and_canonical_views` → `v_open_opportunities_canonical`) dependem de `esfera_id`; 049 tenta `ALTER TYPE` sem dropar/recriar views dependentes.

Seed (`db/seed/001_sc_entities.py`) **não** rodou (setup aborta no fail de migration).

### Tabelas presentes após cenário B (32)

```text
_migrations, capability_coverage, contract_version_history, coverage_evidence,
coverage_snapshots, dedup_cross_source, dlq_entries, engineering_opportunities,
enriched_entities, entity_aliases, entity_coverage, entity_hierarchy,
ingestion_checkpoints, ingestion_runs, opportunity_checkpoints, opportunity_coverage,
opportunity_intel, opportunity_runs, pipeline_runs, pipeline_watermarks,
pncp_enrichment_cache, pncp_raw_bids, pncp_supplier_contracts, record_hashes,
retention_policy, sc_dados_abertos_backfill_log, sc_municipalities, sc_public_entities,
source_applicability_rules, source_snapshot_membership, target_universe_entities,
target_universe_runs
```

### Checklist de tabelas críticas

| Tabela | Presente no fresh B? | Notas |
|--------|----------------------|-------|
| `_migrations` | YES | Ledger com rows applied + failed |
| `pncp_raw_bids` | YES | |
| `pncp_supplier_contracts` | YES | |
| `enriched_entities` | YES | |
| `sc_public_entities` | YES | |
| `entity_coverage` | YES | |
| `coverage_evidence` | YES | |
| `coverage_snapshots` | YES | |
| `opportunity_intel` | YES | |
| `target_universe_entities` | YES | vazia (sem import de seed) |
| `target_universe_runs` | YES | |
| `capability_coverage` | YES | |
| `source_snapshot_membership` | YES | |
| `entity_aliases` | YES | |
| `dlq_entries` | YES | |
| `pipeline_runs` | YES | |
| `pipeline_watermarks` | YES | |
| `record_hashes` | YES | |
| `pncp_backfill_runs` | **NO** | criada só na 049 |
| `pncp_backfill_pages` | **NO** | criada só na 049 |
| `pncp_backfill_records` | **NO** | criada só na 049 |

---

## DB existente `pncp_datalake` (não é fresh)

Não substitui AC de fresh install. Snapshot honesto:

- Ledger **sujo** (chaves duplicadas/legadas `1` vs `001`, status `failed` misturado com objetos já criados).
- 28 tabelas; faltam objetos de migrations tardias (`pipeline_*`, `record_hashes`, `pncp_backfill_*`).
- Dados parciais: bids 343; universo em tabela = 0.

---

## Blockers abertos (para L1/L2)

1. **Alinhar imagem Docker** ao requisito de `vector` (`pgvector` ou imagem custom PostGIS+pgvector).
2. **Corrigir migration 049** para alterar tipos com dependências de view (DROP VIEW → ALTER → CREATE VIEW, ou evitar type change se já compatível).
3. **Limpar ledger** de ambientes half-applied se forem reutilizados.
4. Até (1)+(2), **fresh install exit 0 no HEAD permanece BLOCKED**.

## Como reproduzir

```bash
# Cenário A (esperado: fail 014)
docker compose up -d test-db
bash db/setup_db.sh 'postgresql://test:test@127.0.0.1:5433/<db_limpo>'

# Cenário B (esperado: fail 049)
docker run -d --name pe-l1-pgvector -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test \
  -e POSTGRES_DB=pe_l1_fresh -p 54397:5432 pgvector/pgvector:pg16
bash db/setup_db.sh 'postgresql://test:test@127.0.0.1:54397/pe_l1_fresh'
```
