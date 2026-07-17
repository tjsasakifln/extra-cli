-- ============================================================================
-- Migration 052: Unified Official Acts (DOE + DOM + gazette publications)
-- ============================================================================
-- Purpose: Normalize official publications (state DOE, municipal DOM, CKAN
-- bulk dumps) into a single acts model with provenance, classification,
-- document links, content hashes, and explicit date semantics.
--
-- Tables:
--   official_act_resources      — source resource metadata (CKAN resource, URL, hash)
--   official_acts               — normalized acts (one row per source observation)
--   official_act_classifications— classification snapshots (history-friendly)
--   official_act_links          — URLs / attached documents
--   official_act_source_links   — multi-source observations of the same act
--   official_act_matches        — links to PNCP bids/contracts (reconciliation later)
--
-- Design principles:
--   - Keep original record (raw_json / raw_text)
--   - Defensible unique keys: (source, record_hash) and (source, external_id)
--   - Explicit dates: publication_date, edition_date, event_date + date_semantics
--   - Provenance: source portal, resource_id, run_id
--   - Idempotent: IF NOT EXISTS / DO blocks throughout
--
-- Dependencies: none hard (pipeline_runs is soft reference by TEXT run_id)
-- Rollback: see db/rollback/052_official_acts_rollback.sql
-- ============================================================================

BEGIN;

-- ==========================================================================
-- 1. official_act_resources — bulk resource / edition file metadata
-- ==========================================================================

CREATE TABLE IF NOT EXISTS public.official_act_resources (
    id                  BIGSERIAL PRIMARY KEY,

    -- Source identity
    source              TEXT NOT NULL,          -- ciga_ckan, doe_sc, dom_sc, dados_abertos_sc, ...
    resource_id         TEXT,                   -- CKAN resource UUID or portal resource key
    package_id          TEXT,                   -- CKAN package / dataset id
    package_name        TEXT,                   -- human dataset slug (domsc-publicacoes-de-MM-YYYY)
    title               TEXT,
    resource_url        TEXT,
    format              TEXT,                   -- json, zip, html, pdf, xml

    -- Integrity / cache validators
    content_sha256      TEXT,
    etag                TEXT,
    last_modified       TIMESTAMPTZ,
    size_bytes          BIGINT,

    -- Provenance
    run_id              TEXT,                   -- pipeline_runs.run_id or free-form batch id
    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_fetched_at     TIMESTAMPTZ,
    fetch_status        TEXT NOT NULL DEFAULT 'discovered',
    -- discovered | fetched | parsed | failed | stale

    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE public.official_act_resources IS
    'Metadata of source resources (CKAN files, DOE bulk dumps, DOM ZIPs) feeding official_acts.';
COMMENT ON COLUMN public.official_act_resources.source IS
    'Canonical source portal id (ciga_ckan, doe_sc, dom_sc, dados_abertos_sc, ...).';
COMMENT ON COLUMN public.official_act_resources.resource_id IS
    'Stable resource key in the source (CKAN resource id preferred).';
COMMENT ON COLUMN public.official_act_resources.content_sha256 IS
    'SHA-256 of the downloaded resource body when available.';
COMMENT ON COLUMN public.official_act_resources.run_id IS
    'Pipeline run that last observed/fetched this resource (soft ref to pipeline_runs.run_id).';
COMMENT ON COLUMN public.official_act_resources.fetch_status IS
    'Lifecycle: discovered | fetched | parsed | failed | stale.';

-- Unique: prefer (source, resource_id) when portal gives an id
CREATE UNIQUE INDEX IF NOT EXISTS uq_oar_source_resource_id
    ON public.official_act_resources (source, resource_id)
    WHERE resource_id IS NOT NULL;

-- Unique: same content hash from same source is one resource
CREATE UNIQUE INDEX IF NOT EXISTS uq_oar_source_content_sha256
    ON public.official_act_resources (source, content_sha256)
    WHERE content_sha256 IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_oar_source_seen
    ON public.official_act_resources (source, last_seen_at DESC);

CREATE INDEX IF NOT EXISTS idx_oar_package
    ON public.official_act_resources (source, package_name)
    WHERE package_name IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_oar_run_id
    ON public.official_act_resources (run_id)
    WHERE run_id IS NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_oar_fetch_status'
    ) THEN
        ALTER TABLE public.official_act_resources
            ADD CONSTRAINT ck_oar_fetch_status CHECK (
                fetch_status IN ('discovered', 'fetched', 'parsed', 'failed', 'stale')
            );
    END IF;
