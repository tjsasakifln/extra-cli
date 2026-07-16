# Schema Divergence Audit — DATA-FOUNDATION
## Migrations vs current-schema.sql vs Live Database

*Generated: 2026-07-16*
*Auditor: @data-engineer (Dara)*
*Severity Assessment: CRITICAL*

---

## Executive Summary

This audit compares three sources of truth for the database schema:

1. **Reference file**: `db/current-schema.sql` (5,671 lines)
2. **Migrations in DB**: `_migrations` table (53 entries, 34 unique names)
3. **Live database**: 27 tables, 32 views, 178 functions, 9 triggers

### Key Finding

| Dimension | Status | Severity |
|-----------|--------|----------|
| Schema fingerprint (SHA-256) | **MISMATCH** | CRITICAL |
| current-schema.sql vs Live DB | **34 objects missing from DB** | HIGH |
| DB vs current-schema.sql | **2 objects not in reference** | MEDIUM |
| Missing migrations (029-044) | **16 files never applied** | HIGH |
| CONCURRENTLY index failures | **3 migrations structurally broken** | MEDIUM |

---

## 1. Schema Fingerprint

| Source | SHA-256 |
|--------|---------|
| `db/current-schema.sql` | `85de867c8549e70a4b6dfe10a766e7bbe5b7c49cf737826caa1dc2862c7c6328` |
| Live DB (pg_dump --schema-only) | `42f799b5899da1cc213a47c9592b5cf84b83a793a14016c2bf6ae4b1540c5731` |
| **Match?** | **NO** |

**Severity: CRITICAL** — The reference schema file does not represent the actual database. Any deployment or CI pipeline relying on `current-schema.sql` for diff/plan operations will produce incorrect results.

---

## 2. Migration Application Status

### 2.1 Overall Statistics

| Metric | Value |
|--------|-------|
| Migration files on disk | 44 (`db/migrations/001.sql` through `044_fix_upsert_dedup.sql`) |
| Unique migration names in `_migrations` table | 34 |
| Effectively applied | 23 |
| Effectively failed | 11 |
| Missing from `_migrations` table | 10 (029-038 + 041a, 041b, 042, 043, 044) |

### 2.2 Failed Migrations Detail

| File | Version | Error | Root Cause |
|------|---------|-------|------------|
| `017_td-2.3_matched_entity_id_index.sql` | 017 | "CREATE INDEX CONCURRENTLY cannot run inside a transaction block" | The migration uses CONCURRENTLY but was executed inside a transaction. This index was NEVER created. |
| `016_td-2.3_objeto_compra_gin.sql` | 016 | Same CONCURRENTLY issue | GIN index CONCURRENTLY inside transaction block. Index not created. |
| `013_td-1.1_gin_index_objeto_contrato.sql` | 013 | Same CONCURRENTLY issue | GIN index CONCURRENTLY inside transaction block. Index not created. |
| `001_pncp_raw_bids.sql` | v=1 | "relation pncp_raw_bids already exists" | Duplicate run (integer version batch) — actual migration did apply on first run. |
| `002-004`, `007`, `009` | v=2..9 | Same "already exists" pattern | Cosmetic failures from duplicate run. Objects exist. |
| `015_td-2.3_enriched_entities_ttl.sql` | v=15 | "constraint already exists" | Constraint was already created by a prior run. No harm. |

### 2.3 CONCURRENTLY Index Issue (Structural)

Three migrations attempt `CREATE INDEX CONCURRENTLY` which CANNOT run inside a PostgreSQL transaction block. The migrations are executed inside a transaction, so these indexes were silently skipped.

**Impact**: The following indexes are missing from the database despite being declared in migrations:

| Expected Index | Migration | Status |
|----------------|-----------|--------|
| `idx_pncp_raw_bids_objeto_contrato_gin` | 013 | MISSING from DB |
| `idx_pncp_raw_bids_objeto_compra_gin` | 016 | MISSING from DB |
| `idx_enriched_entities_matched_id` | 017 | MISSING from DB |

---

## 3. Missing Migrations (029-044)

**16 migration files exist on disk but have NO corresponding entry in the `_migrations` table** and were NEVER applied to the database:

