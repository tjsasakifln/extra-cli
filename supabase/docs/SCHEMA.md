# Database Schema — Extra Consultoria

**Versão:** 3.0  
**Data:** 2026-07-17  
**Agente:** Dara (@data-engineer) — Brownfield Discovery Phase 2  
**Fonte de verdade desta revisão:**

| Fonte | Conteúdo | Data / escopo |
|-------|----------|---------------|
| `db/migrations/` (001–054) | Trilha **operacional** canônica | HEAD do repositório |
| `db/current-schema.sql` | Dump `pg_dump --schema-only` (PG 16.14) | 2026-07-14 — cobre ~001–042 |
| `db/current-schema.sha256` | Fingerprint SHA-256 | `85de867c…c7c6328` |
| `supabase/migrations/` (v2/v3) | Baseline consolidado histórico + 006-v3 | 001-v2…006-v3 |
| Código (`scripts/schema/*`, CLIs) | Contrato esperado pelos consumers | 2026-07-17 |

> **Schema derivado de migrations + dump + código.**  
> Em 2026-07-17 **não houve conexão ao banco ao vivo** (timeout em `127.0.0.1:54399` e `:5433`). Contagens de linhas **não** são inventadas.

---

## 1. Overview

| Aspecto | Valor |
|---------|-------|
| **Tecnologia** | PostgreSQL 16.x (dump 16.14 Debian; setup_db.sh aponta 16 como alvo Ubuntu 24.04) |
| **Database típico** | `pncp_datalake` (local Docker / planejado VPS) |
| **Propósito** | DataLake de licitações e contratos públicos (foco SC, raio 200 km de Florianópolis), matching de entes, coverage auditável, opportunity/contract intel |
| **Extensões** | `pg_trgm`, `uuid-ossp`, `vector` (pgvector — presente no dump; uso de embedding opcional) |
| **PostGIS** | **Não** presente no dump atual (histórico apenas) |
| **RLS** | Desligado (`row_security = off`); zero policies — single-user / service role |
| **Acesso** | `psycopg2` via `LOCAL_DATALAKE_DSN` / `DATABASE_URL` (`config/settings.py`) |
| **Pasta `supabase/`** | Guarda SQL docs/migrations de baseline; **não** implica produto Supabase Cloud obrigatório |

### Domínios de dados

| Domínio | Tabelas-chave | Views canônicas |
|---------|---------------|-----------------|
| **Entities / universo** | `sc_public_entities`, `enriched_entities`, `entity_hierarchy`, `entity_aliases`, `entity_source_registry`, `target_universe_*` | `v_entities_canonical`, `v_target_universe_active` |
| **Tenders / bids** | `pncp_raw_bids`, `pncp_enrichment_cache`, `pncp_backfill_*` | `v_open_opportunities_canonical`, `v_unmatched_bids` |
| **Contracts / suppliers** | `pncp_supplier_contracts`, `contract_version_history`, `official_acts*` | `v_contracts_canonical`, `v_suppliers_canonical`, `v_contract_*` |
| **Coverage / evidence** | `entity_coverage`, `coverage_evidence`, `coverage_snapshots`, `capability_coverage`, `source_applicability_rules` | `v_coverage_*`, `v_latest_evidence`, `v_source_health`, `v_coverage_manifest` |
| **Opportunity intel** | `opportunity_intel`, `opportunity_runs`, `opportunity_coverage`, `opportunity_checkpoints`, `source_snapshot_membership` | `v_opportunity_*` |
| **Ops / pipeline** | `ingestion_*`, `dlq_entries`, `pipeline_*`, `record_hashes`, `_migrations`, `retention_policy` | `v_migration_status`, `v_schema_integrity` |

---

## 2. Migration Tracks

O projeto mantém **duas trilhas** de SQL (dívida estrutural documentada em DT-18):

