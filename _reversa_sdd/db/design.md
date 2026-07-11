# Design — Módulo `db`

> 🟢 CONFIRMADO — 12 migrations

## Schema (8 tabelas, 3 RPCs, 1 view)

```
pncp_raw_bids (central)
  ├── PK: pncp_id (TEXT)
  ├── UNIQUE: content_hash (SHA-256)
  ├── FK: matched_entity_id → sc_public_entities.id
  ├── FTS: tsv TSVECTOR (GIN index, PT-BR)
  └── 12 índices B-tree

pncp_supplier_contracts → histórico de contratos
enriched_entities → cache BrasilAPI/IBGE (TTL 30 dias)
sc_public_entities → 2.085 órgãos SC
entity_coverage → tracking (entity_id, source) UNIQUE
ingestion_runs → auditoria de crawls
ingestion_checkpoints → crawl resumable (JSONB cursor)
coverage_snapshots → snapshots históricos

RPCs:
  upsert_pncp_raw_bids(jsonb) → batch upsert
  search_datalake(query, uf, dias, limite) → FTS
  purge_old_records() → limpeza >400 dias

Views:
  v_unmatched_bids → bids sem match para debugging
```

## Migrations (12, sequenciais)

001 → core bids + FTS → 002 supplier contracts → 003 enriched entities → 004 ingestion tracking → 005 search RPC → 006 upsert RPCs → 007 SC entities → 008 purge RPC → 009 coverage + indexes → 010 match logging → 011 unmatched view → 012 coverage snapshots

## Trigger: set_updated_at()

```sql
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```
