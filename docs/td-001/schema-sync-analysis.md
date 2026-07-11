# Schema Sync Analysis — TD-2.4

**Data:** 2026-07-11
**Context:** Story TD-2.4 — Sincronizar Schema do DataLake Local com Migrations
**Analise de divergencia entre `db/migrations/` e `supabase/migrations/` versus banco local.

## Descobertas

O banco local (postgresql://postgres:smartlic_local@127.0.0.1:54399/postgres) apresenta
um schema hibrido que nao corresponde integralmente a nenhuma das duas arvores de migrations.

### Tabelas Existentes

| Tabela | Status | Observacao |
|--------|--------|------------|
| sc_public_entities | OK | Corresponde ao baseline v2 |
| enriched_entities | OK | Corresponde ao baseline v2 |
| pncp_raw_bids | Parcial | TEM `setor_classificado`, `embedding` (nao v2); FALTA `matched_entity_id`, `match_method`, `match_score`, `match_confidence` |
| pncp_supplier_contracts | OK | Corresponde ao baseline v2 |
| ingestion_runs | Schema v2 | Usa colunas v2: `crawl_batch_id`, `run_type`, `completed_at`, `total_fetched`, `inserted`, `updated`, `unchanged`, `errors`, `ufs_completed`, `ufs_failed`, `duration_s`, `metadata`. FALTA `source` |
| ingestion_checkpoints | Schema v2 + TD-2.4 | Usa colunas v2: `uf`, `modalidade_id`, `crawl_batch_id`, `status`, `error_message`, `started_at`, `completed_at`. FALTA `scope_key`, `last_id`, `updated_at` (adicionados por TD-2.4) |
| entity_coverage | **AUSENTE** | Criada por TD-2.4 |

### Tabelas Ausentes

| Tabela | Prevista em | Status |
|--------|-------------|--------|
| entity_coverage | v1 009, v2 002-v2 | **CRIADA** |
| coverage_snapshots | v1 012, v2 004-v2 | Nao criada (out of scope) |

### Views

| View | Prevista em | Status |
|------|-------------|--------|
| v_coverage_summary | v1 009, v2 003-v2 | **CRIADA** |
| v_coverage_gaps_by_municipio | v1 012 | **CRIADA** |
| v_coverage_gaps | v1 012 | Nao criada (out of scope — v_coverage_gaps_by_municipio atende) |
| v_coverage_trend | v1 012 | Nao criada (out of scope) |
| v_unmatched_bids | v2 003-v2 | Nao criada (depende de match_logging 005-v2) |

### Discrepancias Criticas (Nao Corrigidas)

| Item | Impacto | Responsavel |
|------|---------|-------------|
| `pncp_raw_bids.matched_entity_id` ausente | Triggers de cobertura (trg_bids_coverage) NAO foram vinculados — runtime error evitado | TD-3.x (matching pipeline) |
| `pncp_raw_bids.match_method/score/confidence` ausentes | Monitor.py _match_entities_cascade nao funciona | TD-3.x |
| `coverage_snapshots` ausente | generate_coverage_snapshot() e v_coverage_trend nao disponiveis | Story futura |
| Duas arvores de migrations nao reconciliadas | Risco de novo schema drift | TD-7.1 (proposta) |

## Decisoes

1. **Schema v2 como referencia**: O banco local segue o schema v2 (supabase/migrations/001-v2)
   para tabelas existentes. A migration 020 adapta-se a este schema, nao ao v1 de db/migrations/.

2. **Triggers condicionais**: Os triggers trg_bids_coverage e trg_bids_coverage_update so
   serao vinculados quando a coluna `matched_entity_id` existir em `pncp_raw_bids`. Isto
   evita runtime error em INSERT/UPDATE enquanto o matching pipeline nao estiver operacional.

3. **Checkpoint sync API**: A tabela ingestion_checkpoints recebeu colunas extras (scope_key,
   last_id, updated_at) para suportar a sync API de checkpoint.py com PK (source, scope_key),
   mantendo as colunas v2 existentes.

4. **Registro de migracao**: A migration 020 registra-se em `_migrations` se a tabela existir.

## Recomendacao

Unificar as duas arvores de migrations em uma unica sequencia (proposta TD-7.1) para
eliminar o risco de schema drift permanente. A recomunicacao deve definir:
- Qual arvore e a fonte da verdade (provavelmente supabase/migrations/ por ser v2)
- Como migrar db/migrations/ restantes para o formato v2
- Estrategia de validacao continua de schema
