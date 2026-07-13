-- ============================================================================
-- 006-v3-unified-schema.sql — Unified Schema v3
-- ============================================================================
-- Resolves the dual-migration-track problem by consolidating ALL missing
-- tables from v1 migrations 013-028 into a single, idempotent v3 migration.
--
-- WHAT THIS INCLUDES:
--   Tables from v1 021: entity_hierarchy, sc_dados_abertos_backfill_log
--   Tables from v1 023: sc_municipalities, pncp_enrichment_cache,
--                       engineering_opportunities
--   Table  from v1 024: coverage_evidence + evidence_state enum
--   Tables from v1 027: opportunity_intel, opportunity_checkpoints,
--                       opportunity_runs, opportunity_coverage
--   Indexes from v1 028: opportunity indexes + partial unique indexes
--   Columns added to existing tables (IF NOT EXISTS):
--     - entity_coverage.match_method
--     - pncp_raw_bids: situacao_compra, unidade_nome, link_sistema_origem,
--       crawl_batch_id, numero_controle_pncp, ano_compra, sequencial_compra,
--       informacao_complementar, source_id, synthetic_id, synthetic_id_reason
--     - pncp_supplier_contracts: codigo_municipio_ibge, municipio_inferido
--   Constraints on existing tables (IF NOT EXISTS):
--     - chk_pncp_raw_bids_esfera_id
--     - chk_ee_enriched_at_not_future, chk_ee_cnpj_not_empty,
--       chk_ee_enriched_source_not_empty
--   Functions/triggers from v1 that operate on new tables
--
-- DESIGN PRINCIPLES:
--   - 100% idempotent: all DDL uses IF NOT EXISTS / OR REPLACE / DO $$ blocks
--   - public schema prefix for consistency with v2 pattern
--   - No seed data (application manages that)
--   - No DROP/CREATE on existing objects (only ADD)
--   - Register in _migrations tracking at end
--
-- MIGRATION HISTORY:
--   v1 track: db/migrations/ (001-028) — organic, never fully applied
--   v2 track: supabase/migrations/ 001-v2 to 005-v2 — active, production baseline
--   v3 track: supabase/migrations/ 006-v3 — consolidation of what's missing
--
-- DEPENDENCIES: 001-v2 (all base tables exist)
-- ============================================================================

BEGIN;

-- ============================================================================
-- Part 1: ALTER EXISTING TABLES — columns from v1 not in v2 baseline
-- ============================================================================

-- --------------------------------------------------------------------------
-- 1.1 entity_coverage: add match_method column
-- Source: v1 migrations 021 (entity_coverage_rebuild) and 022
-- --------------------------------------------------------------------------
ALTER TABLE public.entity_coverage
    ADD COLUMN IF NOT EXISTS match_method TEXT;

COMMENT ON COLUMN public.entity_coverage.match_method IS
    'Metodo de coverage: direct|cnpj_fallback|hierarchical|name_match — v3 unified';

-- Index for match_method queries (partial: only non-NULL rows)
CREATE INDEX IF NOT EXISTS idx_cov_match_method
    ON public.entity_coverage (match_method)
    WHERE match_method IS NOT NULL;

-- --------------------------------------------------------------------------
-- 1.2 pncp_raw_bids: add columns from v1 migration 023 (engineering pipeline)
-- --------------------------------------------------------------------------
ALTER TABLE public.pncp_raw_bids
    ADD COLUMN IF NOT EXISTS situacao_compra TEXT,
    ADD COLUMN IF NOT EXISTS unidade_nome TEXT,
    ADD COLUMN IF NOT EXISTS link_sistema_origem TEXT,
    ADD COLUMN IF NOT EXISTS crawl_batch_id TEXT,
    ADD COLUMN IF NOT EXISTS numero_controle_pncp TEXT,
    ADD COLUMN IF NOT EXISTS ano_compra INTEGER,
    ADD COLUMN IF NOT EXISTS sequencial_compra INTEGER,
    ADD COLUMN IF NOT EXISTS informacao_complementar TEXT,
    ADD COLUMN IF NOT EXISTS source_id TEXT,
    ADD COLUMN IF NOT EXISTS synthetic_id BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS synthetic_id_reason TEXT;

COMMENT ON COLUMN public.pncp_raw_bids.situacao_compra IS 'Situacao da compra no PNCP';
COMMENT ON COLUMN public.pncp_raw_bids.unidade_nome IS 'Nome da unidade compradora';
COMMENT ON COLUMN public.pncp_raw_bids.link_sistema_origem IS 'Link para o sistema de origem';
COMMENT ON COLUMN public.pncp_raw_bids.crawl_batch_id IS 'Identificador do batch de crawl';
COMMENT ON COLUMN public.pncp_raw_bids.numero_controle_pncp IS 'Numero de controle PNCP';
COMMENT ON COLUMN public.pncp_raw_bids.ano_compra IS 'Ano da compra';
COMMENT ON COLUMN public.pncp_raw_bids.sequencial_compra IS 'Sequencial da compra';
COMMENT ON COLUMN public.pncp_raw_bids.informacao_complementar IS 'Informacao complementar da compra';
COMMENT ON COLUMN public.pncp_raw_bids.synthetic_id IS 'TRUE se o pncp_id foi gerado sinteticamente';
COMMENT ON COLUMN public.pncp_raw_bids.synthetic_id_reason IS 'Motivo da geracao sintetica';

-- Indexes for new columns
CREATE INDEX IF NOT EXISTS idx_bids_numero_controle_pncp
    ON public.pncp_raw_bids (numero_controle_pncp);
CREATE INDEX IF NOT EXISTS idx_bids_ano_sequencial
    ON public.pncp_raw_bids (ano_compra, sequencial_compra);
