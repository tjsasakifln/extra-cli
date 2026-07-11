# Database — Tasks

> Gerado pelo Writer em 2026-07-11T22:30:00Z | doc_level: completo

| # | Tarefa | Fonte | Critério de Pronto | Confiança |
|---|--------|-------|-------------------|-----------|
| T-D01 | Criar tabela `sc_public_entities`: 13 colunas, 5 índices, seed 2.085 entes | `migration 007` | Haversine distance, raio_200km | 🟢 |
| T-D02 | Criar tabela `pncp_raw_bids`: 31 colunas, 10+ índices, FTS português | `migration 001` | Multi-source unified schema | 🟢 |
| T-D03 | Criar tabela `pncp_supplier_contracts`: 18 colunas, 6 índices, GIN trgm | `migration 002` | ~3.69M registros | 🟢 |
| T-D04 | Criar tabela `enriched_entities`: entity_type+entity_id PK, JSONB data | `schema real` | Cache BrasilAPI/IBGE, 90d TTL | 🟢 |
| T-D05 | Criar tabela `entity_coverage`: PK (entity_id, source), 90d window | `migration 009` | Atualizada via triggers | 🟢 |
| T-D06 | Criar tabelas `ingestion_checkpoints` + `ingestion_runs` | `migration 004` | Audit trail + resume support | 🟢 |
| T-D07 | Criar tabela `coverage_snapshots` + view `v_coverage_trend` | `migration 012` | LAG para tendência semanal | 🟢 |
| T-D08 | Implementar `upsert_pncp_raw_bids(JSONB)` + `upsert_pncp_supplier_contracts(JSONB)` | `migration 006` | ON CONFLICT content_hash/contrato_id DO NOTHING | 🟢 |
| T-D09 | Implementar `search_datalake(10 params)`: FTS + ILIKE fallback | `migration 005` | TABLE(13 cols), ts_rank + ILIKE | 🟢 |
| T-D10 | Implementar triggers coverage: AFTER INSERT + AFTER UPDATE | `migration 009` | entity_coverage atualizado automaticamente | 🟢 |
| T-D11 | Implementar `purge_old_bids(400)` + `purge_old_bids_hard(90)` | `migrations 008, 019` | Soft-delete + hard-delete em 2 fases | 🟢 |
| T-D12 | Implementar `ttl_cleanup_enriched_entities(90)` | `migration 015` | DELETE expired cache | 🟢 |
| T-D13 | Implementar `generate_coverage_snapshot(DATE)` | `migration 012` | Snapshots por source | 🟢 |
| T-D14 | Criar seed script: import XLSX → 2.085 entes + Haversine + IBGE resolve | `seed_sc_entities.py:1-770` | 4 estratégias IBGE, cache JSON | 🟢 |
| T-D15 | Criar backup script: pg_dump custom + gzip + Storage Box + retention 7+4 | `backup-database.sh` | systemd timer diário 06:00 UTC | 🟢 |

**Estimativa:** 5-7 dias (15 tarefas)