| Track | Diretório | Arquivos | Runner | Status 2026-07-17 |
|-------|-----------|----------|--------|-------------------|
| **Operacional (canônica)** | `db/migrations/` | 001…054 (59 arquivos) | `db/setup_db.sh` | **HEAD** — stories 1.2–1.5 + data-foundation + official acts |
| **Baseline v2/v3** | `supabase/migrations/` | `_migrations.sql`, `001-v2`…`006-v3` | `scripts/apply-migrations.sh` | Consolidação histórica; **não** substitui 030–054 |
| **v1 archived** | docs / `ARCHIVED.md` | antigas 001–014 | — | Arquivada (divergente) |

### Ledger

```sql
public._migrations (
  version TEXT PRIMARY KEY,
  name TEXT,
  applied_at TIMESTAMPTZ,
  checksum TEXT,
  rollback_sql TEXT  -- presente no track supabase; setup_db pode variar colunas
)
```

### Cadeia operacional resumida (db/migrations)

| Faixa | Tema | Stories / épicos |
|-------|------|------------------|
| 001–012 | Core: bids, contracts, entities, coverage, FTS, upserts | baseline |
| 013–022 | Índices, TTL, hierarchy, match_method | TD / coverage |
| 023–028 | Engineering ops, coverage_evidence, contract intel, opportunity_intel | intel |
| **029–036** | Views canônicas, capability_coverage, versioning, retention, reporting | **Story 1.2** |
| **037–038** | Target universe snapshot + views ativas | **Story 1.3** |
| **039–041b** | Snapshot membership + reconcile open tenders + FK cnpj_8 | **Story 1.4 / 1.2 fix** |
| **040, 042** | Coverage model expansion + validate FKs | **Story 1.5** |
| 043–044 | entity_aliases, dedup_cross_source, upsert dedup | CM-13 |
| 045–048 | DLQ, watermarks, pipeline_runs, record_hashes | DF-1B |
| 049–051 | PNCP backfill resumível, contracts upsert FK, date semantics | ops / pilot |
| 052–054 | official_acts, entity_source_registry, local resilience columns | ADR-021+ |

### supabase/migrations (v2/v3)

| Arquivo | Papel |
|---------|-------|
| `_migrations.sql` | Cria ledger |
| `001-v2_initial_schema.sql` | Baseline completo (dump 2026-07-11 era) |
| `002–005-v2` | entity_coverage, views, snapshots, match_logging |
| `006-v3-unified-schema.sql` | 10 tabelas + colunas + views opportunity/evidence (subset do que 021–028 fizeram em `db/`) |

**Nota:** Stories 1.2+ **escreveram em `db/migrations/`**, não em `supabase/migrations/`. Ambientes novos devem preferir `db/setup_db.sh`.

### Dump vs HEAD

| Camada | Tabelas | Views | Funções (aprox.) |
|--------|---------|-------|------------------|
| Dump `db/current-schema.sql` (2026-07-14) | **26** | **32** | **24** |
| Migrations 043–054 (somente SQL, pós-dump) | **+~16** | **+~2** (`v_official_acts_active`, `v_resolve_publishing_cnpj`) | +várias |
| **Total teórico HEAD** | **~42** | **~34** | **~30+** |

Objetos **no dump** (confirmados em 2026-07-14): ver §3.  
Objetos **apenas em migrations 043–054** (aplicação no ambiente local **não verificada** sem DB): ver §3.2.

---

## 3. Inventário de tabelas

### 3.1 Presentes no dump 2026-07-14 (26)

#### Domínio Entities

##### `sc_public_entities` — cadastro de entes públicos SC

| Coluna | Tipo | Constraints |
|--------|------|-------------|
| `id` | INTEGER | PK, sequence |
| `razao_social` | TEXT | NOT NULL |
| `cnpj_8` | TEXT | NOT NULL, **UNIQUE `uq_spe_cnpj_8`** (Story 1.2 / DT-06) |
| `municipio`, `codigo_ibge`, `natureza_juridica`, `cod_natureza` | TEXT | |
| `latitude`, `longitude`, `distancia_fk` | DOUBLE PRECISION | |
| `raio_200km` | BOOLEAN | NOT NULL DEFAULT FALSE |
| `is_active` | BOOLEAN | NOT NULL DEFAULT TRUE |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() |