| File | Expected To Create | Severity |
|------|--------------------|----------|
| `029_qw01_auditable_radar.sql` | `v_qw01_auditable_radar` view | HIGH |
| `030_schema_contract_and_canonical_views.sql` | `v_entities_canonical`, `v_suppliers_canonical`, `v_contracts_canonical`, etc. | HIGH |
| `031_source_snapshot_reconciliation.sql` | `source_snapshot_reconciliation` table | MEDIUM |
| `032_capability_coverage.sql` | `v_capability_coverage_summary` view | LOW (table exists) |
| `033_contract_versioning.sql` | `contract_version_history` table | LOW (table exists via other path) |
| `034_supplier_identity.sql` | `supplier_identity` table | HIGH |
| `035_value_observations.sql` | `v_value_observations_canonical` view, functions | MEDIUM |
| `036_reporting_views.sql` | Multiple reporting views | MEDIUM |
| `037_target_universe_snapshot.sql` | `target_universe_snapshot` table | HIGH |
| `038_target_universe_active_view.sql` | `v_target_universe_active`, `target_universe_active_view` | HIGH |
| `039_source_snapshot_tracking.sql` | `source_snapshot_tracking` table | MEDIUM |
| `040_coverage_model_expansion.sql` | Coverage model expansions | MEDIUM |
| `041a_fix_fk_constraints.sql` | FK constraint fixes | MEDIUM |
| `041b_fix_snapshot_membership.sql` | Snapshot membership fix | MEDIUM |
| `042_validate_fk_constraints.sql` | FK validation | MEDIUM |
| `043_entity_aliases.sql` | `entity_aliases` table | LOW (table exists via other path) |
| `044_fix_upsert_dedup.sql` | Upsert/dedup fixes | HIGH |

### Anomaly: Tables That Exist Despite Missing Migrations

Three tables (`capability_coverage`, `contract_version_history`, `entity_aliases`) exist in the database even though their creating migrations (032, 033, 043) were never applied. This suggests they were created by alternative means (manual SQL, other scripts, or the reverse-engineering process).

---

## 4. Objects in current-schema.sql But NOT in Live DB

**34 objects** are declared in `current-schema.sql` but do not exist in the live database:

### View-level Missing Objects (31 views)

| View | Likely Migration Dependency | Impact |
|------|-----------------------------|--------|
| `v_coverage_health` | 029 | Query failures |
| `v_qw01_auditable_radar` | 029 | Audit feature broken |
| `v_entities_canonical` | 030 | Entity queries may miss canonical form |
| `v_suppliers_canonical` | 030 | Supplier canonical view missing |
| `v_contracts_canonical` | 030 | Contract canonical view missing |
| `v_coverage_evidence_expanded` | 030 | Coverage analysis affected |
| `v_source_health` | 030 | Health monitoring blind |
| `v_migration_status` | 030 | Migration status check broken |
| `v_schema_integrity` | 030 | Schema validation view missing |
| `v_unmatched_bids` | 030 | Unmatched bid detection affected |
| `v_coverage_gaps` | 030 | Gap analysis blind |
| `v_coverage_gaps_by_municipio` | 030 | Municipal-level gaps unknown |
| `v_coverage_manifest` | 030 | Coverage manifest view missing |
| `v_coverage_trend` | 030 | Trend analysis broken |
| `v_coverage_summary` | 030 | Coverage summary queries affected |
| `v_latest_evidence` | 030 | Latest evidence view missing |
| `v_entity_match_summary` | 030 | Entity matching summary broken |
| `v_hierarchical_coverage` | 030 | Hierarchical coverage view missing |
| `v_contract_historical` | 033 | Contract history view missing |
| `v_contract_intel_ativos_90_180` | 033 | Contract intelligence view missing |
| `v_contract_intel_fornecedores` | 033 | Supplier intelligence view missing |
| `v_contract_intel_historico` | 033 | Contract history view missing |
| `v_contract_intel_percentis` | 033 | Contract percentile view missing |
| `v_expiring_contracts` | 033 | Expiring contract detection missing |
| `v_supplier_winners` | 033 | Supplier winners view missing |
| `v_capability_coverage_summary` | 032 | Capability coverage summary missing |
| `v_open_opportunities_canonical` | 027 | Opportunity canonical view missing |
| `v_opportunity_by_source` | 027 | Opportunity by-source view missing |
| `v_opportunity_coverage_summary` | 027 | Opportunity coverage summary missing |
| `v_opportunity_open` | 027 | Open opportunities view missing |
| `v_value_observations_canonical` | 035 | Value observation canonical view missing |
| `v_target_universe_all` | 038 | Full target universe view missing |

### Table-level Missing Objects (1 table)