END $$;

-- ==========================================================================
-- 2. official_acts — normalized gazette / official publication acts
-- ==========================================================================

CREATE TABLE IF NOT EXISTS public.official_acts (
    id                  BIGSERIAL PRIMARY KEY,

    -- Identity & dedup
    source              TEXT NOT NULL,          -- portal that produced this observation
    external_id         TEXT,                   -- codigo / id nativo da fonte
    record_hash         TEXT NOT NULL,          -- sha256 of stable content fingerprint
    content_hash        TEXT,                   -- optional alternate hash (title+body)

    -- Provenance
    resource_fk         BIGINT REFERENCES public.official_act_resources(id) ON DELETE SET NULL,
    run_id              TEXT,
    crawl_batch_id      TEXT,
    source_url          TEXT,

    -- Original publication payload (never drop)
    title               TEXT,
    raw_text            TEXT,
    raw_json            JSONB,
    summary             TEXT,

    -- Classification (denormalized snapshot; history in official_act_classifications)
    category            TEXT,                   -- machine id from act_classifier / source
    category_source     TEXT,                   -- classifier | source_native | manual
    category_confidence TEXT,                   -- high | medium | low
    classification_evidence TEXT,

    -- Public entity / municipality
    orgao_nome          TEXT,
    orgao_cnpj          TEXT,
    ente_federativo     TEXT,                   -- municipal | estadual | federal | outro
    uf                  TEXT,
    municipio           TEXT,
    codigo_ibge         TEXT,

    -- Explicit date semantics (do NOT overload a single date column)
    publication_date    DATE,                   -- when published in the gazette/portal
    edition_date        DATE,                   -- DOE/DOM edition date
    event_date          DATE,                   -- best event date for the act itself
    date_semantics      TEXT,                   -- how dates were derived
    -- e.g. publication_from_source_data, edition_from_package_name, event_unknown

    edition_number      TEXT,
    page_number         TEXT,
    section             TEXT,

    -- Related process identifiers (textual; structured matches elsewhere)
    process_number      TEXT,
    edital_number       TEXT,
    contract_number     TEXT,
    related_pncp_id     TEXT,                   -- soft text link (numero_controle_pncp)
    related_contract_id TEXT,                   -- soft text link (contrato_id)

    -- Status
    status              TEXT NOT NULL DEFAULT 'active',
    -- active | superseded | revoked | annulled | archived | unknown
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,

    -- Timestamps
    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Flexible provenance + extras
    proveniencia        JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE public.official_acts IS
    'Normalized official acts from DOE/DOM/gazette sources. One row per (source, record_hash).';
COMMENT ON COLUMN public.official_acts.record_hash IS
    'Defensible content fingerprint (sha256). Unique together with source.';
COMMENT ON COLUMN public.official_acts.external_id IS
    'Native source id when available (CIGA codigo, DOE id, etc.).';
COMMENT ON COLUMN public.official_acts.raw_text IS
    'Original publication body text. Prefer raw_json for structured dumps.';
COMMENT ON COLUMN public.official_acts.raw_json IS
    'Original structured record from source. Must be preserved for audit.';
COMMENT ON COLUMN public.official_acts.publication_date IS
    'Date the act was published in the gazette/portal (not signature/event).';
COMMENT ON COLUMN public.official_acts.edition_date IS
    'Date of the DOE/DOM edition that carries the act.';
COMMENT ON COLUMN public.official_acts.event_date IS
    'Best date describing the act event itself when known; else NULL.';
COMMENT ON COLUMN public.official_acts.date_semantics IS
    'How date columns were derived (explicit string, never invent silently).';
COMMENT ON COLUMN public.official_acts.category IS
    'Procurement act category (act_classifier ids or source-native).';
COMMENT ON COLUMN public.official_acts.resource_fk IS
    'FK to official_act_resources when act came from a bulk resource.';
COMMENT ON COLUMN public.official_acts.run_id IS
    'Pipeline run id that last observed this act (soft ref).';
COMMENT ON COLUMN public.official_acts.proveniencia IS
    'Per-field provenance map (source portal, resource_id, run_id, extractors).';

-- Defensible unique keys
CREATE UNIQUE INDEX IF NOT EXISTS uq_oa_source_record_hash
    ON public.official_acts (source, record_hash);

CREATE UNIQUE INDEX IF NOT EXISTS uq_oa_source_external_id
    ON public.official_acts (source, external_id)
    WHERE external_id IS NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_oa_status'
    ) THEN
        ALTER TABLE public.official_acts
            ADD CONSTRAINT ck_oa_status CHECK (
                status IN (
                    'active', 'superseded', 'revoked', 'annulled',
                    'archived', 'unknown'
                )
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_oa_category_confidence'
    ) THEN
        ALTER TABLE public.official_acts
            ADD CONSTRAINT ck_oa_category_confidence CHECK (
                category_confidence IS NULL
                OR category_confidence IN ('high', 'medium', 'low')
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_oa_category_source'
    ) THEN
        ALTER TABLE public.official_acts
            ADD CONSTRAINT ck_oa_category_source CHECK (
                category_source IS NULL
                OR category_source IN ('classifier', 'source_native', 'manual', 'unknown')
            );
    END IF;