Índices: `idx_spe_cnpj`, `idx_spe_ibge`, `idx_spe_municipio`, `idx_spe_natureza`, `idx_spe_raio`.

##### `enriched_entities` — cache BrasilAPI/etc.

PK `cnpj`; campos de CNAE, endereço, `enriched_at`, `enriched_source`.  
CHECKs (NOT VALID no dump): `chk_ee_cnpj_not_empty`, `chk_ee_enriched_at_not_future`, `chk_ee_enriched_source_not_empty`.

##### `entity_hierarchy` — hierarquia municipal

PK `entity_id` → `sc_public_entities`; `parent_entity_id` FK;  
`relationship` CHECK (`prefeitura|camara|autarquia|fundacao|fundo|conselho|outros`);  
`match_confidence` CHECK (`direct|hierarchical|inferred`).

##### `entity_coverage` — cobertura por ente × fonte

PK (`entity_id`, `source`); FK CASCADE → entities;  
`last_seen_at`, `total_bids`, `is_covered`, `within_200km`, `match_method`.

##### `target_universe_runs` / `target_universe_entities` — **autoridade do universo (Story 1.3)**

- **runs:** snapshot imutável (`seed_sha256`, `radius_km` default 200, contagens, `git_sha`).
- **entities:** PK (`universe_run_id`, `canonical_entity_key`); `radius_decision` ∈ included|excluded|unresolved; `duplicate_root`; `db_entity_id` opcional.

Queries analíticas devem usar `v_target_universe_active` (último run), **não** apenas `raio_200km`.

##### `source_applicability_rules` — matriz de aplicabilidade (Story 1.5)

Regras materializadas fonte × tipo de ente / esfera / capacidade.

##### `capability_coverage` — cobertura por capacidade de negócio (Story 1.2)

Rastreio granular por capacidade (ex.: open tenders, contracts, radar).

---

#### Domínio Tenders

##### `pncp_raw_bids` — licitações unificadas (multi-fonte)

| Coluna | Tipo | Notas |
|--------|------|-------|
| `pncp_id` | TEXT PK | ID canônico |
| `objeto_compra`, `valor_total_estimado` | TEXT / NUMERIC(18,2) | |
| `modalidade_id/nome`, `esfera_id` | INT/TEXT | `esfera_id` CHECK 1–4 ou NULL |
| `uf`, `municipio`, `codigo_municipio_ibge` | TEXT | |
| `orgao_razao_social`, `orgao_cnpj` | TEXT | CNPJ 14 dig |
| **`orgao_cnpj_8`** | TEXT GENERATED | `left(orgao_cnpj,8)` STORED — alvo FK |
| `data_publicacao/abertura/encerramento` | **DATE** | |
| `link_pncp`, `content_hash` (UNIQUE), `tsv` | | FTS |
| `source` DEFAULT `'pncp'`, `source_id` | | |
| `matched_entity_id` | INT FK SET NULL | |
| **`match_method`, `match_score`, `match_confidence`** | | Story match logging (DT-01) |
| `situacao_compra`, `unidade_nome`, `link_sistema_origem`, `crawl_batch_id` | | v3/eng |
| `numero_controle_pncp`, `ano_compra`, `sequencial_compra`, `informacao_complementar` | | |
| `synthetic_id`, `synthetic_id_reason` | | IDs sintéticos |
| `ingested_at`, `updated_at`, `is_active` | | soft-delete |

**FKs (dump):**  
- `fk_bids_matched_entity` → entities(id) ON DELETE SET NULL  
- `fk_bids_orgao_entity_v2` → entities(**cnpj_8**) via `orgao_cnpj_8` (041a)

**Triggers:** `trg_bids_updated_at`, `trg_bids_coverage`, `trg_bids_coverage_update`.

**Índices relevantes:** GIN `tsv`, GIN trigram `idx_bids_objeto_compra_gin` (partial `is_active`), UF+data, matched_entity partial, match_method, numero_controle, etc. (~15+).

##### `pncp_enrichment_cache`

PK/FK `pncp_id` → bids CASCADE; payloads JSONB detail/items/documents.

