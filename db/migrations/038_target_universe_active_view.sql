-- Migration 038: Target Universe Active View
--
-- Creates the v_target_universe_active view that resolves "current entity set"
-- through the latest snapshot instead of the raio_200km column.
--
-- All analytic queries should JOIN with this view instead of filtering
-- by sc_public_entities.raio_200km directly.
--
-- Design:
--   - Idempotent (CREATE OR REPLACE VIEW)
--   - Latest snapshot is determined by MAX(target_universe_runs.id)
--   - LEFT JOIN preserves entities even if snapshot is missing (graceful deg.)
--   - Supercedes the within_200km column for universe membership decisions
--
-- References:
--   Story 1.3: Universe Authority — Task 4 (migration) + Task 7/8 (queries)

BEGIN;

-- ============================================================================
-- v_target_universe_active — Entities in the latest snapshot
-- ============================================================================
CREATE OR REPLACE VIEW public.v_target_universe_active AS
WITH latest_run AS (
    SELECT id, seed_sha256, radius_km, created_at
    FROM target_universe_runs
    ORDER BY id DESC
    LIMIT 1
)
SELECT
    tue.universe_run_id,
    tue.canonical_entity_key,
    tue.seed_row,
    tue.cnpj8,
    tue.legal_name,
    tue.municipality,
    tue.ibge_code,
    tue.legal_nature,
    tue.latitude,
    tue.longitude,
    tue.distance_km,
    tue.radius_decision,
    tue.duplicate_root,
    tue.db_entity_id,
    tue.match_method,
    lr.seed_sha256,
    lr.radius_km           AS snapshot_radius_km,
    lr.created_at           AS snapshot_created_at,
    spe.id                  AS db_entity_id_original,
    spe.razao_social        AS db_razao_social,
    spe.municipio           AS db_municipio,
    spe.raio_200km          AS db_within_200km,
    spe.is_active           AS db_is_active
FROM target_universe_entities tue
CROSS JOIN latest_run lr
LEFT JOIN sc_public_entities spe ON spe.id = tue.db_entity_id
WHERE tue.universe_run_id = lr.id
  AND tue.radius_decision = 'included';

COMMENT ON VIEW public.v_target_universe_active IS
    'Active target universe entities from the latest snapshot. '
    'Replaces WHERE raio_200km filtering for analytic queries. Story 1.3';

COMMENT ON COLUMN public.v_target_universe_active.universe_run_id IS
    'Snapshot run ID — connect query results to a specific seed version';
COMMENT ON COLUMN public.v_target_universe_active.radius_decision IS
    'included | excluded | unresolved — from seed resolution';
COMMENT ON COLUMN public.v_target_universe_active.db_within_200km IS
    'Diagnostic: what the DB raio_200km column says (may diverge from seed)';
COMMENT ON COLUMN public.v_target_universe_active.db_entity_id_original IS
    'sc_public_entities.id for legacy joins (NULL if entity not in DB)';

-- ============================================================================
-- v_target_universe_all — All entities in the latest snapshot (incl. excluded)
-- ============================================================================
CREATE OR REPLACE VIEW public.v_target_universe_all AS
WITH latest_run AS (
    SELECT id, seed_sha256, radius_km, created_at
    FROM target_universe_runs
    ORDER BY id DESC
    LIMIT 1
)
SELECT
    tue.universe_run_id,
    tue.canonical_entity_key,
    tue.seed_row,
    tue.cnpj8,
    tue.legal_name,
    tue.municipality,
    tue.ibge_code,
    tue.legal_nature,
    tue.latitude,
    tue.longitude,
    tue.distance_km,
    tue.radius_decision,
    tue.duplicate_root,
    tue.db_entity_id,
    tue.match_method,
    lr.seed_sha256,
    lr.radius_km           AS snapshot_radius_km,
    lr.created_at           AS snapshot_created_at
FROM target_universe_entities tue
CROSS JOIN latest_run lr
WHERE tue.universe_run_id = lr.id;

COMMENT ON VIEW public.v_target_universe_all IS
    'All target universe entities (included + excluded + unresolved) from latest snapshot. '
    'Use for diagnostic reports and divergence analysis. Story 1.3';

COMMIT;
