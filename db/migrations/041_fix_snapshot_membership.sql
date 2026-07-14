-- ============================================================================
-- Migration 041: Fix Snapshot Membership — align SQL with Python payload keys
-- ============================================================================
-- CRITICAL BUG FIX: The original fn_record_snapshot_membership in migration
-- 039 expected raw records with keys like 'numero_controle_pncp' in the JSONB
-- input, but the Python code in reconciliation.py._record_memberships sends
-- records with keys 'source_record_id' and 'canonical_opportunity_key'.
--
-- This caused every source_record_id to be inserted as 'unknown' and every
-- canonical_opportunity_key as NULL, which in turn made reconciliation
-- (fn_reconcile_source_snapshot) unable to match records — it would inactivate
-- ALL active records on the next completed run.
--
-- Fixes:
--   1. Recreates fn_record_snapshot_membership to read the actual keys
--      sent by the Python code (source_record_id, canonical_opportunity_key).
--   2. Defensively recreates fn_reconcile_source_snapshot to ensure it
--      matches the current schema (same body as migration 039).
--
-- Idempotent: YES (CREATE OR REPLACE)
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. Fix fn_record_snapshot_membership — accept the keys Python actually sends
-- ============================================================================

CREATE OR REPLACE FUNCTION public.fn_record_snapshot_membership(
    p_run_id INTEGER,
    p_source_name TEXT,
    p_records_json JSONB
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_rec JSONB;
    v_count BIGINT := 0;
    v_scope_key TEXT;
    v_run_source TEXT;
BEGIN
    -- Resolve scope_key and source from the run itself
    SELECT scope_key, source INTO v_scope_key, v_run_source
    FROM public.opportunity_runs
    WHERE id = p_run_id;

    v_scope_key := COALESCE(v_scope_key, 'default');
    v_run_source := COALESCE(v_run_source, p_source_name);

    FOR v_rec IN SELECT * FROM jsonb_array_elements(p_records_json)
    LOOP
        INSERT INTO public.source_snapshot_membership (
            source_run_id, source, scope_key,
            source_record_id, canonical_opportunity_key, seen_at
        ) VALUES (
            p_run_id,
            v_run_source,
            v_scope_key,
            -- Python sends records with keys 'source_record_id' and
            -- 'canonical_opportunity_key' (reconciliation.py _record_memberships)
            COALESCE(v_rec->>'source_record_id', 'unknown'),
            v_rec->>'canonical_opportunity_key',
            NOW()
        )
        ON CONFLICT (source_run_id, source_record_id) DO NOTHING;

        v_count := v_count + 1;
    END LOOP;

    RETURN v_count;
END;
$$;

COMMENT ON FUNCTION public.fn_record_snapshot_membership IS
    'Registra os IDs processados (ja extraidos pelo Python) na tabela de membership. Migration 041 fix.';

-- ============================================================================
-- 2. Defensively recreate fn_reconcile_source_snapshot (same body as 039)
-- ============================================================================

CREATE OR REPLACE FUNCTION public.fn_reconcile_source_snapshot(
    p_source_run_id BIGINT,
    p_source TEXT DEFAULT 'pncp'
)
RETURNS TABLE(
    action TEXT,
    record_id BIGINT,
    content_hash TEXT,
    reason TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_run RECORD;
    v_active_before INTEGER;
    v_inactivated INTEGER;
    v_reactivated INTEGER;
    v_skipped BOOLEAN;
    v_skip_reason TEXT;
BEGIN
    -- 1) Load the run — halt if not found
    SELECT * INTO v_run
    FROM public.opportunity_runs
    WHERE id = p_source_run_id;

    IF NOT FOUND THEN
        RETURN QUERY SELECT 'SKIPPED'::TEXT, NULL::BIGINT, NULL::TEXT,
            format('Run %s not found', p_source_run_id)::TEXT;
        RETURN;
    END IF;

    -- 2) Protection: NEVER reconcile partial, failed, or limited runs
    v_skipped := FALSE;
    v_skip_reason := NULL;

    IF v_run.status NOT IN ('completed', 'completed_zero') THEN
        v_skipped := TRUE;
        v_skip_reason := format(
            'Run %s status is %s — reconciliation requires completed or completed_zero',
            p_source_run_id, v_run.status
        );
    ELSIF v_run.scope_complete IS DISTINCT FROM TRUE THEN
        v_skipped := TRUE;
        v_skip_reason := format(
            'Run %s scope_complete = FALSE — reconciliation requires full pagination',
            p_source_run_id
        );
    ELSIF v_run.metadata->>'stopped_by_record_limit' = 'true'
       OR v_run.metadata->>'stopped_by_max_pages' = 'true' THEN
        v_skipped := TRUE;
        v_skip_reason := format(
            'Run %s was limited (record or page cap) — reconciliation blocked',
            p_source_run_id
        );
    END IF;

    IF v_skipped THEN
        RETURN QUERY SELECT 'SKIPPED'::TEXT, NULL::BIGINT, NULL::TEXT, v_skip_reason;
        RETURN;
    END IF;

    -- Count active before
    SELECT COUNT(*) INTO v_active_before
    FROM public.opportunity_intel
    WHERE source = p_source AND source_active = TRUE;

    -- 3) Inactivate records not seen in this run
    WITH inactivated AS (
        UPDATE public.opportunity_intel oi
        SET source_active = FALSE,
            source_inactive_at = NOW(),
            source_inactive_reason = 'absent_from_complete_open_snapshot',
            source_active_changes = oi.source_active_changes || jsonb_build_array(
                jsonb_build_object(
                    'changed_at', NOW(),
                    'from', TRUE,
                    'to', FALSE,
                    'reason', 'absent_from_complete_open_snapshot',
                    'source_run_id', p_source_run_id
                )
            )
        FROM public.opportunity_intel oi_current
        WHERE oi.id = oi_current.id
          AND oi.source = p_source
          AND oi.source_active = TRUE
          AND oi.is_active = TRUE
          AND NOT EXISTS (
              SELECT 1
              FROM public.source_snapshot_membership ssm
              WHERE ssm.source_run_id = p_source_run_id
                AND ssm.canonical_opportunity_key = oi.numero_controle_pncp
          )
          AND NOT EXISTS (
              SELECT 1
              FROM public.source_snapshot_membership ssm2
              WHERE ssm2.source_run_id = p_source_run_id
                AND ssm2.source_record_id = oi.source_id
          )
        RETURNING oi.id, oi.content_hash, oi.numero_controle_pncp
    )
    SELECT COUNT(*) INTO v_inactivated FROM inactivated;

    -- 4) Reactivate records that reappeared
    WITH reactivated AS (
        UPDATE public.opportunity_intel oi
        SET source_active = TRUE,
            source_inactive_at = NULL,
            source_inactive_reason = NULL,
            last_seen_source_run_id = p_source_run_id,
            last_status_verified_at = NOW(),
            last_status_verified_by = 'reconciliation_algorithm',
            source_active_changes = oi.source_active_changes || jsonb_build_array(
                jsonb_build_object(
                    'changed_at', NOW(),
                    'from', FALSE,
                    'to', TRUE,
                    'reason', 'reappeared_in_snapshot',
                    'source_run_id', p_source_run_id
                )
            )
        WHERE oi.source = p_source
          AND oi.source_active = FALSE
          AND oi.is_active = TRUE
          AND (
              EXISTS (
                  SELECT 1
                  FROM public.source_snapshot_membership ssm
                  WHERE ssm.source_run_id = p_source_run_id
                    AND ssm.canonical_opportunity_key = oi.numero_controle_pncp
              )
              OR
              EXISTS (
                  SELECT 1
                  FROM public.source_snapshot_membership ssm2
                  WHERE ssm2.source_run_id = p_source_run_id
                    AND ssm2.source_record_id = oi.source_id
              )
          )
        RETURNING oi.id, oi.content_hash, oi.numero_controle_pncp
    )
    SELECT COUNT(*) INTO v_reactivated FROM reactivated;

    -- 5) Update last_seen_source_run_id and verified_at for records that
    --    are already source_active=TRUE and were seen in this run
    UPDATE public.opportunity_intel oi
    SET last_seen_source_run_id = p_source_run_id,
        last_status_verified_at = NOW(),
        last_status_verified_by = 'reconciliation_algorithm'
    WHERE oi.source = p_source
      AND oi.source_active = TRUE
      AND oi.is_active = TRUE
      AND (
          EXISTS (
              SELECT 1
              FROM public.source_snapshot_membership ssm
              WHERE ssm.source_run_id = p_source_run_id
                AND ssm.canonical_opportunity_key = oi.numero_controle_pncp
          )
          OR
          EXISTS (
              SELECT 1
              FROM public.source_snapshot_membership ssm2
              WHERE ssm2.source_run_id = p_source_run_id
                AND ssm2.source_record_id = oi.source_id
          )
      );

    -- Return summary
    RETURN QUERY
    SELECT 'RECONCILIATION_SUMMARY'::TEXT,
           v_active_before::BIGINT,
           v_inactivated::TEXT,
           v_reactivated::TEXT;
END;
$$;

COMMENT ON FUNCTION public.fn_reconcile_source_snapshot IS
    'Reconcilia opportunity_intel com o snapshot de uma run completa. Migration 041 (recreate from 039).';

-- ============================================================================
-- Rollback
-- ============================================================================
-- DROP FUNCTION IF EXISTS public.fn_record_snapshot_membership(INTEGER, TEXT, JSONB);
-- DROP FUNCTION IF EXISTS public.fn_reconcile_source_snapshot(BIGINT, TEXT);

COMMIT;
