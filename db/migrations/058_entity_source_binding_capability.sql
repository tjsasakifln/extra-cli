-- ============================================================================
-- Migration 058: Entity Source Binding with capability (Option A)
-- ============================================================================
-- Purpose: Capability-aware entity↔source bindings for freshness and coverage.
-- Distinguishes at least notices_or_bids vs contracts per entity-source pair.
--
-- Decision (ENTITY-FRESHNESS-01 Architecture/Data Squad): Option A —
-- capability column on binding with UNIQUE (canonical_id, source_id, capability).
-- Smaller than redesigning entity_source_registry (053); preserves history;
-- allows multiple capabilities per entity-source without event bus.
--
-- Dependencies: 053_entity_source_registry (soft — no hard FK to allow seed-first)
-- Rollback: DROP TABLE IF EXISTS public.entity_source_binding;
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS public.entity_source_binding (
    id                      BIGSERIAL PRIMARY KEY,

    -- Identity (canonical_id aligns with entity_source_registry)
    canonical_id            TEXT NOT NULL,
    source_id               TEXT NOT NULL,
    capability              TEXT NOT NULL
                            CHECK (capability IN (
                                'notices_or_bids',
                                'contracts'
                            )),

    -- Applicability / access
    applicability           TEXT NOT NULL DEFAULT 'unknown'
                            CHECK (applicability IN (
                                'applicable',
                                'not_applicable',
                                'unknown'
                            )),
    acquisition_method      TEXT NOT NULL DEFAULT 'unknown'
                            CHECK (acquisition_method IN (
                                'api', 'html', 'pdf', 'ckan', 'manual', 'none', 'unknown'
                            )),
    portal_url              TEXT,
    external_org_id         TEXT,
    confidence              DOUBLE PRECISION NOT NULL DEFAULT 0.0
                            CHECK (confidence >= 0.0 AND confidence <= 1.0),

    -- Operational / freshness denormalized hints (source of truth is evidence)
    status                  TEXT NOT NULL DEFAULT 'active'
                            CHECK (status IN (
                                'active', 'blocked', 'deprecated'
                            )),
    last_attempt_at         TIMESTAMPTZ,
    last_success_at         TIMESTAMPTZ,
    last_verified_at        TIMESTAMPTZ,
    current_blocker         TEXT,
    next_action             TEXT NOT NULL DEFAULT 'review_binding',
    evidence_ref            TEXT,
    notes                   TEXT,

    -- Audit
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_entity_source_binding_cap
        UNIQUE (canonical_id, source_id, capability)
);

CREATE INDEX IF NOT EXISTS idx_esb_canonical
    ON public.entity_source_binding (canonical_id);

CREATE INDEX IF NOT EXISTS idx_esb_source
    ON public.entity_source_binding (source_id);

CREATE INDEX IF NOT EXISTS idx_esb_capability
    ON public.entity_source_binding (capability);

CREATE INDEX IF NOT EXISTS idx_esb_applicability
    ON public.entity_source_binding (applicability);

CREATE INDEX IF NOT EXISTS idx_esb_status
    ON public.entity_source_binding (status);

COMMENT ON TABLE public.entity_source_binding IS
    'Capability-aware entity↔source binding (ADR-028 Option A). '
    'Unique on (canonical_id, source_id, capability).';

COMMENT ON COLUMN public.entity_source_binding.capability IS
    'notices_or_bids | contracts — dual metric; never conflate';

COMMENT ON COLUMN public.entity_source_binding.applicability IS
    'applicable | not_applicable | unknown — unknown ≠ covered';

CREATE OR REPLACE FUNCTION public.entity_source_binding_touch_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_entity_source_binding_updated_at
    ON public.entity_source_binding;

CREATE TRIGGER trg_entity_source_binding_updated_at
    BEFORE UPDATE ON public.entity_source_binding
    FOR EACH ROW
    EXECUTE FUNCTION public.entity_source_binding_touch_updated_at();

COMMIT;
