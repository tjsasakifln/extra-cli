-- ============================================================================
-- Migration 039: Source Snapshot Tracking & Reconciliation Schema
-- ============================================================================
-- Story 1.4 (Reconcile Open Tenders) — Schema for snapshot reconciliation.
--
-- Adds tracking columns to opportunity_intel:
--   - source_active            BOOLEAN  (separated from ingestion is_active)
--   - source_inactive_at       TIMESTAMPTZ
--   - source_inactive_reason   TEXT
--   - last_seen_source_run_id  BIGINT
--   - last_status_verified_at  TIMESTAMPTZ
--   - last_status_verified_by  TEXT
--   - source_active_changes    JSONB    (history of activation/inactivation)
--
-- Creates source_snapshot_membership to persist every record ID seen
-- in each completed source run.
--
-- Creates fn_reconcile_source_snapshot() — the reconciliation function
-- that inactivates/activates records based on snapshot presence.
--
-- Dependencies: 027 (opportunity_intel), 029 (opportunity_runs extended)
-- Idempotent: YES
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. Tracking columns on opportunity_intel
-- ============================================================================

ALTER TABLE public.opportunity_intel
    ADD COLUMN IF NOT EXISTS source_active BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE public.opportunity_intel
    ADD COLUMN IF NOT EXISTS source_inactive_at TIMESTAMPTZ;

ALTER TABLE public.opportunity_intel
    ADD COLUMN IF NOT EXISTS source_inactive_reason TEXT;

ALTER TABLE public.opportunity_intel
    ADD COLUMN IF NOT EXISTS last_seen_source_run_id BIGINT;

ALTER TABLE public.opportunity_intel
    ADD COLUMN IF NOT EXISTS last_status_verified_at TIMESTAMPTZ;

ALTER TABLE public.opportunity_intel
    ADD COLUMN IF NOT EXISTS last_status_verified_by TEXT;

ALTER TABLE public.opportunity_intel
    ADD COLUMN IF NOT EXISTS source_active_changes JSONB NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN public.opportunity_intel.source_active IS
    'Separada de is_active (ingestao). source_active reflete se o registro foi visto no ultimo snapshot completo da fonte.';
COMMENT ON COLUMN public.opportunity_intel.source_inactive_at IS
    'Momento em que source_active foi alterado de TRUE para FALSE.';
COMMENT ON COLUMN public.opportunity_intel.source_inactive_reason IS
    'Razao da inativacao via snapshot. Ex: absent_from_complete_open_snapshot';
COMMENT ON COLUMN public.opportunity_intel.last_seen_source_run_id IS
    'ID da ultima opportunity_runs.execution que confirmou este registro.';
COMMENT ON COLUMN public.opportunity_intel.last_status_verified_at IS
    'Ultima verificacao de status contra a fonte de verdade.';
COMMENT ON COLUMN public.opportunity_intel.last_status_verified_by IS
    'Metodo que verificou: reconciliation_algorithm, manual_review, etc.';
COMMENT ON COLUMN public.opportunity_intel.source_active_changes IS
    'Historico de alteracoes de source_active como array JSONB.';

CREATE INDEX IF NOT EXISTS idx_oi_source_active
    ON public.opportunity_intel (source, source_active)
    WHERE source_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_oi_last_seen_source_run
    ON public.opportunity_intel (last_seen_source_run_id)
    WHERE last_seen_source_run_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_oi_last_status_verified
    ON public.opportunity_intel (source, last_status_verified_at DESC NULLS LAST)
    WHERE source_active = TRUE;

-- ============================================================================
-- 2. Source Snapshot Membership table
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.source_snapshot_membership (
    source_run_id               BIGINT NOT NULL REFERENCES public.opportunity_runs(id) ON DELETE CASCADE,
    source                      TEXT NOT NULL,
    scope_key                   TEXT,
    source_record_id            TEXT NOT NULL,
    canonical_opportunity_key   TEXT,
    seen_at                     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (source_run_id, source_record_id)
);

COMMENT ON TABLE public.source_snapshot_membership IS
    'Registra cada ID de registro visto em cada run completa de cada fonte. Usado para reconciliacao.';
COMMENT ON COLUMN public.source_snapshot_membership.source_run_id IS
    'FK para opportunity_runs.id — a execucao que capturou este registro.';
COMMENT ON COLUMN public.source_snapshot_membership.source IS
    'Nome canonico da fonte (ex: pncp).';
