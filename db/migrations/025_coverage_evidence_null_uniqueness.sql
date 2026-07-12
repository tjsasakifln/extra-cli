-- Migration 025: Coverage Evidence — NULL uniqueness + completeness metadata
-- Fixes the NULL entity_id uniqueness gap in migration 024.
-- NULL != NULL in SQL, so the UNIQUE constraint on (entity_id, source, data_type, run_id)
-- allowed duplicate source-level aggregate rows.
--
-- This migration:
--   1. Drops the old UNIQUE constraint that doesn't work for NULL entity_id.
--   2. Adds two partial unique indexes that correctly enforce:
--      a. One entity-level row per (entity_id, source, data_type, run_id).
--      b. One source-level aggregate row per (source, data_type, run_id).
--   3. Adds a CHECK constraint requiring success_zero rows to carry
--      query-scope proof in metadata (queried_start + queried_end OR
--      a 'completeness' key).
--
-- Idempotent: all DDL uses IF NOT EXISTS / IF EXISTS. Safe to re-run.

BEGIN;

-- ---------------------------------------------------------------------------
-- Step 1: Drop old UNIQUE constraint (does not work for NULL entity_id)
-- ---------------------------------------------------------------------------

-- The constraint was created inline in CREATE TABLE. We must find and drop it.
-- PostgreSQL auto-names it; we locate it dynamically.
DO $$
DECLARE
    _constraint_name TEXT;
BEGIN
    SELECT conname INTO _constraint_name
    FROM pg_constraint
    WHERE conrelid = 'coverage_evidence'::regclass
      AND contype = 'u'
      AND array_length(conkey, 1) = 4
      AND conkey = ARRAY[
          (SELECT attnum FROM pg_attribute WHERE attrelid = 'coverage_evidence'::regclass AND attname = 'entity_id'),
          (SELECT attnum FROM pg_attribute WHERE attrelid = 'coverage_evidence'::regclass AND attname = 'source'),
          (SELECT attnum FROM pg_attribute WHERE attrelid = 'coverage_evidence'::regclass AND attname = 'data_type'),
          (SELECT attnum FROM pg_attribute WHERE attrelid = 'coverage_evidence'::regclass AND attname = 'run_id')
      ];

    IF _constraint_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE coverage_evidence DROP CONSTRAINT %I', _constraint_name);
        RAISE NOTICE 'Dropped unique constraint: %', _constraint_name;
    ELSE
        RAISE NOTICE 'No old unique constraint found — already migrated.';
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- Step 2: Partial unique indexes that correctly handle NULL entity_id
-- ---------------------------------------------------------------------------

-- Entity-level uniqueness: one row per entity+source+data_type+run_id
CREATE UNIQUE INDEX IF NOT EXISTS uq_ce_entity_run
    ON coverage_evidence (entity_id, source, data_type, run_id)
    WHERE entity_id IS NOT NULL;

-- Source-level aggregate uniqueness: exactly one aggregate row per run
CREATE UNIQUE INDEX IF NOT EXISTS uq_ce_source_aggregate_run
    ON coverage_evidence (source, data_type, run_id)
    WHERE entity_id IS NULL;

-- ---------------------------------------------------------------------------
-- Step 3: Completeness metadata CHECK for success_zero rows
-- ---------------------------------------------------------------------------
-- success_zero MUST carry proof that the query scope was fully covered.
-- Accept: (queried_start, queried_end) both non-NULL, OR
--          metadata->>'completeness' exists with a recognised value.

DO $$ BEGIN
    ALTER TABLE coverage_evidence ADD CONSTRAINT ck_success_zero_completeness
        CHECK (
            state != 'success_zero'
            OR (queried_start IS NOT NULL AND queried_end IS NOT NULL)
            OR (metadata ? 'completeness')
        );
EXCEPTION
    WHEN duplicate_object THEN
        RAISE NOTICE 'Constraint ck_success_zero_completeness already exists.';
END $$;

-- ---------------------------------------------------------------------------
-- Step 4: Recreate v_latest_evidence view (to pick up any column changes)
-- ---------------------------------------------------------------------------

DROP VIEW IF EXISTS v_source_health;
DROP VIEW IF EXISTS v_latest_evidence;

CREATE OR REPLACE VIEW v_latest_evidence AS
SELECT DISTINCT ON (entity_id, source, data_type)
    id,
    entity_id,
    source,
    data_type,
    queried_start,
    queried_end,
    run_id,
    started_at,
    completed_at,
    count_obtained,
    count_transformed,
    count_persisted,
    state,
    error_message,
    error_code,
    metadata
FROM coverage_evidence
ORDER BY entity_id, source, data_type, completed_at DESC;

-- v_source_health: per-source aggregates from latest evidence rows.
-- Filters to entity-level rows only (entity_id IS NOT NULL) for entity coverage;
-- source-level aggregates (entity_id IS NULL) contribute run-level health.
CREATE OR REPLACE VIEW v_source_health AS
SELECT
    source,
    COUNT(*) FILTER (WHERE entity_id IS NOT NULL) AS total_entity_rows,
    COUNT(*) FILTER (WHERE entity_id IS NULL)     AS total_aggregate_rows,
    COUNT(*) FILTER (WHERE entity_id IS NOT NULL AND state = 'success_with_data') AS success_with_data,
    COUNT(*) FILTER (WHERE entity_id IS NOT NULL AND state = 'success_zero')      AS success_zero,
    COUNT(*) FILTER (WHERE entity_id IS NOT NULL AND state = 'partial')           AS partial,
    COUNT(*) FILTER (WHERE entity_id IS NOT NULL AND state = 'connection_failed') AS connection_failed,
    COUNT(*) FILTER (WHERE entity_id IS NOT NULL AND state = 'auth_failed')       AS auth_failed,
    COUNT(*) FILTER (WHERE entity_id IS NOT NULL AND state = 'parse_failed')      AS parse_failed,
    COUNT(*) FILTER (WHERE entity_id IS NOT NULL AND state = 'transform_failed')  AS transform_failed,
    COUNT(*) FILTER (WHERE entity_id IS NOT NULL AND state = 'persist_failed')    AS persist_failed,
    COUNT(*) FILTER (WHERE entity_id IS NOT NULL AND state = 'not_applicable')    AS not_applicable,
    COUNT(*) FILTER (WHERE entity_id IS NOT NULL AND state = 'not_investigated')  AS not_investigated,
    MAX(completed_at) AS last_check_at
FROM v_latest_evidence
GROUP BY source
ORDER BY source;

COMMIT;