CREATE INDEX IF NOT EXISTS idx_bids_source_id
    ON public.pncp_raw_bids (source_id);

-- --------------------------------------------------------------------------
-- 1.3 pncp_raw_bids: CHECK constraint for esfera_id (v1 018)
-- --------------------------------------------------------------------------
UPDATE public.pncp_raw_bids
SET esfera_id = NULL
WHERE esfera_id IS NOT NULL
  AND esfera_id NOT IN (1, 2, 3, 4);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_pncp_raw_bids_esfera_id') THEN
        ALTER TABLE public.pncp_raw_bids
            ADD CONSTRAINT chk_pncp_raw_bids_esfera_id
            CHECK (esfera_id IS NULL OR esfera_id IN (1, 2, 3, 4));
    END IF;
END $$;

COMMENT ON CONSTRAINT chk_pncp_raw_bids_esfera_id ON public.pncp_raw_bids IS
    'v3 unified: esfera_id deve ser 1=Federal, 2=Estadual, 3=Municipal, 4=Distrital, ou NULL';

-- --------------------------------------------------------------------------
-- 1.4 enriched_entities: CHECK constraints from v1 015
-- --------------------------------------------------------------------------
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_ee_enriched_at_not_future') THEN
        ALTER TABLE public.enriched_entities
            ADD CONSTRAINT chk_ee_enriched_at_not_future
            CHECK (enriched_at <= NOW() + INTERVAL '1 hour')
            NOT VALID;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_ee_cnpj_not_empty') THEN
        ALTER TABLE public.enriched_entities
            ADD CONSTRAINT chk_ee_cnpj_not_empty
            CHECK (cnpj <> '')
            NOT VALID;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_ee_enriched_source_not_empty') THEN
        ALTER TABLE public.enriched_entities
            ADD CONSTRAINT chk_ee_enriched_source_not_empty
            CHECK (enriched_source <> '')
            NOT VALID;
    END IF;
END $$;

-- --------------------------------------------------------------------------
-- 1.5 pncp_supplier_contracts: add columns from v1 021_sc
-- --------------------------------------------------------------------------
ALTER TABLE public.pncp_supplier_contracts
    ADD COLUMN IF NOT EXISTS codigo_municipio_ibge TEXT;

ALTER TABLE public.pncp_supplier_contracts
    ADD COLUMN IF NOT EXISTS municipio_inferido BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN public.pncp_supplier_contracts.codigo_municipio_ibge
    IS '7-digit IBGE municipality code, backfilled by sc_dados_abertos_backfill.py';
COMMENT ON COLUMN public.pncp_supplier_contracts.municipio_inferido
    IS 'TRUE when municipio was inferred (not from original source)';

-- ============================================================================
-- Part 2: NEW TABLES from v1 021 (entity_hierarchy, backfill_log)
-- ============================================================================

-- --------------------------------------------------------------------------
-- 2.1 entity_hierarchy — hierarchical entity mapping
-- Source: v1 021_entity_hierarchy.sql (Story COVERAGE-1.8)
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.entity_hierarchy (
    entity_id           INTEGER NOT NULL,
    parent_entity_id    INTEGER NOT NULL,
    relationship        VARCHAR(32) NOT NULL,
    match_confidence    VARCHAR(16) NOT NULL,
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Primary key
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'entity_hierarchy_pkey') THEN
        ALTER TABLE ONLY public.entity_hierarchy
            ADD CONSTRAINT entity_hierarchy_pkey PRIMARY KEY (entity_id);
    END IF;
END $$;

-- Foreign keys
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'entity_hierarchy_entity_id_fkey') THEN
        ALTER TABLE ONLY public.entity_hierarchy
            ADD CONSTRAINT entity_hierarchy_entity_id_fkey
            FOREIGN KEY (entity_id) REFERENCES public.sc_public_entities(id);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'entity_hierarchy_parent_entity_id_fkey') THEN
        ALTER TABLE ONLY public.entity_hierarchy
            ADD CONSTRAINT entity_hierarchy_parent_entity_id_fkey
            FOREIGN KEY (parent_entity_id) REFERENCES public.sc_public_entities(id);
    END IF;
END $$;

-- CHECK constraints
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'entity_hierarchy_relationship_check') THEN
        ALTER TABLE ONLY public.entity_hierarchy
            ADD CONSTRAINT entity_hierarchy_relationship_check
            CHECK (relationship IN (
                'prefeitura', 'camara', 'autarquia',
                'fundacao', 'fundo', 'conselho', 'outros'
            ));
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'entity_hierarchy_match_confidence_check') THEN
        ALTER TABLE ONLY public.entity_hierarchy
            ADD CONSTRAINT entity_hierarchy_match_confidence_check
            CHECK (match_confidence IN ('direct', 'hierarchical', 'inferred'));
    END IF;
END $$;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_entity_hierarchy_parent
    ON public.entity_hierarchy(parent_entity_id);

CREATE INDEX IF NOT EXISTS idx_entity_hierarchy_relationship
    ON public.entity_hierarchy(relationship);

CREATE INDEX IF NOT EXISTS idx_entity_hierarchy_coverage
    ON public.entity_hierarchy(entity_id, parent_entity_id)
    INCLUDE (relationship);

COMMENT ON TABLE public.entity_hierarchy IS
    'Mapeamento hierarquico de entidades municipais para suas respectivas prefeituras — Story COVERAGE-1.8 (v3 unified)';

