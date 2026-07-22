-- ============================================================================
-- Migration 058: Dual capability coverage views + entity_coverage delimitation
-- ============================================================================
-- Campaign: DUAL-CAPABILITY-COVERAGE-TRUTH-01 / ADR-029
--
-- Does NOT introduce a third coverage architecture. Documents that
-- entity_coverage is non-canonical for dual gates, and exposes a helper view
-- for latest coverage_evidence rows used by dual_capability_coverage.py.
--
-- Idempotent: Yes
-- ============================================================================

BEGIN;

-- Delimit legacy entity_coverage purpose (non-canonical for dual gates).
COMMENT ON TABLE public.entity_coverage IS
    'LEGACY/DIAGNOSTIC entity×source admin coverage flags. '
    'NOT the authority for capability_monitoring_coverage(open_tenders|historical_contracts). '
    'Canonical dual coverage: scripts/coverage/dual_capability_coverage.py + coverage_evidence. '
    'Forbidden methods: treating any_row or undifferentiated is_covered as general coverage. ADR-029.';

COMMENT ON COLUMN public.entity_coverage.is_covered IS
    'LEGACY flag (e.g. publications in a window). NOT dual capability monitoring coverage. ADR-029.';

-- Latest evidence per entity/source/capability for dual scoring audits.
CREATE OR REPLACE VIEW public.v_dual_capability_evidence_latest AS
SELECT DISTINCT ON (
    entity_id,
    source,
    COALESCE(capability, data_type)
)
    id,
    entity_id,
    source,
    data_type,
    capability,
    applicability,
    applicability_reason,
    state,
    run_id,
    started_at,
    completed_at,
    pages_expected,
    pages_processed,
    count_obtained,
    count_transformed,
    count_persisted,
    queried_start,
    queried_end,
    freshness_status,
    error_code,
    error_message,
    metadata
FROM public.coverage_evidence
ORDER BY
    entity_id,
    source,
    COALESCE(capability, data_type),
    completed_at DESC NULLS LAST;

COMMENT ON VIEW public.v_dual_capability_evidence_latest IS
    'Latest coverage_evidence row per entity×source×capability for dual monitoring coverage audits. ADR-029.';

COMMIT;

-- Rollback:
-- DROP VIEW IF EXISTS public.v_dual_capability_evidence_latest;
-- (restore entity_coverage comments manually if required)