END $$;

-- Required indexes: orgao, municipio, date, category, hash, source
CREATE INDEX IF NOT EXISTS idx_oa_orgao_nome
    ON public.official_acts (orgao_nome)
    WHERE orgao_nome IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_oa_orgao_cnpj
    ON public.official_acts (orgao_cnpj)
    WHERE orgao_cnpj IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_oa_municipio
    ON public.official_acts (municipio)
    WHERE municipio IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_oa_uf_municipio
    ON public.official_acts (uf, municipio)
    WHERE uf IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_oa_publication_date
    ON public.official_acts (publication_date DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_oa_edition_date
    ON public.official_acts (edition_date DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_oa_event_date
    ON public.official_acts (event_date DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_oa_category
    ON public.official_acts (category)
    WHERE category IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_oa_record_hash
    ON public.official_acts (record_hash);

CREATE INDEX IF NOT EXISTS idx_oa_source
    ON public.official_acts (source, last_seen_at DESC);

CREATE INDEX IF NOT EXISTS idx_oa_source_status
    ON public.official_acts (source, status)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_oa_resource_fk
    ON public.official_acts (resource_fk)
    WHERE resource_fk IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_oa_run_id
    ON public.official_acts (run_id)
    WHERE run_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_oa_process_number
    ON public.official_acts (process_number)
    WHERE process_number IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_oa_related_pncp
    ON public.official_acts (related_pncp_id)
    WHERE related_pncp_id IS NOT NULL;

-- ==========================================================================
-- 3. official_act_classifications — classification history snapshots
-- ==========================================================================

CREATE TABLE IF NOT EXISTS public.official_act_classifications (
    id                  BIGSERIAL PRIMARY KEY,
    act_id              BIGINT NOT NULL
                            REFERENCES public.official_acts(id) ON DELETE CASCADE,
    category            TEXT NOT NULL,
    confidence          TEXT,
    method              TEXT NOT NULL DEFAULT 'deterministic_rules',
    -- deterministic_rules | source_native | manual | ml
    classifier_version  TEXT,
    evidence            TEXT,
    classified_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE public.official_act_classifications IS
    'Historical classification snapshots for official_acts (reclass-safe).';

CREATE INDEX IF NOT EXISTS idx_oac_act_id
    ON public.official_act_classifications (act_id, classified_at DESC);

CREATE INDEX IF NOT EXISTS idx_oac_category
    ON public.official_act_classifications (category);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_oac_confidence'
    ) THEN
        ALTER TABLE public.official_act_classifications
            ADD CONSTRAINT ck_oac_confidence CHECK (
                confidence IS NULL
                OR confidence IN ('high', 'medium', 'low')
            );
    END IF;
END $$;

-- ==========================================================================
-- 4. official_act_links — document / page URLs
-- ==========================================================================

CREATE TABLE IF NOT EXISTS public.official_act_links (
    id                  BIGSERIAL PRIMARY KEY,
    act_id              BIGINT NOT NULL
                            REFERENCES public.official_acts(id) ON DELETE CASCADE,
    link_type           TEXT NOT NULL DEFAULT 'source_page',
    -- source_page | pdf | attachment | html | edital | zip | other
    url                 TEXT NOT NULL,
    title               TEXT,
    mime_type           TEXT,
    content_sha256      TEXT,
    fetched_at          TIMESTAMPTZ,
    is_primary          BOOLEAN NOT NULL DEFAULT FALSE,
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE public.official_act_links IS
    'URLs and document references attached to an official act.';

CREATE UNIQUE INDEX IF NOT EXISTS uq_oal_act_url
    ON public.official_act_links (act_id, url);

CREATE INDEX IF NOT EXISTS idx_oal_act_id
    ON public.official_act_links (act_id);

CREATE INDEX IF NOT EXISTS idx_oal_link_type
    ON public.official_act_links (link_type);

CREATE INDEX IF NOT EXISTS idx_oal_content_sha256
    ON public.official_act_links (content_sha256)
    WHERE content_sha256 IS NOT NULL;

-- ==========================================================================
-- 5. official_act_source_links — multi-source observations of one act
-- ==========================================================================
-- Optional bridge: several portals may publish the "same" act. The canonical
-- row lives in official_acts; each additional observation is recorded here.

CREATE TABLE IF NOT EXISTS public.official_act_source_links (
    id                  BIGSERIAL PRIMARY KEY,
    act_id              BIGINT NOT NULL
                            REFERENCES public.official_acts(id) ON DELETE CASCADE,
    source              TEXT NOT NULL,
    external_id         TEXT,
    record_hash         TEXT NOT NULL,
    resource_fk         BIGINT
                            REFERENCES public.official_act_resources(id) ON DELETE SET NULL,
    run_id              TEXT,
    source_url          TEXT,
    observed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    raw_json            JSONB,
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE public.official_act_source_links IS
    'Additional source observations pointing to a canonical official_acts row.';

CREATE UNIQUE INDEX IF NOT EXISTS uq_oasl_source_record_hash
    ON public.official_act_source_links (source, record_hash);

CREATE UNIQUE INDEX IF NOT EXISTS uq_oasl_source_external_id
    ON public.official_act_source_links (source, external_id)
    WHERE external_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_oasl_act_id
    ON public.official_act_source_links (act_id);

CREATE INDEX IF NOT EXISTS idx_oasl_source
    ON public.official_act_source_links (source, observed_at DESC);

-- ==========================================================================
-- 6. official_act_matches — reconciliation to bids / contracts
-- ==========================================================================

CREATE TABLE IF NOT EXISTS public.official_act_matches (
    id                  BIGSERIAL PRIMARY KEY,
    act_id              BIGINT NOT NULL
                            REFERENCES public.official_acts(id) ON DELETE CASCADE,
    match_type          TEXT NOT NULL,
    -- bid | contract | process | entity | opportunity
    target_table        TEXT NOT NULL,
    -- pncp_raw_bids | pncp_supplier_contracts | opportunity_intel | ...
    target_id           TEXT NOT NULL,
    match_method        TEXT,                   -- exact_id, fuzzy_process, cnpj_date, manual
    match_score         NUMERIC(6, 4),
    match_confidence    TEXT,                   -- high | medium | low
    matched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    matched_by          TEXT,                   -- run_id or agent/system name
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE public.official_act_matches IS
    'Links official acts to PNCP bids/contracts/opportunities for later reconciliation.';

CREATE UNIQUE INDEX IF NOT EXISTS uq_oam_act_target
    ON public.official_act_matches (act_id, match_type, target_table, target_id);

CREATE INDEX IF NOT EXISTS idx_oam_act_id
    ON public.official_act_matches (act_id)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_oam_target
    ON public.official_act_matches (target_table, target_id)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_oam_match_type
    ON public.official_act_matches (match_type)
    WHERE is_active = TRUE;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_oam_confidence'
    ) THEN
        ALTER TABLE public.official_act_matches
            ADD CONSTRAINT ck_oam_confidence CHECK (
                match_confidence IS NULL
                OR match_confidence IN ('high', 'medium', 'low')
            );
    END IF;
END $$;

-- ==========================================================================
-- 7. updated_at trigger for official_acts / resources
-- ==========================================================================

CREATE OR REPLACE FUNCTION public.fn_official_acts_touch_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_oa_updated_at ON public.official_acts;
CREATE TRIGGER trg_oa_updated_at
    BEFORE UPDATE ON public.official_acts
    FOR EACH ROW
    EXECUTE FUNCTION public.fn_official_acts_touch_updated_at();

DROP TRIGGER IF EXISTS trg_oar_updated_at ON public.official_act_resources;
CREATE TRIGGER trg_oar_updated_at
    BEFORE UPDATE ON public.official_act_resources
    FOR EACH ROW
    EXECUTE FUNCTION public.fn_official_acts_touch_updated_at();

-- ==========================================================================
-- 8. Upsert helpers (SQL) — batch insert/update for crawlers
-- ==========================================================================

-- 8a. Upsert a resource; returns id
CREATE OR REPLACE FUNCTION public.upsert_official_act_resource(
    p_source            TEXT,
    p_resource_id       TEXT DEFAULT NULL,
    p_package_id        TEXT DEFAULT NULL,
    p_package_name      TEXT DEFAULT NULL,
    p_title             TEXT DEFAULT NULL,
    p_resource_url      TEXT DEFAULT NULL,
    p_format            TEXT DEFAULT NULL,
    p_content_sha256    TEXT DEFAULT NULL,
    p_etag              TEXT DEFAULT NULL,
    p_last_modified     TIMESTAMPTZ DEFAULT NULL,
    p_size_bytes        BIGINT DEFAULT NULL,
    p_run_id            TEXT DEFAULT NULL,
    p_fetch_status      TEXT DEFAULT 'discovered',
    p_metadata          JSONB DEFAULT '{}'::jsonb
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_id BIGINT;
BEGIN
    IF p_source IS NULL OR btrim(p_source) = '' THEN
        RAISE EXCEPTION 'upsert_official_act_resource: source is required';
    END IF;

    -- Prefer match by (source, resource_id)
    IF p_resource_id IS NOT NULL AND btrim(p_resource_id) <> '' THEN
        INSERT INTO public.official_act_resources AS r (
            source, resource_id, package_id, package_name, title, resource_url,
            format, content_sha256, etag, last_modified, size_bytes,
            run_id, last_fetched_at, fetch_status, metadata, last_seen_at
        ) VALUES (
            p_source, p_resource_id, p_package_id, p_package_name, p_title, p_resource_url,
            p_format, p_content_sha256, p_etag, p_last_modified, p_size_bytes,
            p_run_id,
            CASE WHEN p_fetch_status IN ('fetched', 'parsed') THEN NOW() ELSE NULL END,
            COALESCE(NULLIF(p_fetch_status, ''), 'discovered'),
            COALESCE(p_metadata, '{}'::jsonb),
            NOW()
        )
        ON CONFLICT (source, resource_id) WHERE resource_id IS NOT NULL
        DO UPDATE SET
            package_id = COALESCE(EXCLUDED.package_id, r.package_id),
            package_name = COALESCE(EXCLUDED.package_name, r.package_name),
            title = COALESCE(EXCLUDED.title, r.title),
            resource_url = COALESCE(EXCLUDED.resource_url, r.resource_url),
            format = COALESCE(EXCLUDED.format, r.format),
            content_sha256 = COALESCE(EXCLUDED.content_sha256, r.content_sha256),
            etag = COALESCE(EXCLUDED.etag, r.etag),
            last_modified = COALESCE(EXCLUDED.last_modified, r.last_modified),
            size_bytes = COALESCE(EXCLUDED.size_bytes, r.size_bytes),
            run_id = COALESCE(EXCLUDED.run_id, r.run_id),
            fetch_status = COALESCE(EXCLUDED.fetch_status, r.fetch_status),
            last_fetched_at = COALESCE(EXCLUDED.last_fetched_at, r.last_fetched_at),
            metadata = COALESCE(r.metadata, '{}'::jsonb) || COALESCE(EXCLUDED.metadata, '{}'::jsonb),
            last_seen_at = NOW(),
            updated_at = NOW()
        RETURNING id INTO v_id;
        RETURN v_id;
    END IF;

    -- Fallback: match by (source, content_sha256)
    IF p_content_sha256 IS NOT NULL AND btrim(p_content_sha256) <> '' THEN
        INSERT INTO public.official_act_resources AS r (
            source, resource_id, package_id, package_name, title, resource_url,
            format, content_sha256, etag, last_modified, size_bytes,
            run_id, last_fetched_at, fetch_status, metadata, last_seen_at
        ) VALUES (
            p_source, p_resource_id, p_package_id, p_package_name, p_title, p_resource_url,
            p_format, p_content_sha256, p_etag, p_last_modified, p_size_bytes,
            p_run_id,
            CASE WHEN p_fetch_status IN ('fetched', 'parsed') THEN NOW() ELSE NULL END,
            COALESCE(NULLIF(p_fetch_status, ''), 'discovered'),
            COALESCE(p_metadata, '{}'::jsonb),
            NOW()
        )
        ON CONFLICT (source, content_sha256) WHERE content_sha256 IS NOT NULL
        DO UPDATE SET
            resource_id = COALESCE(EXCLUDED.resource_id, r.resource_id),
            package_id = COALESCE(EXCLUDED.package_id, r.package_id),
            package_name = COALESCE(EXCLUDED.package_name, r.package_name),
            title = COALESCE(EXCLUDED.title, r.title),
            resource_url = COALESCE(EXCLUDED.resource_url, r.resource_url),
            format = COALESCE(EXCLUDED.format, r.format),
            etag = COALESCE(EXCLUDED.etag, r.etag),
            last_modified = COALESCE(EXCLUDED.last_modified, r.last_modified),
            size_bytes = COALESCE(EXCLUDED.size_bytes, r.size_bytes),
            run_id = COALESCE(EXCLUDED.run_id, r.run_id),
            fetch_status = COALESCE(EXCLUDED.fetch_status, r.fetch_status),
            last_fetched_at = COALESCE(EXCLUDED.last_fetched_at, r.last_fetched_at),
            metadata = COALESCE(r.metadata, '{}'::jsonb) || COALESCE(EXCLUDED.metadata, '{}'::jsonb),
            last_seen_at = NOW(),
            updated_at = NOW()
        RETURNING id INTO v_id;
        RETURN v_id;
    END IF;

    -- No unique key → plain insert
    INSERT INTO public.official_act_resources (
        source, resource_id, package_id, package_name, title, resource_url,
        format, content_sha256, etag, last_modified, size_bytes,
        run_id, fetch_status, metadata
    ) VALUES (
        p_source, p_resource_id, p_package_id, p_package_name, p_title, p_resource_url,
        p_format, p_content_sha256, p_etag, p_last_modified, p_size_bytes,
        p_run_id, COALESCE(NULLIF(p_fetch_status, ''), 'discovered'),
        COALESCE(p_metadata, '{}'::jsonb)
    )
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION public.upsert_official_act_resource IS
    'Idempotent upsert of official_act_resources by (source, resource_id) or (source, content_sha256).';

-- 8b. Batch upsert acts from JSONB array
CREATE OR REPLACE FUNCTION public.upsert_official_acts(p_records JSONB)
RETURNS TABLE (
    action      TEXT,
    act_id      BIGINT,
    record_hash TEXT,
    source      TEXT
)
LANGUAGE plpgsql
AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    WITH input AS (
        SELECT DISTINCT ON (
            COALESCE(rec->>'source', ''),
            COALESCE(rec->>'record_hash', '')
        )
            rec->>'source'                          AS in_source,
            NULLIF(rec->>'external_id', '')         AS external_id,
            rec->>'record_hash'                     AS in_record_hash,
            NULLIF(rec->>'content_hash', '')        AS content_hash,
            NULLIF(rec->>'resource_fk', '')::BIGINT AS resource_fk,
            NULLIF(rec->>'run_id', '')              AS run_id,
            NULLIF(rec->>'crawl_batch_id', '')      AS crawl_batch_id,
            NULLIF(rec->>'source_url', '')          AS source_url,
            NULLIF(rec->>'title', '')               AS title,
            NULLIF(rec->>'raw_text', '')            AS raw_text,
            CASE
                WHEN rec ? 'raw_json' AND jsonb_typeof(rec->'raw_json') <> 'null'
                THEN rec->'raw_json'
                ELSE NULL
            END                                     AS raw_json,
            NULLIF(rec->>'summary', '')             AS summary,
            NULLIF(rec->>'category', '')            AS category,
            NULLIF(rec->>'category_source', '')     AS category_source,
            NULLIF(rec->>'category_confidence', '') AS category_confidence,
            NULLIF(rec->>'classification_evidence', '') AS classification_evidence,
            NULLIF(rec->>'orgao_nome', '')          AS orgao_nome,
            NULLIF(rec->>'orgao_cnpj', '')          AS orgao_cnpj,
            NULLIF(rec->>'ente_federativo', '')    AS ente_federativo,
            NULLIF(rec->>'uf', '')                  AS uf,
            NULLIF(rec->>'municipio', '')           AS municipio,
            NULLIF(rec->>'codigo_ibge', '')         AS codigo_ibge,
            NULLIF(rec->>'publication_date', '')::DATE AS publication_date,
            NULLIF(rec->>'edition_date', '')::DATE AS edition_date,
            NULLIF(rec->>'event_date', '')::DATE   AS event_date,
            NULLIF(rec->>'date_semantics', '')     AS date_semantics,
            NULLIF(rec->>'edition_number', '')      AS edition_number,
            NULLIF(rec->>'page_number', '')         AS page_number,
            NULLIF(rec->>'section', '')             AS section,
            NULLIF(rec->>'process_number', '')      AS process_number,
            NULLIF(rec->>'edital_number', '')       AS edital_number,
            NULLIF(rec->>'contract_number', '')     AS contract_number,
            NULLIF(rec->>'related_pncp_id', '')     AS related_pncp_id,
            NULLIF(rec->>'related_contract_id', '') AS related_contract_id,
            COALESCE(NULLIF(rec->>'status', ''), 'active') AS status,
            CASE
                WHEN rec ? 'proveniencia' AND jsonb_typeof(rec->'proveniencia') = 'object'
                THEN rec->'proveniencia'
                ELSE '{}'::jsonb
            END                                     AS proveniencia,
            CASE
                WHEN rec ? 'metadata' AND jsonb_typeof(rec->'metadata') = 'object'
                THEN rec->'metadata'
                ELSE '{}'::jsonb
            END                                     AS metadata
        FROM jsonb_array_elements(p_records) AS rec
        WHERE COALESCE(rec->>'source', '') <> ''
          AND COALESCE(rec->>'record_hash', '') <> ''
        ORDER BY
            COALESCE(rec->>'source', ''),
            COALESCE(rec->>'record_hash', '')
    ),
    upserted AS (
        INSERT INTO public.official_acts AS t (
            source, external_id, record_hash, content_hash,
            resource_fk, run_id, crawl_batch_id, source_url,
            title, raw_text, raw_json, summary,
            category, category_source, category_confidence, classification_evidence,
            orgao_nome, orgao_cnpj, ente_federativo, uf, municipio, codigo_ibge,
            publication_date, edition_date, event_date, date_semantics,
            edition_number, page_number, section,
            process_number, edital_number, contract_number,
            related_pncp_id, related_contract_id,
            status, first_seen_at, last_seen_at, proveniencia, metadata
        )
        SELECT
            i.in_source, i.external_id, i.in_record_hash, i.content_hash,
            i.resource_fk, i.run_id, i.crawl_batch_id, i.source_url,
            i.title, i.raw_text, i.raw_json, i.summary,
            i.category, i.category_source, i.category_confidence, i.classification_evidence,
            i.orgao_nome, i.orgao_cnpj, i.ente_federativo, i.uf, i.municipio, i.codigo_ibge,
            i.publication_date, i.edition_date, i.event_date, i.date_semantics,
            i.edition_number, i.page_number, i.section,
            i.process_number, i.edital_number, i.contract_number,
            i.related_pncp_id, i.related_contract_id,
            i.status, NOW(), NOW(), i.proveniencia, i.metadata
        FROM input i
        ON CONFLICT (source, record_hash)
        DO UPDATE SET
            last_seen_at = NOW(),
            updated_at = NOW(),
            external_id = COALESCE(t.external_id, EXCLUDED.external_id),
            content_hash = COALESCE(EXCLUDED.content_hash, t.content_hash),
            resource_fk = COALESCE(EXCLUDED.resource_fk, t.resource_fk),
            run_id = COALESCE(EXCLUDED.run_id, t.run_id),
            crawl_batch_id = COALESCE(EXCLUDED.crawl_batch_id, t.crawl_batch_id),
            source_url = COALESCE(EXCLUDED.source_url, t.source_url),
            title = COALESCE(EXCLUDED.title, t.title),
            -- Prefer non-empty raw payload refresh
            raw_text = COALESCE(EXCLUDED.raw_text, t.raw_text),
            raw_json = COALESCE(EXCLUDED.raw_json, t.raw_json),
            summary = COALESCE(EXCLUDED.summary, t.summary),
            category = COALESCE(EXCLUDED.category, t.category),
            category_source = COALESCE(EXCLUDED.category_source, t.category_source),
            category_confidence = COALESCE(EXCLUDED.category_confidence, t.category_confidence),
            classification_evidence = COALESCE(EXCLUDED.classification_evidence, t.classification_evidence),
            orgao_nome = COALESCE(EXCLUDED.orgao_nome, t.orgao_nome),
            orgao_cnpj = COALESCE(EXCLUDED.orgao_cnpj, t.orgao_cnpj),
            ente_federativo = COALESCE(EXCLUDED.ente_federativo, t.ente_federativo),
            uf = COALESCE(EXCLUDED.uf, t.uf),
            municipio = COALESCE(EXCLUDED.municipio, t.municipio),
            codigo_ibge = COALESCE(EXCLUDED.codigo_ibge, t.codigo_ibge),
            -- Fill null semantic dates only; never clobber established values with NULL
            publication_date = COALESCE(t.publication_date, EXCLUDED.publication_date),
            edition_date = COALESCE(t.edition_date, EXCLUDED.edition_date),
            event_date = COALESCE(t.event_date, EXCLUDED.event_date),
            date_semantics = COALESCE(t.date_semantics, EXCLUDED.date_semantics),
            edition_number = COALESCE(EXCLUDED.edition_number, t.edition_number),
            page_number = COALESCE(EXCLUDED.page_number, t.page_number),
            section = COALESCE(EXCLUDED.section, t.section),
            process_number = COALESCE(EXCLUDED.process_number, t.process_number),
            edital_number = COALESCE(EXCLUDED.edital_number, t.edital_number),
            contract_number = COALESCE(EXCLUDED.contract_number, t.contract_number),
            related_pncp_id = COALESCE(EXCLUDED.related_pncp_id, t.related_pncp_id),
            related_contract_id = COALESCE(EXCLUDED.related_contract_id, t.related_contract_id),
            status = COALESCE(EXCLUDED.status, t.status),
            proveniencia = COALESCE(t.proveniencia, '{}'::jsonb) || COALESCE(EXCLUDED.proveniencia, '{}'::jsonb),
            metadata = COALESCE(t.metadata, '{}'::jsonb) || COALESCE(EXCLUDED.metadata, '{}'::jsonb),
            is_active = TRUE
        RETURNING t.id, t.record_hash, t.source, (xmax = 0) AS is_insert
    )
    SELECT
        CASE WHEN u.is_insert THEN 'inserted'::TEXT ELSE 'updated'::TEXT END,
        u.id,
        u.record_hash,
        u.source
    FROM upserted u;
END;
$$;

COMMENT ON FUNCTION public.upsert_official_acts(JSONB) IS
    'Batch upsert official_acts by (source, record_hash). Refreshes last_seen_at; fills null dates only.';

-- ==========================================================================
-- 9. Convenience view
-- ==========================================================================

CREATE OR REPLACE VIEW public.v_official_acts_active AS
SELECT
    a.id,
    a.source,
    a.external_id,
    a.record_hash,
    a.title,
    a.category,
    a.category_confidence,
    a.orgao_nome,
    a.orgao_cnpj,
    a.uf,
    a.municipio,
    a.codigo_ibge,
    a.publication_date,
    a.edition_date,
    a.event_date,
    a.date_semantics,
    a.process_number,
    a.edital_number,
    a.contract_number,
    a.status,
    a.source_url,
    a.run_id,
    a.resource_fk,
    r.resource_id   AS resource_external_id,
    r.package_name  AS resource_package_name,
    r.content_sha256 AS resource_sha256,
    a.first_seen_at,
    a.last_seen_at
FROM public.official_acts a
LEFT JOIN public.official_act_resources r ON r.id = a.resource_fk
WHERE a.is_active = TRUE
  AND a.status = 'active';

COMMENT ON VIEW public.v_official_acts_active IS
    'Active official acts with resource provenance columns.';

COMMIT;

-- ============================================================================
-- Safe rollback strategy (documented)
-- ============================================================================
-- Preferred: apply db/rollback/052_official_acts_rollback.sql
--
-- Manual (destructive — drops data):
--   DROP VIEW  IF EXISTS public.v_official_acts_active;
--   DROP FUNCTION IF EXISTS public.upsert_official_acts(JSONB);
--   DROP FUNCTION IF EXISTS public.upsert_official_act_resource(
--       TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
--       TIMESTAMPTZ, BIGINT, TEXT, TEXT, JSONB);
--   DROP TRIGGER IF EXISTS trg_oa_updated_at ON public.official_acts;
--   DROP TRIGGER IF EXISTS trg_oar_updated_at ON public.official_act_resources;
--   DROP FUNCTION IF EXISTS public.fn_official_acts_touch_updated_at();
--   DROP TABLE IF EXISTS public.official_act_matches CASCADE;
--   DROP TABLE IF EXISTS public.official_act_source_links CASCADE;
--   DROP TABLE IF EXISTS public.official_act_links CASCADE;
--   DROP TABLE IF EXISTS public.official_act_classifications CASCADE;
--   DROP TABLE IF EXISTS public.official_acts CASCADE;
--   DROP TABLE IF EXISTS public.official_act_resources CASCADE;
--
-- Non-destructive alternative: leave tables in place; disable writers
-- (crawlers) and stop inserting. Tables have no hard FK into legacy PNCP
-- tables so rollback does not break existing contracts/bids schema.
-- ============================================================================