##### `engineering_opportunities`

Camada derivada (classificação engenharia + geo SC); UNIQUE `pncp_id` FK CASCADE.

---

#### Domínio Contracts / Suppliers

##### `pncp_supplier_contracts`

| Coluna | Tipo | Notas |
|--------|------|-------|
| `id` | SERIAL PK | |
| `contrato_id` | TEXT UNIQUE | |
| `orgao_*`, `fornecedor_*`, `objeto_contrato`, `valor_total` | | |
| `data_inicio`, `data_fim`, `data_publicacao` | DATE | 051 adiciona semântica `data_assinatura` etc. (pós-dump) |
| `orgao_cnpj_8`, `fornecedor_cnpj_8` | GENERATED | |
| `is_active` | BOOLEAN DEFAULT TRUE | soft-delete |
| `codigo_municipio_ibge`, `municipio_inferido` | | |

**FKs no dump 07-14:** `fk_contracts_orgao_entity_v2`, `fk_contracts_supplier_entity_v2` → `cnpj_8`.  
**Migration 050 (HEAD):** **DROP** dessas FKs de contracts — pilot nacional PNCP (~0% hit-rate no universo SC). Documentar estado real com `diagnostics.py` quando DB estiver up.

**Trigger:** `trg_contract_versioning` → `fn_capture_contract_snapshot()`.

##### `contract_version_history`

Histórico de mudanças em contracts (033).

##### `sc_municipalities` / `sc_dados_abertos_backfill_log`

Referência IBGE municipal + log de backfill de município.

---

#### Domínio Coverage / Evidence

##### `coverage_evidence` — ledger de evidência (024 + 040 Story 1.5)

| Coluna | Tipo | Notas |
|--------|------|-------|
| `id` | BIGSERIAL PK | |
| `entity_id` | INT NULL | NULL = agregado fonte |
| `source`, `data_type` DEFAULT `'bids'` | TEXT | |
| `queried_start/end` | DATE | janela consultada |
| `run_id` | TEXT NOT NULL | |
| `started_at`, `completed_at` | TIMESTAMPTZ | |
| `count_obtained/transformed/persisted` | INT | |
| `state` | **`evidence_state` enum** | ver §5 |
| `error_message`, `error_code`, `metadata` | | |
| **Story 1.5:** `canonical_entity_key`, `capability`, `applicability`, `applicability_reason`, `scope_key` | | |
| `pages_expected/processed`, `records_expected`, `records_fetched`, `open_records` | | |
| `freshness_status`, `checked_at`, `next_due_at`, `evidence_metadata` | | |
| **054 (pós-dump):** `request_scope`, `pages_fetched`, `provenance`, `satisfactory` | | se 054 aplicada |

Partial UNIQUE: `uq_ce_entity_run`, `uq_ce_source_aggregate_run`.  
CHECKs: `ck_ce_applicability`, `ck_ce_freshness_status`, `ck_ce_success_zero_scope` (NOT VALID no dump).

##### `coverage_snapshots`

Snapshots semanais (`generate_coverage_snapshot`).

---

#### Domínio Opportunity Intel

##### `opportunity_intel`

Oportunidade normalizada multi-fonte; UNIQUE `content_hash`; status/ranking CHECKs;  
**Story 1.4:** `source_active`, `source_inactive_at/reason`, `last_seen_source_run_id`, `last_status_verified_*`, `source_active_changes`.

##### `opportunity_runs` / `opportunity_checkpoints` / `opportunity_coverage`

Runs de coleta, checkpoints de crawler, cobertura por entidade×fonte.

##### `source_snapshot_membership`

Membership de registros em runs (reconcile Story 1.4); funções `fn_record_snapshot_membership`, `fn_reconcile_source_snapshot` (corrigidas em 041b).

---

#### Domínio Ops

| Tabela | Papel |
|--------|-------|
| `ingestion_runs` | Runs de ingestão genéricos |
| `ingestion_checkpoints` | Checkpoint crawler (pode estar pouco usado) |
| `retention_policy` | Políticas de retenção (035) |
| `_migrations` | Ledger |

