-- ============================================================================
-- Migration 031: Source Snapshot Reconciliation
-- ============================================================================
-- Story 1.2 (Unify Schema) — Snapshot reconciliation logic
--
-- Adiciona mecanismos de reconciliacao de snapshots por fonte para garantir
-- que a cobertura de cada fonte seja rastreavel e auditavel.
--
-- Depende de: 030 (canonical views), coverage_snapshots, entity_coverage
-- Idempotente: Sim (IF NOT EXISTS)
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. Ensure coverage_snapshots has reconciliation columns
-- ============================================================================
ALTER TABLE public.coverage_snapshots
    ADD COLUMN IF NOT EXISTS source_reconciled BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE public.coverage_snapshots
    ADD COLUMN IF NOT EXISTS reconciliation_notes TEXT;

ALTER TABLE public.coverage_snapshots
    ADD COLUMN IF NOT EXISTS fingerprint TEXT;

COMMENT ON COLUMN public.coverage_snapshots.source_reconciled IS
    'Se este snapshot foi reconciliado contra a fonte de verdade';
COMMENT ON COLUMN public.coverage_snapshots.reconciliation_notes IS
    'Notas sobre a reconciliacao (gaps identificados, discrepancias)';
COMMENT ON COLUMN public.coverage_snapshots.fingerprint IS
    'SHA-256 do conjunto de dados do snapshot para verificacao de integridade';

-- Index for reconciled-by-source queries
CREATE INDEX IF NOT EXISTS idx_cov_snap_reconciled
    ON public.coverage_snapshots (source, source_reconciled)
    WHERE source_reconciled = TRUE;

-- ============================================================================
-- 2. Reconciliation summary function
-- ============================================================================
CREATE OR REPLACE FUNCTION public.fn_reconciliation_summary(
    p_source TEXT DEFAULT NULL,
    p_days INTEGER DEFAULT 30
)
RETURNS TABLE (
    source          TEXT,
    total_snapshots BIGINT,
    reconciled      BIGINT,
    last_snapshot   TIMESTAMPTZ,
    pct_reconciled  NUMERIC
) LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        cs.source,
        COUNT(*)::BIGINT AS total_snapshots,
        COUNT(*) FILTER (WHERE cs.source_reconciled)::BIGINT AS reconciled,
        MAX(cs.snapshot_date::TIMESTAMPTZ) AS last_snapshot,
        ROUND(
            100.0 * COUNT(*) FILTER (WHERE cs.source_reconciled) / GREATEST(COUNT(*), 1),
            1
        ) AS pct_reconciled
    FROM public.coverage_snapshots cs
    WHERE (p_source IS NULL OR cs.source = p_source)
      AND cs.snapshot_date >= CURRENT_DATE - p_days
    GROUP BY cs.source
    ORDER BY cs.source;
END;
$$;

COMMENT ON FUNCTION public.fn_reconciliation_summary IS
    'Summary of snapshot reconciliation per source. Story 1.2';

-- ============================================================================
-- Rollback SQL
-- ============================================================================
-- DROP FUNCTION IF EXISTS public.fn_reconciliation_summary;
-- ALTER TABLE public.coverage_snapshots DROP COLUMN IF EXISTS fingerprint;
-- ALTER TABLE public.coverage_snapshots DROP COLUMN IF EXISTS reconciliation_notes;
-- ALTER TABLE public.coverage_snapshots DROP COLUMN IF EXISTS source_reconciled;

COMMIT;
