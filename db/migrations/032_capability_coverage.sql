-- ============================================================================
-- Migration 032: Capability Coverage
-- ============================================================================
-- Story 1.2 (Unify Schema) — Capability coverage tracking
--
-- Define uma estrutura para rastrear cobertura por capacidade de negocio
-- (ex: "detecta oportunidades de engenharia", "cobertura de contratos
-- ativos", "radar QW-01"), permitindo visibilidade granular sobre quais
-- capacidades do sistema estao operacionais por fonte/entidade.
--
-- Depende de: 001-029 (coverage_evidence, entity_coverage existem)
-- Idempotente: Sim
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. Capability coverage table
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.capability_coverage (
    id              BIGSERIAL PRIMARY KEY,
    capability      TEXT NOT NULL,
    entity_id       INT,
    source          TEXT NOT NULL,
    is_covered      BOOLEAN NOT NULL DEFAULT FALSE,
    coverage_pct    NUMERIC(5,2) DEFAULT 0,
    last_verified   TIMESTAMPTZ,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Same entity+source+capability can only have one active row
    CONSTRAINT uq_cap_coverage UNIQUE (capability, entity_id, source)
);

COMMENT ON TABLE public.capability_coverage IS
    'Capability-level coverage tracking. Story 1.2';
COMMENT ON COLUMN public.capability_coverage.capability IS
    'Nome da capacidade: opportunity_radar|contract_intel|entity_matching|coverage_truth|source_health';
COMMENT ON COLUMN public.capability_coverage.coverage_pct IS
    'Percentual de cobertura para esta capacidade (0.00 - 100.00)';

-- Indexes
CREATE INDEX IF NOT EXISTS idx_cc_capability
    ON public.capability_coverage (capability, is_covered);

CREATE INDEX IF NOT EXISTS idx_cc_entity
    ON public.capability_coverage (entity_id, capability)
    WHERE entity_id IS NOT NULL;

-- ============================================================================
-- 2. Auto-update trigger for updated_at
-- ============================================================================
CREATE OR REPLACE FUNCTION public.fn_cap_coverage_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_cap_coverage_updated_at') THEN
        CREATE TRIGGER trg_cap_coverage_updated_at
            BEFORE UPDATE ON public.capability_coverage
            FOR EACH ROW
            EXECUTE FUNCTION public.fn_cap_coverage_updated_at();
    END IF;
END $$;

-- ============================================================================
-- 3. Capability coverage summary view
-- ============================================================================
CREATE OR REPLACE VIEW public.v_capability_coverage_summary AS
SELECT
    capability,
    COUNT(*)::INTEGER AS total_entries,
    COUNT(*) FILTER (WHERE is_covered)::INTEGER AS covered_entries,
    ROUND(100.0 * COUNT(*) FILTER (WHERE is_covered) / GREATEST(COUNT(*), 1), 1) AS pct_covered,
    MAX(last_verified) AS last_verified_at
FROM public.capability_coverage
GROUP BY capability
ORDER BY capability;

COMMENT ON VIEW public.v_capability_coverage_summary IS
    'Summary of capability coverage per capability. Story 1.2';

-- ============================================================================
-- Rollback SQL
-- ============================================================================
-- DROP VIEW IF EXISTS public.v_capability_coverage_summary;
-- DROP TRIGGER IF EXISTS trg_cap_coverage_updated_at ON public.capability_coverage;
-- DROP FUNCTION IF EXISTS public.fn_cap_coverage_updated_at;
-- DROP TABLE IF EXISTS public.capability_coverage;

COMMIT;