---

### 3.2 Definidas em migrations 043–054 (pós-dump — status de aplicação **não verificado**)

| Migration | Tabelas |
|-----------|---------|
| 043 | `entity_aliases`, `dedup_cross_source` |
| 045 | `dlq_entries` (+ cols 054) |
| 046 | `pipeline_watermarks` |
| 047 | `pipeline_runs` |
| 048 | `record_hashes` |
| 049 | `pncp_backfill_runs`, `pncp_backfill_pages`, `pncp_backfill_records` |
| 052 | `official_act_resources`, `official_acts`, `official_act_classifications`, `official_act_links`, `official_act_source_links`, `official_act_matches` |
| 053 | `entity_source_registry` |
| 054 | ALTER em `dlq_entries` / `coverage_evidence` (não cria tabela nova) |

Detalhe de colunas: ler o SQL correspondente em `db/migrations/`.

---

## 4. Views — contrato canônico e operacionais

### 4.1 Views canônicas (Story 1.2 — migration 030) — **contrato estável**

Consumers Python devem preferir estas views a tabelas físicas quando possível.

| View | Propósito | Fontes principais |
|------|-----------|-------------------|
| `v_entities_canonical` | Entes SC + coverage PNCP | `sc_public_entities` ⟕ `entity_coverage` |
| `v_open_opportunities_canonical` | Licitações abertas/recentes + match | `pncp_raw_bids` ⟕ entities (filtro encerramento/publicação) |
| `v_contracts_canonical` | Contratos + entidade/enriched | `pncp_supplier_contracts` |
| `v_suppliers_canonical` | Fornecedores agregados | `enriched_entities` + contracts |
| `v_value_observations_canonical` | Observações de valor (bids+contracts) | bids ∪ contracts |

Contrato detalhado: `docs/stories/story-1.2-canonical-views-contract.md`.  
**049** recria `v_open_opportunities_canonical` após ALTER de tipos em bids.

### 4.2 Universe (Story 1.3)

| View | Propósito |
|------|-----------|
| `v_target_universe_active` | Entes do **último** snapshot com `radius_decision = included` |
| `v_target_universe_all` | Todos os entes do último snapshot |

### 4.3 Coverage / evidence

| View | Propósito |
|------|-----------|
| `v_coverage_gaps` | Entes sem cobertura |
| `v_coverage_gaps_by_municipio` | Gaps por município |
| `v_coverage_summary` | Sumário por fonte |
| `v_coverage_trend` | Evolução semanal |
| `v_coverage_health` | Dashboard health (036) |
| `v_coverage_manifest` | Manifest por capacidade (1.5) |
| `v_coverage_evidence_expanded` | Evidence expandida |
| `v_latest_evidence` | Último estado por (entity, source, data_type) |
| `v_source_health` | Saúde agregada por fonte |
| `v_hierarchical_coverage` | Cobertura herdada via hierarchy |
| `v_unmatched_bids` | Bids sem `matched_entity_id` |
| `v_entity_match_summary` | Sumário de matching |
| `v_capability_coverage_summary` | Capability coverage |

### 4.4 Opportunity

| View | Propósito |
|------|-----------|
| `v_opportunity_open` | Oportunidades open/upcoming |
| `v_opportunity_by_source` | Agregado source × status |
| `v_opportunity_coverage_summary` | Dashboard coverage opportunity |

### 4.5 Contract intel

| View | Propósito |
|------|-----------|
| `v_contract_historical` | Histórico 3 anos / raio |
| `v_supplier_winners` | Ranking vencedores |
| `v_expiring_contracts` | Expirando 90–180d |
| `v_contract_intel_*` | historico, fornecedores, ativos, percentis |

### 4.6 Meta / schema

| View | Propósito |
|------|-----------|
| `v_schema_integrity` | Checa objetos críticos (FKs, UNIQUE) |
| `v_migration_status` | Status do ledger |

### 4.7 Pós-dump (052+)

| View | Migration |
|------|-----------|
| `v_official_acts_active` | 052 |
| `v_resolve_publishing_cnpj` | 043/aliases |