-- --------------------------------------------------------------------------
-- 2.2 sc_dados_abertos_backfill_log — audit log for municipio backfill
-- Source: v1 021_sc_dados_abertos_municipio.sql (COVERAGE-1.9)
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.sc_dados_abertos_backfill_log (
    id              SERIAL PRIMARY KEY,
    orgao_cnpj      TEXT NOT NULL,
    match_method    TEXT,
    municipio       TEXT,
    codigo_ibge     TEXT,
    motivo          TEXT,
    executed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE public.sc_dados_abertos_backfill_log IS
    'Audit log for COVERAGE-1.9 municipio backfill: tracks every CNPJ attempt and its outcome';

CREATE INDEX IF NOT EXISTS idx_sdabfl_orgao_cnpj
    ON public.sc_dados_abertos_backfill_log (orgao_cnpj);

CREATE INDEX IF NOT EXISTS idx_sdabfl_motivo
    ON public.sc_dados_abertos_backfill_log (motivo);

CREATE INDEX IF NOT EXISTS idx_sdabfl_executed_at
    ON public.sc_dados_abertos_backfill_log (executed_at DESC);

-- ============================================================================
-- Part 3: NEW TABLES from v1 023 (pncp_engineering_pipeline)
-- ============================================================================

-- --------------------------------------------------------------------------
-- 3.1 sc_municipalities — municipality reference for geolocation
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.sc_municipalities (
    codigo_ibge TEXT PRIMARY KEY,
    municipio TEXT NOT NULL,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    source TEXT NOT NULL DEFAULT 'sc_public_entities_seed',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE public.sc_municipalities IS
    'Referencia municipal usada na geolocalizacao do pipeline PNCP. v3 unified.';

-- --------------------------------------------------------------------------
-- 3.2 pncp_enrichment_cache — PNCP detail enrichment cache
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.pncp_enrichment_cache (
    pncp_id TEXT PRIMARY KEY,
    detail_payload JSONB,
    items_payload JSONB,
    documents_payload JSONB,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- FK to pncp_raw_bids
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'pncp_enrichment_cache_pncp_id_fkey') THEN
        ALTER TABLE ONLY public.pncp_enrichment_cache
            ADD CONSTRAINT pncp_enrichment_cache_pncp_id_fkey
            FOREIGN KEY (pncp_id) REFERENCES public.pncp_raw_bids(pncp_id)
            ON DELETE CASCADE;
    END IF;
END $$;

COMMENT ON TABLE public.pncp_enrichment_cache IS
    'Cache de enriquecimento de detalhes PNCP por pncp_id. v3 unified.';

-- --------------------------------------------------------------------------
-- 3.3 engineering_opportunities — classified engineering opportunities
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.engineering_opportunities (
    id BIGSERIAL PRIMARY KEY,
    pncp_id TEXT NOT NULL,
    source TEXT NOT NULL,
    source_id TEXT,
    objeto_compra TEXT,
    orgao_cnpj TEXT,
    orgao_razao_social TEXT,
    codigo_municipio_ibge TEXT,
    municipio TEXT,
    uf TEXT,
    modalidade_id INTEGER,
    modalidade_nome TEXT,
    valor_total_estimado NUMERIC(18,2),
    data_publicacao TIMESTAMPTZ,
    data_abertura TIMESTAMPTZ,
    data_encerramento TIMESTAMPTZ,
    link_pncp TEXT,
    link_sistema_origem TEXT,
    is_engineering BOOLEAN NOT NULL DEFAULT FALSE,
    engineering_score INTEGER NOT NULL DEFAULT 0,
    engineering_confidence TEXT,
    engineering_categories TEXT[] NOT NULL DEFAULT '{}',
    classification_reasons JSONB NOT NULL DEFAULT '{}'::jsonb,
    classifier_version TEXT,
    exclusion_reason TEXT,
    distance_from_florianopolis_km DOUBLE PRECISION,
    within_200km BOOLEAN NOT NULL DEFAULT FALSE,
    geographic_priority TEXT,
    location_confidence TEXT,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    content_hash TEXT
);

-- FK to pncp_raw_bids
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'engineering_opportunities_pncp_id_fkey') THEN
        ALTER TABLE ONLY public.engineering_opportunities
            ADD CONSTRAINT engineering_opportunities_pncp_id_fkey
            FOREIGN KEY (pncp_id) REFERENCES public.pncp_raw_bids(pncp_id)
            ON DELETE CASCADE;
    END IF;
END $$;

-- Unique constraint
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'engineering_opportunities_pncp_id_key') THEN
        ALTER TABLE ONLY public.engineering_opportunities
            ADD CONSTRAINT engineering_opportunities_pncp_id_key UNIQUE (pncp_id);
    END IF;
END $$;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_eng_op_is_engineering
    ON public.engineering_opportunities (is_engineering);
CREATE INDEX IF NOT EXISTS idx_eng_op_engineering_score
    ON public.engineering_opportunities (engineering_score DESC);
CREATE INDEX IF NOT EXISTS idx_eng_op_within_200km
    ON public.engineering_opportunities (within_200km);
CREATE INDEX IF NOT EXISTS idx_eng_op_ibge
    ON public.engineering_opportunities (codigo_municipio_ibge);
CREATE INDEX IF NOT EXISTS idx_eng_op_orgao_cnpj
    ON public.engineering_opportunities (orgao_cnpj);
CREATE INDEX IF NOT EXISTS idx_eng_op_data_publicacao
    ON public.engineering_opportunities (data_publicacao DESC);
CREATE INDEX IF NOT EXISTS idx_eng_op_data_encerramento
    ON public.engineering_opportunities (data_encerramento DESC);
CREATE INDEX IF NOT EXISTS idx_eng_op_modalidade_id
    ON public.engineering_opportunities (modalidade_id);

COMMENT ON TABLE public.engineering_opportunities IS
    'Camada derivada com classificacao de engenharia civil, geografia SC e links PNCP. v3 unified.';

