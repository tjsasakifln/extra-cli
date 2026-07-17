-- ============================================================================
-- Migration 053: Entity Source Registry
-- ============================================================================
-- Purpose: Persist the canonical per-entity source mapping for the 1093-entity
-- target universe (200 km). One row per entity with portals, platforms,
-- access status, blockers, and collection strategy.
--
-- Unique keys:
--   - canonical_id (stable text id)
--   - (cnpj, natureza_juridica, razao_social) as defensive uniqueness
--
-- Dependencies: none hard
-- Rollback: DROP TABLE IF EXISTS public.entity_source_registry;
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS public.entity_source_registry (
    id                      BIGSERIAL PRIMARY KEY,

    -- Identity
    canonical_id            TEXT NOT NULL,
    razao_social            TEXT NOT NULL,
    nome_fantasia           TEXT,
    cnpj                    TEXT NOT NULL,          -- 14 digits preferred; partial (8) accepted
    natureza_juridica       TEXT NOT NULL,          -- entity_type from seed
    entity_type             TEXT GENERATED ALWAYS AS (natureza_juridica) STORED,

    -- Location
    municipio               TEXT,
    uf                      TEXT NOT NULL DEFAULT 'SC',
    ibge_code               TEXT,
    lat                     DOUBLE PRECISION,
    lon                     DOUBLE PRECISION,
    distance_km             DOUBLE PRECISION,

    -- Portals
    portal_institucional    TEXT,
    portal_transparencia    TEXT,
    portal_licitacoes       TEXT,
    diario_oficial          TEXT,

    -- Platforms & integration
    plataformas             TEXT[] NOT NULL DEFAULT '{}',
    external_ids            JSONB NOT NULL DEFAULT '{}'::jsonb,
    url_patterns            JSONB NOT NULL DEFAULT '{}'::jsonb,
    integration_type        TEXT NOT NULL DEFAULT 'unknown'
                            CHECK (integration_type IN (
                                'api_json', 'html', 'pdf', 'js', 'ckan',
                                'rss', 'shared_portal', 'unknown'
                            )),

    -- Access / SLA
    access_status           TEXT NOT NULL DEFAULT 'unknown'
                            CHECK (access_status IN (
                                'mapped', 'accessible', 'collected', 'failed',
                                'blocked', 'unknown', 'source_not_identified'
                            )),
    last_success_at         TIMESTAMPTZ,
    last_attempt_at         TIMESTAMPTZ,
    sla_hours               INTEGER,

    -- Strategy / blockers
    collection_strategy     TEXT NOT NULL DEFAULT 'pending_review',
    current_blocker         TEXT,
    next_action             TEXT NOT NULL DEFAULT 'review_source_applicability',
    priority                INTEGER NOT NULL DEFAULT 5
                            CHECK (priority BETWEEN 1 AND 10),
    mapping_confidence      DOUBLE PRECISION NOT NULL DEFAULT 0.0
                            CHECK (mapping_confidence >= 0.0 AND mapping_confidence <= 1.0),
    evidences               JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Audit
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_entity_source_registry_canonical UNIQUE (canonical_id),
    CONSTRAINT uq_entity_source_registry_cnpj_type_name
        UNIQUE (cnpj, natureza_juridica, razao_social)
);

CREATE INDEX IF NOT EXISTS idx_entity_source_registry_cnpj
    ON public.entity_source_registry (cnpj);

CREATE INDEX IF NOT EXISTS idx_entity_source_registry_ibge
    ON public.entity_source_registry (ibge_code);

CREATE INDEX IF NOT EXISTS idx_entity_source_registry_status
    ON public.entity_source_registry (access_status);

CREATE INDEX IF NOT EXISTS idx_entity_source_registry_blocker
    ON public.entity_source_registry (current_blocker);

CREATE INDEX IF NOT EXISTS idx_entity_source_registry_priority
    ON public.entity_source_registry (priority);

CREATE INDEX IF NOT EXISTS idx_entity_source_registry_plataformas
    ON public.entity_source_registry USING GIN (plataformas);

CREATE INDEX IF NOT EXISTS idx_entity_source_registry_municipio
    ON public.entity_source_registry (municipio);

COMMENT ON TABLE public.entity_source_registry IS
    'Canonical per-entity source mapping for the 1093-entity 200km target universe';

COMMENT ON COLUMN public.entity_source_registry.canonical_id IS
    'Stable id: {cnpj8}:{NAME_SLUG}';

COMMENT ON COLUMN public.entity_source_registry.access_status IS
    'mapped|accessible|collected|failed|blocked|unknown|source_not_identified';

COMMENT ON COLUMN public.entity_source_registry.current_blocker IS
    'rate_limited|no_api|legacy_portal|pdf|javascript|captcha|fragmented|credential|not_applicable|none';

-- Touch updated_at on UPDATE
CREATE OR REPLACE FUNCTION public.entity_source_registry_touch_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_entity_source_registry_updated_at
    ON public.entity_source_registry;

CREATE TRIGGER trg_entity_source_registry_updated_at
    BEFORE UPDATE ON public.entity_source_registry
    FOR EACH ROW
    EXECUTE FUNCTION public.entity_source_registry_touch_updated_at();

COMMIT;