**Total documentado:** 32 no dump + ~2 pós-dump ≈ **34 views**.

---

## 5. Enums e tipos

### `evidence_state` (enum)

Valores no dump 2026-07-14 (ordem real do catálogo pode variar por `ADD VALUE`):

```
running, success_with_data, success_zero, partial,
connection_failed, auth_failed, parse_failed, transform_failed, persist_failed,
not_applicable, not_investigated, success, error, pending, stale, blocked
```

- Base (024/v3): success_*, partial, *_failed, not_applicable, not_investigated  
- Story 1.5 (040): `pending`, `running`, `blocked`, `stale`  
- Aliases legados: `success`, `error`

---

## 6. Funções e triggers

### Funções (dump — 24)

| Função | Papel |
|--------|-------|
| `upsert_pncp_raw_bids(jsonb)` | **Set-based** CTE + INSERT ON CONFLICT (`pncp_id`) — retorna inserted/updated/unchanged |
| `upsert_pncp_supplier_contracts(jsonb)` | Set-based; 044/050: DISTINCT ON + fix ambiguidade OUT; FKs contracts removidas em 050 |
| `search_datalake(...)` | FTS + filtros; assinatura estendida (incl. `p_embedding vector` opcional) |
| `update_entity_coverage` / `_on_update` | Triggers coverage |
| `generate_coverage_snapshot` | Snapshot semanal |
| `purge_old_bids` / `purge_old_bids_hard` / `fn_purge_old_data` | Retenção |
| `ttl_cleanup_enriched_entities` | TTL cache |
| `upsert_opportunity_intel` | Batch opportunity |
| `upsert_qw01_pncp_opportunities` | Radar QW-01 |
| `fn_record_snapshot_membership` / `fn_reconcile_source_snapshot` / `fn_reconciliation_summary` | Story 1.4 |
| `fn_capture_contract_snapshot` | Versioning contracts |
| `fn_validate_coverage_evidence` | Validação evidence |
| `fn_value_statistics` | Stats valores |
| `fn_*_updated_at` / `set_updated_at` / `trg_oi_*` | Triggers de timestamp |

Pós-dump: `upsert_official_acts`, `upsert_official_act_resource`, `commit_watermark`, `get_last_watermark`, `resolve_publishing_cnpj_sql`, etc.

### Triggers (dump — 9)

| Trigger | Tabela | Evento |
|---------|--------|--------|
| `trg_bids_updated_at` | pncp_raw_bids | BEFORE UPDATE |
| `trg_bids_coverage` | pncp_raw_bids | AFTER INSERT |
| `trg_bids_coverage_update` | pncp_raw_bids | AFTER UPDATE OF matched_entity_id |
| `trg_entity_hierarchy_timestamp` | entity_hierarchy | BEFORE UPDATE |
| `trg_opportunity_intel_*` | opportunity_intel | BEFORE UPDATE |
| `trg_contract_versioning` | pncp_supplier_contracts | AFTER I/U/D |
| `trg_cap_coverage_updated_at` | capability_coverage | BEFORE UPDATE |
| `trg_applicability_updated_at` | source_applicability_rules | BEFORE UPDATE |

---

## 7. Foreign keys (dump)

| Constraint | De → Para | ON DELETE |
|------------|-----------|-----------|
| `entity_coverage_entity_id_fkey` | entity_coverage → entities | CASCADE |
| `fk_bids_matched_entity` | bids.matched_entity_id → entities | SET NULL |
| `fk_bids_orgao_entity_v2` | bids.orgao_cnpj_8 → entities.cnpj_8 | — |
| `fk_contracts_orgao_entity_v2` | contracts.orgao_cnpj_8 → entities | — (**DROP em 050**) |
| `fk_contracts_supplier_entity_v2` | contracts.fornecedor_cnpj_8 → entities | — (**DROP em 050**) |
| `entity_hierarchy_*_fkey` | hierarchy → entities | — |
| `pncp_enrichment_cache_pncp_id_fkey` | cache → bids | CASCADE |
| `engineering_opportunities_pncp_id_fkey` | eng → bids | CASCADE |
| `fk_oi_run_id` | opportunity_intel → runs | SET NULL |
| `opportunity_coverage_entity_id_fkey` | opp_coverage → entities | — |
| `fk_universe_run` | universe_entities → runs | CASCADE |
| `source_snapshot_membership_source_run_id_fkey` | membership → opportunity_runs | CASCADE |

