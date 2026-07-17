-- ============================================================================
-- Rollback for Migration 052: Unified Official Acts
-- ============================================================================
-- DESTRUCTIVE: drops all official_acts* objects and data.
-- Safe only when no production crawlers depend on these tables yet,
-- or after an explicit backup / export.
--
-- Usage:
--   psql "$LOCAL_DATALAKE_DSN" -f db/rollback/052_official_acts_rollback.sql
--
-- Non-destructive alternative: leave tables in place and stop writers.
-- ============================================================================

BEGIN;

DROP VIEW IF EXISTS public.v_official_acts_active;

DROP FUNCTION IF EXISTS public.upsert_official_acts(JSONB);

-- Drop overload by signature (matches CREATE OR REPLACE in 052)
DROP FUNCTION IF EXISTS public.upsert_official_act_resource(
    TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
    TIMESTAMPTZ, BIGINT, TEXT, TEXT, JSONB
);

DROP TRIGGER IF EXISTS trg_oa_updated_at ON public.official_acts;
DROP TRIGGER IF EXISTS trg_oar_updated_at ON public.official_act_resources;
DROP FUNCTION IF EXISTS public.fn_official_acts_touch_updated_at();

DROP TABLE IF EXISTS public.official_act_matches CASCADE;
DROP TABLE IF EXISTS public.official_act_source_links CASCADE;
DROP TABLE IF EXISTS public.official_act_links CASCADE;
DROP TABLE IF EXISTS public.official_act_classifications CASCADE;
DROP TABLE IF EXISTS public.official_acts CASCADE;
DROP TABLE IF EXISTS public.official_act_resources CASCADE;

COMMIT;
