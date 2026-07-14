-- ============================================================================
-- Migration 036: Reporting Views
-- ============================================================================
-- Story 1.2 (Unify Schema) — Final reporting views
--
-- Views de reporting que dependem de todas as migrations anteriores (030-035).
-- Inclui views para:
--   1. Coverage health dashboard
--   2. Schema integrity check
--   3. Migration status
--   4. Canonical entity match summary
--
-- Depende de: 030-035 (todas as views e tabelas anteriores)
-- Idempotente: Sim (OR REPLACE)
-- ============================================================================

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

-- ============================================================================
-- 1. Coverage health dashboard view
-- ============================================================================
CREATE OR REPLACE VIEW public.v_coverage_health AS
SELECT
    ec.source,
    COUNT(*)::INTEGER AS total_entities,
    COUNT(*) FILTER (WHERE ec.is_covered)::INTEGER AS covered,
    ROUND(100.0 * COUNT(*) FILTER (WHERE ec.is_covered) / GREATEST(COUNT(*), 1), 1) AS pct_covered,
    COUNT(*) FILTER (WHERE ec.within_200km AND ec.is_covered)::INTEGER AS covered_200km,
    COUNT(*) FILTER (WHERE ec.within_200km)::INTEGER AS total_200km,
    ROUND(100.0 * COUNT(*) FILTER (WHERE ec.within_200km AND ec.is_covered) / GREATEST(COUNT(*) FILTER (WHERE ec.within_200km), 1), 1) AS pct_200km,
    MAX(ec.last_seen_at)::DATE AS last_coverage_date,
    NOW()::DATE - MAX(ec.last_seen_at)::DATE AS days_since_last_coverage
FROM public.entity_coverage ec
GROUP BY ec.source
ORDER BY ec.source;

COMMENT ON VIEW public.v_coverage_health IS
    'Coverage health per source. Story 1.2';

-- ============================================================================
-- 2. Schema integrity check view
-- ============================================================================
CREATE OR REPLACE VIEW public.v_schema_integrity AS
SELECT
    'tables'::TEXT AS check_type,
    COUNT(*)::INTEGER AS total_expected,
    COUNT(*) FILTER (WHERE EXISTS (
        SELECT 1 FROM information_schema.tables t
        WHERE t.table_schema = 'public'
        AND t.table_name = o.object_name
    ))::INTEGER AS present,
    COUNT(*) FILTER (WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.tables t
        WHERE t.table_schema = 'public'
        AND t.table_name = o.object_name
    ))::INTEGER AS missing
FROM (VALUES
    ('pncp_raw_bids'), ('pncp_supplier_contracts'), ('sc_public_entities'),
    ('enriched_entities'), ('entity_coverage'), ('entity_hierarchy'),
    ('coverage_snapshots'), ('coverage_evidence'), ('opportunity_intel'),
    ('ingestion_runs'), ('ingestion_checkpoints')
) AS o(object_name)

UNION ALL

SELECT
    'views'::TEXT AS check_type,
    COUNT(*)::INTEGER,
    COUNT(*) FILTER (WHERE EXISTS (
        SELECT 1 FROM information_schema.views v
        WHERE v.table_schema = 'public'
        AND v.table_name = o.object_name
    ))::INTEGER,
    COUNT(*) FILTER (WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.views v
        WHERE v.table_schema = 'public'
        AND v.table_name = o.object_name
    ))::INTEGER
FROM (VALUES
    ('v_entities_canonical'), ('v_open_opportunities_canonical'),
    ('v_contracts_canonical'), ('v_suppliers_canonical'),
    ('v_value_observations_canonical'), ('v_latest_evidence'),
    ('v_source_health'), ('v_coverage_health'),
    ('v_schema_integrity'), ('v_capability_coverage_summary')
) AS o(object_name)

UNION ALL

SELECT
    'fk_constraints'::TEXT,
    COUNT(*)::INTEGER,
    COUNT(*) FILTER (WHERE EXISTS (
        SELECT 1 FROM pg_constraint c
        JOIN pg_class cl ON c.conrelid = cl.oid
        WHERE c.conname = o.object_name
    ))::INTEGER,
    COUNT(*) FILTER (WHERE NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        JOIN pg_class cl ON c.conrelid = cl.oid
        WHERE c.conname = o.object_name
    ))::INTEGER
FROM (VALUES
    ('fk_bids_orgao_entity'), ('fk_contracts_supplier_entity'),
    ('fk_contracts_orgao_entity'), ('uq_spe_cnpj_8'),
    ('uq_oi_content_hash')
) AS o(object_name);

COMMENT ON VIEW public.v_schema_integrity IS
    'Schema integrity check — tables, views, constraints expected vs actual. Story 1.2';

-- ============================================================================
-- 3. Migration status view
-- ============================================================================
CREATE OR REPLACE VIEW public.v_migration_status AS
SELECT
    version,
    name,
    applied_at,
    checksum,
    CASE
        WHEN rollback_sql IS NOT NULL THEN 'reversible'
        ELSE 'irreversible'
    END AS reversibility,
    CASE
        WHEN checksum IS NOT NULL THEN 'verified'
        ELSE 'unverified'
    END AS integrity_status
FROM public._migrations
ORDER BY version::INTEGER;

COMMENT ON VIEW public.v_migration_status IS
    'Migration tracking status. Story 1.2';

-- ============================================================================
-- 4. Entity match summary view
-- ============================================================================
CREATE OR REPLACE VIEW public.v_entity_match_summary AS
SELECT
    b.match_method,
    COUNT(*)::INTEGER AS total_bids,
    COUNT(*) FILTER (WHERE b.matched_entity_id IS NOT NULL)::INTEGER AS matched,
    ROUND(100.0 * COUNT(*) FILTER (WHERE b.matched_entity_id IS NOT NULL) / GREATEST(COUNT(*), 1), 1) AS pct_matched,
    MIN(b.match_score) AS min_score,
    MAX(b.match_score) AS max_score,
    ROUND(AVG(b.match_score)::NUMERIC, 3) AS avg_score,
    COUNT(DISTINCT b.matched_entity_id)::INTEGER AS distinct_entities
FROM public.pncp_raw_bids b
WHERE b.match_method IS NOT NULL
GROUP BY b.match_method
ORDER BY b.match_method;

COMMENT ON VIEW public.v_entity_match_summary IS
    'Entity match performance by method. Story 1.2';

-- ============================================================================
-- Rollback SQL
-- ============================================================================
-- DROP VIEW IF EXISTS public.v_entity_match_summary;
-- DROP VIEW IF EXISTS public.v_migration_status;
-- DROP VIEW IF EXISTS public.v_schema_integrity;
-- DROP VIEW IF EXISTS public.v_coverage_health;

COMMIT;