-- ============================================================================
-- Part 4: NEW TABLE from v1 024 (coverage_evidence_ledger)
-- ============================================================================

-- --------------------------------------------------------------------------
-- 4.1 evidence_state enum
-- --------------------------------------------------------------------------
DO $$ BEGIN
    CREATE TYPE evidence_state AS ENUM (
        'success_with_data',
        'success_zero',
        'partial',
        'connection_failed',
        'auth_failed',
        'parse_failed',
        'transform_failed',
        'persist_failed',
        'not_applicable',
        'not_investigated'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- --------------------------------------------------------------------------
-- 4.2 coverage_evidence table
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.coverage_evidence (
    id              BIGSERIAL PRIMARY KEY,
    entity_id       INT,
    source          TEXT NOT NULL,
    data_type       TEXT NOT NULL DEFAULT 'bids',
    queried_start   DATE,
    queried_end     DATE,
    run_id          TEXT NOT NULL,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    count_obtained     INT NOT NULL DEFAULT 0,
    count_transformed  INT NOT NULL DEFAULT 0,
    count_persisted    INT NOT NULL DEFAULT 0,
    state           evidence_state NOT NULL DEFAULT 'not_investigated',
    error_message   TEXT,
    error_code      TEXT,
    metadata        JSONB DEFAULT '{}'::jsonb
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_ce_state
    ON public.coverage_evidence (state);
CREATE INDEX IF NOT EXISTS idx_ce_entity_source
    ON public.coverage_evidence (entity_id, source);
CREATE INDEX IF NOT EXISTS idx_ce_run
    ON public.coverage_evidence (run_id);
CREATE INDEX IF NOT EXISTS idx_ce_completed
    ON public.coverage_evidence (completed_at);
CREATE INDEX IF NOT EXISTS idx_ce_source_state
    ON public.coverage_evidence (source, state);

-- Partial unique indexes for NULL-safe uniqueness (v1 025_coverage_evidence_null_uniqueness)
CREATE UNIQUE INDEX IF NOT EXISTS uq_ce_entity_run
    ON public.coverage_evidence (entity_id, source, data_type, run_id)
    WHERE entity_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_ce_source_aggregate_run
    ON public.coverage_evidence (source, data_type, run_id)
    WHERE entity_id IS NULL;

-- Completeness check for success_zero rows
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_success_zero_completeness') THEN
        ALTER TABLE public.coverage_evidence
            ADD CONSTRAINT ck_success_zero_completeness
            CHECK (
                state != 'success_zero'
                OR (queried_start IS NOT NULL AND queried_end IS NOT NULL)
                OR (metadata ? 'completeness')
            );
    END IF;
END $$;

COMMENT ON TABLE public.coverage_evidence IS
    'Canonical entity/source evidence table for auditable coverage truth. v3 unified.';

-- --------------------------------------------------------------------------
-- 4.3 Views for coverage_evidence
-- --------------------------------------------------------------------------

CREATE OR REPLACE VIEW public.v_latest_evidence AS
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
FROM public.coverage_evidence
ORDER BY entity_id, source, data_type, completed_at DESC;

COMMENT ON VIEW public.v_latest_evidence IS
    'Latest evidence state per (entity, source, data_type) combination. v3 unified.';

CREATE OR REPLACE VIEW public.v_source_health AS
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
FROM public.v_latest_evidence
GROUP BY source
ORDER BY source;

COMMENT ON VIEW public.v_source_health IS
    'Per-source health summary from latest evidence rows. v3 unified.';

-- ============================================================================
-- Part 5: NEW TABLES from v1 027-028 (opportunity_intel)
-- ============================================================================

-- --------------------------------------------------------------------------
-- 5.1 opportunity_intel — core opportunity records
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.opportunity_intel (
    id                  BIGSERIAL PRIMARY KEY,
    source              TEXT NOT NULL,
    source_id           TEXT NOT NULL,
    source_url          TEXT,
    content_hash        TEXT NOT NULL,
    numero_controle_pncp TEXT,
    crawl_batch_id      TEXT,
    run_id              BIGINT,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    orgao_cnpj          TEXT,
    orgao_nome          TEXT,
    ente_federativo     TEXT,
    uf                  TEXT NOT NULL,
    municipio           TEXT,
    codigo_ibge         TEXT,
    numero_processo     TEXT,
    numero_edital       TEXT,
    modalidade          TEXT,
    modalidade_id       INTEGER,
    objeto              TEXT NOT NULL,
    categoria           TEXT,
    valor_estimado      NUMERIC(18,2),
    valor_homologado    NUMERIC(18,2),
    valor_semantica     TEXT,
    data_publicacao     TIMESTAMPTZ,
    data_abertura       TIMESTAMPTZ,
    data_encerramento   TIMESTAMPTZ,
    data_homologacao    TIMESTAMPTZ,
    status_fonte        TEXT,
    status_canonico     TEXT NOT NULL DEFAULT 'unknown',
    status_motivo       TEXT,
    status_data         TIMESTAMPTZ,
    link_edital         TEXT,
    link_anexos         TEXT[],
    qualidade_score     INTEGER DEFAULT 0,
    qualidade_fatores   JSONB DEFAULT '{}',
    dados_ausentes      TEXT[],
    ranking             TEXT DEFAULT 'REVIEW',
    ranking_score       INTEGER DEFAULT 0,
    ranking_fatores     JSONB DEFAULT '{}',
    ranking_regras      TEXT[],
    ranking_confianca   TEXT DEFAULT 'MEDIUM',
    proveniencia        JSONB DEFAULT '{}',
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    metadata            JSONB DEFAULT '{}'
);

-- Unique constraint for dedup
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_oi_content_hash') THEN
        ALTER TABLE ONLY public.opportunity_intel
            ADD CONSTRAINT uq_oi_content_hash UNIQUE (content_hash);
    END IF;
END $$;

-- CHECK constraints
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_oi_status_canonico') THEN
        ALTER TABLE ONLY public.opportunity_intel
            ADD CONSTRAINT ck_oi_status_canonico CHECK (
                status_canonico IN (
                    'open', 'upcoming', 'closed', 'suspended',
                    'revoked', 'annulled', 'failed', 'unknown'
                )
            );
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_oi_ranking') THEN
        ALTER TABLE ONLY public.opportunity_intel
            ADD CONSTRAINT ck_oi_ranking CHECK (
                ranking IN ('GO', 'REVIEW', 'NO_GO')
            );
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_oi_ranking_confianca') THEN
        ALTER TABLE ONLY public.opportunity_intel
            ADD CONSTRAINT ck_oi_ranking_confianca CHECK (
                ranking_confianca IN ('HIGH', 'MEDIUM', 'LOW')
            );
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_oi_ranking_score') THEN
        ALTER TABLE ONLY public.opportunity_intel
            ADD CONSTRAINT ck_oi_ranking_score CHECK (
                ranking_score >= 0 AND ranking_score <= 100
            );
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_oi_qualidade_score') THEN
        ALTER TABLE ONLY public.opportunity_intel
            ADD CONSTRAINT ck_oi_qualidade_score CHECK (
                qualidade_score >= 0 AND qualidade_score <= 100
            );
    END IF;
END $$;

-- B-tree indexes for lookups
CREATE INDEX IF NOT EXISTS idx_oi_source ON public.opportunity_intel(source);
CREATE INDEX IF NOT EXISTS idx_oi_source_id ON public.opportunity_intel(source, source_id);
CREATE INDEX IF NOT EXISTS idx_oi_orgao_cnpj ON public.opportunity_intel(orgao_cnpj);
CREATE INDEX IF NOT EXISTS idx_oi_uf ON public.opportunity_intel(uf);
CREATE INDEX IF NOT EXISTS idx_oi_municipio ON public.opportunity_intel(municipio);
CREATE INDEX IF NOT EXISTS idx_oi_codigo_ibge ON public.opportunity_intel(codigo_ibge);
CREATE INDEX IF NOT EXISTS idx_oi_status_canonico ON public.opportunity_intel(status_canonico);
CREATE INDEX IF NOT EXISTS idx_oi_data_abertura ON public.opportunity_intel(data_abertura);
CREATE INDEX IF NOT EXISTS idx_oi_data_encerramento ON public.opportunity_intel(data_encerramento);
CREATE INDEX IF NOT EXISTS idx_oi_modalidade ON public.opportunity_intel(modalidade);
CREATE INDEX IF NOT EXISTS idx_oi_ranking ON public.opportunity_intel(ranking);
CREATE INDEX IF NOT EXISTS idx_oi_numero_processo ON public.opportunity_intel(numero_processo);
CREATE INDEX IF NOT EXISTS idx_oi_numero_edital ON public.opportunity_intel(numero_edital);
CREATE INDEX IF NOT EXISTS idx_oi_numero_controle_pncp ON public.opportunity_intel(numero_controle_pncp);
CREATE INDEX IF NOT EXISTS idx_oi_crawl_batch_id ON public.opportunity_intel(crawl_batch_id);
CREATE INDEX IF NOT EXISTS idx_oi_ingested_at ON public.opportunity_intel(ingested_at);
CREATE INDEX IF NOT EXISTS idx_oi_is_active ON public.opportunity_intel(is_active);

-- Composite indexes
CREATE INDEX IF NOT EXISTS idx_oi_uf_status ON public.opportunity_intel(uf, status_canonico);
CREATE INDEX IF NOT EXISTS idx_oi_source_status ON public.opportunity_intel(source, status_canonico);
CREATE INDEX IF NOT EXISTS idx_oi_ranking_score ON public.opportunity_intel(ranking, ranking_score DESC);

-- GIN index for full-text search on objeto
CREATE INDEX IF NOT EXISTS idx_oi_objeto_gin
    ON public.opportunity_intel USING gin(to_tsvector('portuguese', COALESCE(objeto, '')));

-- Partial unique indexes from v1 028
CREATE UNIQUE INDEX IF NOT EXISTS uq_oi_pncp_id
    ON public.opportunity_intel(numero_controle_pncp)
    WHERE numero_controle_pncp IS NOT NULL
      AND is_active = TRUE;

CREATE UNIQUE INDEX IF NOT EXISTS uq_oi_orgao_processo_edital
    ON public.opportunity_intel(orgao_cnpj, numero_processo, numero_edital)
    WHERE orgao_cnpj IS NOT NULL
      AND numero_processo IS NOT NULL
      AND numero_edital IS NOT NULL
      AND is_active = TRUE;

COMMENT ON TABLE public.opportunity_intel IS
    'Core opportunity records for open bidding tracking within 200km of Florianopolis. v3 unified.';

-- --------------------------------------------------------------------------
-- 5.2 opportunity_checkpoints — pagination resumption
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.opportunity_checkpoints (
    source          TEXT NOT NULL,
    scope_key       TEXT NOT NULL,
    last_page       INTEGER,
    last_date       DATE,
    last_id         TEXT,
    records_fetched INTEGER DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (source, scope_key)
);

COMMENT ON TABLE public.opportunity_checkpoints IS
    'Pagination checkpoints per source/scope for opportunity crawl. v3 unified.';

-- --------------------------------------------------------------------------
-- 5.3 opportunity_runs — crawl execution audit trail
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.opportunity_runs (
    id              BIGSERIAL PRIMARY KEY,
    source          TEXT NOT NULL,
    scope_key       TEXT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    records_fetched INTEGER DEFAULT 0,
    records_new     INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    pages_processed INTEGER DEFAULT 0,
    pages_expected  INTEGER,
    status          TEXT NOT NULL DEFAULT 'running',
    error_message   TEXT,
    metadata        JSONB DEFAULT '{}'
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_or_status') THEN
        ALTER TABLE ONLY public.opportunity_runs
            ADD CONSTRAINT ck_or_status CHECK (
                status IN ('running', 'completed', 'completed_zero', 'failed', 'partial')
            );
    END IF;
END $$;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_or_source ON public.opportunity_runs(source);
CREATE INDEX IF NOT EXISTS idx_or_status ON public.opportunity_runs(status);
CREATE INDEX IF NOT EXISTS idx_or_started_at ON public.opportunity_runs(started_at DESC);

COMMENT ON TABLE public.opportunity_runs IS
    'Crawl execution audit trail for opportunity intelligence. v3 unified.';

-- FK: opportunity_intel.run_id -> opportunity_runs.id
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_oi_run_id') THEN
        ALTER TABLE ONLY public.opportunity_intel
            ADD CONSTRAINT fk_oi_run_id
            FOREIGN KEY (run_id) REFERENCES public.opportunity_runs(id)
            ON DELETE SET NULL;
    END IF;
END $$;

-- --------------------------------------------------------------------------
-- 5.4 opportunity_coverage — per-entity per-source coverage
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.opportunity_coverage (
    entity_id         INTEGER NOT NULL,
    source            TEXT NOT NULL,
    period_start      DATE,
    period_end        DATE,
    pages_expected    INTEGER,
    pages_processed   INTEGER,
    last_attempt      TIMESTAMPTZ,
    result            TEXT,
    count_obtained    INTEGER DEFAULT 0,
    count_open        INTEGER DEFAULT 0,
    freshness         INTERVAL,
    error_message     TEXT,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (entity_id, source)
);

-- FK to sc_public_entities
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'opportunity_coverage_entity_id_fkey') THEN
        ALTER TABLE ONLY public.opportunity_coverage
            ADD CONSTRAINT opportunity_coverage_entity_id_fkey
            FOREIGN KEY (entity_id) REFERENCES public.sc_public_entities(id);
    END IF;
END $$;

-- CHECK constraint
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_oc_result') THEN
        ALTER TABLE ONLY public.opportunity_coverage
            ADD CONSTRAINT ck_oc_result CHECK (
                result IN ('success', 'success_zero', 'partial', 'error', 'pending')
            );
    END IF;
END $$;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_oc_source ON public.opportunity_coverage(source);
CREATE INDEX IF NOT EXISTS idx_oc_result ON public.opportunity_coverage(result);
CREATE INDEX IF NOT EXISTS idx_oc_last_attempt ON public.opportunity_coverage(last_attempt DESC);

COMMENT ON TABLE public.opportunity_coverage IS
    'Per-entity per-source coverage tracking for opportunity sources. v3 unified.';

-- ============================================================================
-- Part 6: FUNCTIONS, TRIGGERS & VIEWS from v1 on new tables
-- ============================================================================

-- --------------------------------------------------------------------------
-- 6.1 Entity hierarchy timestamp trigger
-- --------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.update_entity_hierarchy_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_entity_hierarchy_timestamp ON public.entity_hierarchy;
CREATE TRIGGER trg_entity_hierarchy_timestamp
    BEFORE UPDATE ON public.entity_hierarchy
    FOR EACH ROW
    EXECUTE FUNCTION public.update_entity_hierarchy_timestamp();

-- --------------------------------------------------------------------------
-- 6.2 v_hierarchical_coverage view
-- --------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.v_hierarchical_coverage AS
SELECT
    e.id AS entity_id,
    e.razao_social,
    e.municipio,
    e.natureza_juridica,
    h.relationship,
    h.parent_entity_id,
    p.razao_social AS parent_razao_social,
    pec.is_covered AS parent_covered,
    pec.total_bids AS parent_total_bids,
    ec.is_covered AS direct_covered
FROM public.sc_public_entities e
JOIN public.entity_hierarchy h ON h.entity_id = e.id
JOIN public.sc_public_entities p ON p.id = h.parent_entity_id
LEFT JOIN public.entity_coverage ec ON ec.entity_id = e.id AND ec.source = 'pncp'
LEFT JOIN public.entity_coverage pec ON pec.entity_id = h.parent_entity_id AND pec.source = 'pncp'
WHERE e.is_active = TRUE;

COMMENT ON VIEW public.v_hierarchical_coverage IS
    'Consolidated hierarchical coverage view — Story COVERAGE-1.8 (v3 unified)';

-- --------------------------------------------------------------------------
-- 6.3 Opportunity Intel triggers
-- --------------------------------------------------------------------------

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION public.trg_oi_updated_at_fn()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_opportunity_intel_updated_at ON public.opportunity_intel;
CREATE TRIGGER trg_opportunity_intel_updated_at
    BEFORE UPDATE ON public.opportunity_intel
    FOR EACH ROW
    EXECUTE FUNCTION public.trg_oi_updated_at_fn();

-- Auto-update last_seen_at
CREATE OR REPLACE FUNCTION public.trg_oi_last_seen_fn()
RETURNS TRIGGER AS $$
BEGIN
    NEW.last_seen_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_opportunity_intel_last_seen ON public.opportunity_intel;
CREATE TRIGGER trg_opportunity_intel_last_seen
    BEFORE UPDATE ON public.opportunity_intel
    FOR EACH ROW
    EXECUTE FUNCTION public.trg_oi_last_seen_fn();

-- --------------------------------------------------------------------------
-- 6.4 Opportunity Views
-- --------------------------------------------------------------------------

CREATE OR REPLACE VIEW public.v_opportunity_open AS
SELECT
    oi.*,
    spe.razao_social AS orgao_razao_social,
    spe.municipio AS orgao_municipio,
    spe.distancia_fk AS distancia_florianopolis_km,
    spe.raio_200km
FROM public.opportunity_intel oi
LEFT JOIN public.sc_public_entities spe ON oi.orgao_cnpj = spe.cnpj_8
WHERE oi.status_canonico IN ('open', 'upcoming')
  AND oi.is_active = TRUE;

COMMENT ON VIEW public.v_opportunity_open IS
    'Open/upcoming opportunities with entity details. v3 unified.';

CREATE OR REPLACE VIEW public.v_opportunity_by_source AS
SELECT
    source,
    status_canonico,
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE ranking = 'GO') AS go_count,
    COUNT(*) FILTER (WHERE ranking = 'REVIEW') AS review_count,
    COUNT(*) FILTER (WHERE ranking = 'NO_GO') AS no_go_count,
    MIN(data_abertura) AS earliest_abertura,
    MAX(data_encerramento) AS latest_encerramento,
    MIN(ingested_at) AS first_ingested,
    MAX(ingested_at) AS last_ingested
FROM public.opportunity_intel
WHERE is_active = TRUE
GROUP BY source, status_canonico
ORDER BY source, status_canonico;

COMMENT ON VIEW public.v_opportunity_by_source IS
    'Opportunity count summary by source and status. v3 unified.';

CREATE OR REPLACE VIEW public.v_opportunity_coverage_summary AS
SELECT
    oc.source,
    COUNT(DISTINCT oc.entity_id) AS entities_attempted,
    COUNT(DISTINCT oc.entity_id) FILTER (WHERE oc.result IN ('success', 'success_zero')) AS entities_covered,
    COUNT(DISTINCT oc.entity_id) FILTER (WHERE oc.result = 'success') AS entities_with_data,
    COUNT(DISTINCT oc.entity_id) FILTER (WHERE oc.result = 'success_zero') AS entities_empty,
    COUNT(DISTINCT oc.entity_id) FILTER (WHERE oc.result = 'error') AS entities_error,
    SUM(oc.count_obtained) AS total_records,
    SUM(oc.count_open) AS total_open,
    MAX(oc.last_attempt) AS last_run,
    ROUND(
        COUNT(DISTINCT oc.entity_id) FILTER (WHERE oc.result IN ('success', 'success_zero'))::NUMERIC
        / NULLIF(COUNT(DISTINCT oc.entity_id), 0) * 100, 1
    ) AS pct_covered
FROM public.opportunity_coverage oc
GROUP BY oc.source
ORDER BY oc.source;

COMMENT ON VIEW public.v_opportunity_coverage_summary IS
    'Coverage dashboard for opportunity sources. v3 unified.';

-- --------------------------------------------------------------------------
-- 6.5 upsert_opportunity_intel function
-- --------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.upsert_opportunity_intel(batch JSONB)
RETURNS TABLE(action TEXT, record_id BIGINT, content_hash TEXT)
LANGUAGE plpgsql AS $$
DECLARE
    rec JSONB;
    v_action TEXT;
    v_record_id BIGINT;
    v_content_hash TEXT;
BEGIN
    FOR rec IN SELECT * FROM jsonb_array_elements(batch)
    LOOP
        INSERT INTO public.opportunity_intel (
            source, source_id, source_url, content_hash,
            numero_controle_pncp,
            crawl_batch_id, run_id,
            first_seen_at, last_seen_at,
            orgao_cnpj, orgao_nome, ente_federativo,
            uf, municipio, codigo_ibge,
            numero_processo, numero_edital,
            modalidade, modalidade_id,
            objeto, categoria,
            valor_estimado, valor_homologado, valor_semantica,
            data_publicacao, data_abertura, data_encerramento, data_homologacao,
            status_fonte, status_canonico, status_motivo, status_data,
            link_edital, link_anexos,
            qualidade_score, qualidade_fatores, dados_ausentes,
            ranking, ranking_score, ranking_fatores, ranking_regras, ranking_confianca,
            proveniencia, metadata
        ) VALUES (
            rec->>'source',
            rec->>'source_id',
            rec->>'source_url',
            rec->>'content_hash',
            rec->>'numero_controle_pncp',
            rec->>'crawl_batch_id',
            (rec->>'run_id')::BIGINT,
            COALESCE((rec->>'first_seen_at')::TIMESTAMPTZ, NOW()),
            COALESCE((rec->>'last_seen_at')::TIMESTAMPTZ, NOW()),
            rec->>'orgao_cnpj',
            rec->>'orgao_nome',
            rec->>'ente_federativo',
            rec->>'uf',
            rec->>'municipio',
            rec->>'codigo_ibge',
            rec->>'numero_processo',
            rec->>'numero_edital',
            rec->>'modalidade',
            (rec->>'modalidade_id')::INTEGER,
            rec->>'objeto',
            rec->>'categoria',
            (rec->>'valor_estimado')::NUMERIC,
            (rec->>'valor_homologado')::NUMERIC,
            rec->>'valor_semantica',
            (rec->>'data_publicacao')::TIMESTAMPTZ,
            (rec->>'data_abertura')::TIMESTAMPTZ,
            (rec->>'data_encerramento')::TIMESTAMPTZ,
            (rec->>'data_homologacao')::TIMESTAMPTZ,
            rec->>'status_fonte',
            COALESCE(rec->>'status_canonico', 'unknown'),
            rec->>'status_motivo',
            (rec->>'status_data')::TIMESTAMPTZ,
            rec->>'link_edital',
            CASE WHEN rec->'link_anexos' IS NOT NULL
                 THEN ARRAY(SELECT * FROM jsonb_array_elements_text(rec->'link_anexos'))
            END,
            COALESCE((rec->>'qualidade_score')::INTEGER, 0),
            COALESCE(rec->'qualidade_fatores', '{}'),
            CASE WHEN rec->'dados_ausentes' IS NOT NULL
                 THEN ARRAY(SELECT * FROM jsonb_array_elements_text(rec->'dados_ausentes'))
            END,
            COALESCE(rec->>'ranking', 'REVIEW'),
            COALESCE((rec->>'ranking_score')::INTEGER, 0),
            COALESCE(rec->'ranking_fatores', '{}'),
            CASE WHEN rec->'ranking_regras' IS NOT NULL
                 THEN ARRAY(SELECT * FROM jsonb_array_elements_text(rec->'ranking_regras'))
            END,
            COALESCE(rec->>'ranking_confianca', 'MEDIUM'),
            COALESCE(rec->'proveniencia', '{}'),
            COALESCE(rec->'metadata', '{}')
        )
        ON CONFLICT ON CONSTRAINT uq_oi_content_hash DO UPDATE SET
            source_url = EXCLUDED.source_url,
            numero_controle_pncp = COALESCE(EXCLUDED.numero_controle_pncp, public.opportunity_intel.numero_controle_pncp),
            crawl_batch_id = EXCLUDED.crawl_batch_id,
            run_id = EXCLUDED.run_id,
            last_seen_at = NOW(),
            orgao_cnpj = COALESCE(EXCLUDED.orgao_cnpj, public.opportunity_intel.orgao_cnpj),
            orgao_nome = COALESCE(EXCLUDED.orgao_nome, public.opportunity_intel.orgao_nome),
            uf = COALESCE(EXCLUDED.uf, public.opportunity_intel.uf),
            municipio = COALESCE(EXCLUDED.municipio, public.opportunity_intel.municipio),
            codigo_ibge = COALESCE(EXCLUDED.codigo_ibge, public.opportunity_intel.codigo_ibge),
            numero_processo = COALESCE(EXCLUDED.numero_processo, public.opportunity_intel.numero_processo),
            numero_edital = COALESCE(EXCLUDED.numero_edital, public.opportunity_intel.numero_edital),
            modalidade = COALESCE(EXCLUDED.modalidade, public.opportunity_intel.modalidade),
            modalidade_id = COALESCE(EXCLUDED.modalidade_id, public.opportunity_intel.modalidade_id),
            objeto = COALESCE(EXCLUDED.objeto, public.opportunity_intel.objeto),
            categoria = COALESCE(EXCLUDED.categoria, public.opportunity_intel.categoria),
            valor_estimado = COALESCE(EXCLUDED.valor_estimado, public.opportunity_intel.valor_estimado),
            valor_homologado = COALESCE(EXCLUDED.valor_homologado, public.opportunity_intel.valor_homologado),
            valor_semantica = COALESCE(EXCLUDED.valor_semantica, public.opportunity_intel.valor_semantica),
            data_publicacao = COALESCE(EXCLUDED.data_publicacao, public.opportunity_intel.data_publicacao),
            data_abertura = COALESCE(EXCLUDED.data_abertura, public.opportunity_intel.data_abertura),
            data_encerramento = COALESCE(EXCLUDED.data_encerramento, public.opportunity_intel.data_encerramento),
            data_homologacao = COALESCE(EXCLUDED.data_homologacao, public.opportunity_intel.data_homologacao),
            status_fonte = EXCLUDED.status_fonte,
            status_canonico = EXCLUDED.status_canonico,
            status_motivo = EXCLUDED.status_motivo,
            status_data = EXCLUDED.status_data,
            link_edital = COALESCE(EXCLUDED.link_edital, public.opportunity_intel.link_edital),
            link_anexos = COALESCE(EXCLUDED.link_anexos, public.opportunity_intel.link_anexos),
            qualidade_score = EXCLUDED.qualidade_score,
            qualidade_fatores = EXCLUDED.qualidade_fatores,
            dados_ausentes = EXCLUDED.dados_ausentes,
            ranking = EXCLUDED.ranking,
            ranking_score = EXCLUDED.ranking_score,
            ranking_fatores = EXCLUDED.ranking_fatores,
            ranking_regras = EXCLUDED.ranking_regras,
            ranking_confianca = EXCLUDED.ranking_confianca,
            proveniencia = EXCLUDED.proveniencia,
            metadata = EXCLUDED.metadata,
            is_active = EXCLUDED.is_active
        RETURNING
            (CASE WHEN xmax = 0 THEN 'insert' ELSE 'update' END)::TEXT,
            id,
            content_hash
        INTO v_action, v_record_id, v_content_hash;

        action := v_action;
        record_id := v_record_id;
        content_hash := v_content_hash;
        RETURN NEXT;
    END LOOP;
END;
$$;

COMMENT ON FUNCTION public.upsert_opportunity_intel IS
    'Batch upsert for opportunity_intel with content_hash dedup. v3 unified.';

-- ============================================================================
-- Part 7: Register in _migrations tracking
-- ============================================================================
INSERT INTO public._migrations (version, name, applied_at, checksum, rollback_sql)
VALUES (
    '006-v3',
    'unified_schema_v3',
    NOW(),
    'sha256=v3-unified-manual',
    'See docs/architecture/schema-v3.md for rollback procedure'
)
ON CONFLICT (version) DO NOTHING;

COMMIT;