COMMENT ON COLUMN public.source_snapshot_membership.scope_key IS
    'Escopo dentro do run (ex: uf=SC;modalidade=1).';
COMMENT ON COLUMN public.source_snapshot_membership.source_record_id IS
    'ID unico do registro na fonte (ex: numero_controle_pncp).';
COMMENT ON COLUMN public.source_snapshot_membership.canonical_opportunity_key IS
    'Chave canonica da oportunidade (content_hash ou numero_controle_pncp).';

CREATE INDEX IF NOT EXISTS idx_ssm_source_run
    ON public.source_snapshot_membership (source_run_id);

CREATE INDEX IF NOT EXISTS idx_ssm_source_record
    ON public.source_snapshot_membership (source, source_record_id);

CREATE INDEX IF NOT EXISTS idx_ssm_canonical_key
    ON public.source_snapshot_membership (canonical_opportunity_key)
    WHERE canonical_opportunity_key IS NOT NULL;

-- ============================================================================
-- 3. Reconciliation function
-- ============================================================================

CREATE OR REPLACE FUNCTION fn_reconcile_source_snapshot(
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
    'Reconcilia opportunity_intel com o snapshot de uma run completa. Inativa ausentes, reativa reaparecidos. Story 1.4';

-- ============================================================================
-- 5. Update v_opportunity_open to filter by source_active=TRUE
-- ============================================================================
-- B2G-FIX-04: DROP first — CREATE OR REPLACE cannot change column list
DROP VIEW IF EXISTS v_opportunity_open;
CREATE OR REPLACE VIEW v_opportunity_open AS
SELECT
    oi.*,
    spe.razao_social AS orgao_razao_social,
    spe.municipio AS orgao_municipio,
    spe.distancia_fk AS distancia_florianopolis_km,
    spe.raio_200km
FROM opportunity_intel oi
LEFT JOIN sc_public_entities spe ON oi.orgao_cnpj = spe.cnpj_8
WHERE oi.status_canonico IN ('open', 'upcoming')
  AND oi.is_active = TRUE
  AND oi.source_active = TRUE;

-- ============================================================================
-- 6. Function to record memberships for a run
-- ============================================================================

CREATE OR REPLACE FUNCTION fn_record_snapshot_membership(
    p_source_run_id BIGINT,
    p_source TEXT DEFAULT 'pncp',
    p_records JSONB DEFAULT '[]'::jsonb
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
    WHERE id = p_source_run_id;

    v_scope_key := COALESCE(v_scope_key, 'default');
    v_run_source := COALESCE(v_run_source, p_source);

    FOR v_rec IN SELECT * FROM jsonb_array_elements(p_records)
    LOOP
        INSERT INTO public.source_snapshot_membership (
            source_run_id, source, scope_key,
            source_record_id, canonical_opportunity_key, seen_at
        ) VALUES (
            p_source_run_id,
            v_run_source,
            v_scope_key,
            COALESCE(v_rec->>'numero_controle_pncp', v_rec->>'source_id', v_rec->>'id', 'unknown'),
            COALESCE(v_rec->>'content_hash', v_rec->>'numero_controle_pncp'),
            NOW()
        )
        ON CONFLICT (source_run_id, source_record_id) DO NOTHING;
        v_count := v_count + 1;
    END LOOP;

    RETURN v_count;
END;
$$;

COMMENT ON FUNCTION public.fn_record_snapshot_membership IS
    'Registra os IDs vistos em um run na tabela de membership. Story 1.4';

-- ============================================================================
-- Rollback
-- ============================================================================
-- DROP FUNCTION IF EXISTS public.fn_reconcile_source_snapshot;
-- DROP FUNCTION IF EXISTS public.fn_record_snapshot_membership;
-- DROP TABLE IF EXISTS public.source_snapshot_membership;
-- ALTER TABLE public.opportunity_intel DROP COLUMN IF EXISTS source_active_changes;
-- ALTER TABLE public.opportunity_intel DROP COLUMN IF EXISTS last_status_verified_by;
-- ALTER TABLE public.opportunity_intel DROP COLUMN IF EXISTS last_status_verified_at;
-- ALTER TABLE public.opportunity_intel DROP COLUMN IF EXISTS last_seen_source_run_id;
-- ALTER TABLE public.opportunity_intel DROP COLUMN IF EXISTS source_inactive_reason;
-- ALTER TABLE public.opportunity_intel DROP COLUMN IF EXISTS source_inactive_at;
-- ALTER TABLE public.opportunity_intel DROP COLUMN IF EXISTS source_active;

COMMIT;