| Table | Migration | Impact |
|-------|-----------|--------|
| `mv_entity_source_applicability` | Not tracked | Entity applicability features degraded |
| `opportunity_coverage` | Not tracked | Opportunity coverage analysis affected |

### Materialized View (1)

| Object | Impact |
|--------|--------|
| `mv_entity_source_applicability` | Missing from DB |

---

## 5. Objects in Live DB But NOT in current-schema.sql

| Object | Notes |
|--------|-------|
| `dedup_cross_source` | Table exists in DB but not in reference schema. Likely created by external process. |
| `entity_aliases` | Table exists in DB but not in reference schema. Possibly created manually. |

---

## 6. Reconciliation Plan

### 6.1 Critical (Must Fix Before Any Code Changes)

| # | Issue | Owner | Priority | Action |
|---|-------|-------|----------|--------|
| R1 | Schema fingerprint mismatch | @data-engineer | P0 | Regenerate `current-schema.sql` from live DB after reconciliation |
| R2 | Missing migration files 029-044 | @data-engineer | P0 | Apply migrations 029-044 in sequence, outside transaction block for CONCURRENTLY |
| R3 | 3 CONCURRENTLY indexes missing | @data-engineer | P0 | Run CREATE INDEX CONCURRENTLY manually outside transaction |P0

### 6.2 High (Feature-Blocking)

| # | Issue | Owner | Priority | Action |
|---|-------|-------|----------|--------|
| R4 | Canonical views (030) missing | @data-engineer | P1 | Apply migration 030 to create canonical views |
| R5 | Audit view (029) missing | @data-engineer | P1 | Apply migration 029 |
| R6 | Target universe views (037-038) missing | @data-engineer | P1 | Apply migrations 037-038 |
| R7 | Supplier identity table (034) missing | @data-engineer | P1 | Apply migration 034 |

### 6.3 Medium (Non-Blocking But Recommended)

| # | Issue | Owner | Priority | Action |
|---|-------|-------|----------|--------|
| R8 | Value observations (035) missing | @data-engineer | P2 | Apply migration 035 |
| R9 | Reporting views (036) missing | @data-engineer | P2 | Apply migration 036 |
| R10 | Source snapshot tables (039) | @data-engineer | P2 | Apply migration 039 |
| R11 | Coverage model expansion (040) | @data-engineer | P2 | Apply migration 040 |
| R12 | FK constraint fixes (041a, 041b, 042) | @data-engineer | P2 | Apply migrations 041-042 |
| R13 | Upsert/dedup fixes (044) | @data-engineer | P2 | Apply migration 044 |

### 6.4 Cosmetic (Duplicate Run Cleanup)

| # | Issue | Owner | Priority | Action |
|---|-------|-------|----------|--------|
| R14 | Duplicate entries in `_migrations` (v=1..9) | @data-engineer | P3 | Clean up duplicate entries; keep only the successful versioned entries |
| R15 | `entity_aliases` and `dedup_cross_source` orphan tables | @data-engineer | P3 | Either add to `current-schema.sql` or document their origin |

---

## 7. Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Schema-ledger desync leads to broken queries | HIGH | HIGH | Apply missing migrations before W1 starts |
| CONCURRENTLY index missing causes slow queries | MEDIUM | MEDIUM | Create indexes manually; include in reconciliation |
| Duplicate _migrations entries confuse future tooling | MEDIUM | LOW | Cleanup is cosmetic — dedup on name in query |
| current-schema.sql as authoritative source is untrustworthy | HIGH | HIGH | Regenerate after reconciliation from live DB |

---

## 8. Appendix: Migration Traceability Matrix

| File | On Disk | In `_migrations` | In DB (objects) | Status |
|------|---------|------------------|-----------------|--------|
| 001-012 | YES | YES (duplicate) | YES | APPLIED (with warnings) |
| 013-014 | YES | YES | PARTIAL | CONCURRENTLY FAIL on 013 |
| 015 | YES | YES | YES | APPLIED |
| 016 | YES | YES | NO | CONCURRENTLY FAIL |
| 017 | YES | YES | NO | CONCURRENTLY FAIL |
| 018-td-5.3 | YES | YES | YES | APPLIED |
| 019-td-5.3 | YES | YES | YES | APPLIED |
| 020-028 | YES | YES | YES | APPLIED |
| 029-044 | YES | **NO** | **NO** | **NEVER APPLIED** |

---

*Report generated by `pg_dump --schema-only` + manual audit. Schema fingerprint: 42f799b5 (live) vs 85de867c (reference).*