Alguns CHECKs em `enriched_entities` / `coverage_evidence` permanecem **NOT VALID** no dump (validar com 042+).

---

## 8. Índices (resumo)

- **~122** índices no dump (CREATE INDEX / UNIQUE INDEX).
- Destaques de performance:
  - GIN FTS `idx_bids_tsv`
  - GIN trigram `idx_bids_objeto_compra_gin` (partial active) — resolve DT-11/TD-DB-06
  - GIN trigram contracts (`idx_psc_objeto_trgm` + partial `idx_psc_objeto_contrato_gin`)
  - Partial unique coverage_evidence
  - Partial unique opportunity_intel (pncp / processo+edital ativos)
  - Universe: `(universe_run_id)` + partial included

---

## 9. Scripts e tooling de schema

| Artefato | Função |
|----------|--------|
| `db/setup_db.sh` | Aplica **todas** `db/migrations/*.sql` com advisory lock + ledger |
| `scripts/apply-migrations.sh` | Aplica apenas `supabase/migrations/` (v2/v3) |
| `scripts/verify-schema-divergence.sh` | Diff schema esperado vs real |
| `scripts/schema/diagnostics.py` | Expected tables/views/functions vs live DB |
| `scripts/schema/audit_sql_references.py` | Extrai SQL embutido em Python vs KNOWN_* |
| `scripts/schema/official_acts.py` | Modelo official acts |
| `db/current-schema.sql` + `.sha256` | Baseline reproduzível (regenerar após 043–054) |

---

## 10. ERD textual (núcleo)

```
sc_public_entities (uq cnpj_8)
    │
    ├── entity_coverage (entity_id, source)
    ├── entity_hierarchy (entity_id → parent)
    ├── opportunity_coverage
    ├── pncp_raw_bids.matched_entity_id
    ├── pncp_raw_bids.orgao_cnpj_8 ──FK──► cnpj_8
    │         └── pncp_enrichment_cache
    │         └── engineering_opportunities
    │
target_universe_runs
    └── target_universe_entities (canonical_entity_key)
              ▲
              │ (lógico)
        coverage_evidence.canonical_entity_key

opportunity_runs
    ├── opportunity_intel (run_id, source_active…)
    └── source_snapshot_membership

pncp_supplier_contracts ──trigger──► contract_version_history
```

---

## 11. SQLite / fixtures

- `contract_intel` pode usar SQLite local com tabela `target_universe` simplificada.
- **Não** é fonte da verdade; PostgreSQL + seed snapshot (`target_universe_*`) é autoritativo (Story 1.3).

---

## 12. Path para VPS / Supabase self-hosted

1. Subir PostgreSQL 16 + extensões `pg_trgm`, `uuid-ossp`, `vector`.  
2. `LOCAL_DATALAKE_DSN=... bash db/setup_db.sh`  
3. Regenerar `db/current-schema.sql` + SHA-256.  
4. `python scripts/schema/diagnostics.py --dsn ...`  
5. RLS: só necessário se houver multi-tenant / API pública; hoje N/A.  
6. **Não** usar apenas `supabase/migrations/` — incompleto vs 030–054.

---

## 13. Como regenerar este documento

```bash
# Com DB disponível (somente leitura):
pg_dump --schema-only "$LOCAL_DATALAKE_DSN" > db/current-schema.sql
sha256sum db/current-schema.sql > db/current-schema.sha256
python scripts/schema/diagnostics.py --json
bash scripts/verify-schema-divergence.sh --dsn "$LOCAL_DATALAKE_DSN"
```

---

*SCHEMA.md v3.0 — 2026-07-17. Schema derived from migrations + `db/current-schema.sql` + code. Live row counts not available.*
