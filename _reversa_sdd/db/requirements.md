# Requirements — Módulo `db`

> 🟢 CONFIRMADO — 12 migrations SQL, `db/seed/`, `db/setup_db.sh`

## Funcionais

| ID | Requisito | Fonte | Confiança |
|----|-----------|-------|-----------|
| FR-D1 | Schema multi-source unificado: `pncp_raw_bids` com FTS PT-BR (TSVECTOR + GIN) | `001_pncp_raw_bids.sql` | 🟢 |
| FR-D2 | Soft delete via `is_active` flag | `001:30` | 🟢 |
| FR-D3 | Upsert otimizado via RPC `upsert_pncp_raw_bids(jsonb)` | `006_upsert_rpcs.sql` | 🟢 |
| FR-D4 | Full-text search PT-BR via RPC `search_datalake(query, uf, dias, limite)` | `005_search_datalake_rpc.sql` | 🟢 |
| FR-D5 | Entity coverage tracking com trigger após upsert | `009_indexes_and_coverage.sql` | 🟢 |
| FR-D6 | Cascade matching logging (match_method, match_score, match_confidence) | `010_match_logging.sql` | 🟢 |
| FR-D7 | View `v_unmatched_bids` para debugging de unmatched | `011_unmatched_bids_view.sql` | 🟢 |
| FR-D8 | Coverage snapshots históricos | `012_coverage_snapshots.sql` | 🟢 |
| FR-D9 | Seed de 2.085 órgãos SC a partir de planilha Excel | `seed/001_sc_entities.py` | 🟢 |
| FR-D10 | Purge de registros >400 dias | `008_purge_rpc.sql` | 🟢 |

## MoSCoW

- **Must:** FR-D1, FR-D2, FR-D3, FR-D9
- **Should:** FR-D4, FR-D5, FR-D6, FR-D7, FR-D8, FR-D10
