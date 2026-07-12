-- Migration 027: Opportunity Intelligence — Core Tables
--
-- Purpose: Track open bidding opportunities from official sources
-- within 200km of Florianópolis for Extra Construtora.
--
-- Tables created:
--   opportunity_intel        — core opportunity records
--   opportunity_checkpoints  — pagination checkpoints per source/scope
--   opportunity_runs         — crawl execution tracking
--   opportunity_coverage     — per-entity per-source coverage
--
-- Design:
--   - IDs stable across reruns (content_hash dedup)
--   - Status canonical: open, upcoming, closed, suspended, revoked,
--     annulled, failed, unknown
--   - Ranking deterministic: GO, REVIEW, NO_GO with score 0-100
--   - Proveniência tracked per field
--   - Fail-closed: never mark open just by recency
--
-- Follows patterns from:
--   pncp_raw_bids (001), ingestion_checkpoints (004),
--   entity_coverage (009), coverage_evidence (024)

BEGIN;

-- ==========================================================================
-- Table 1: opportunity_intel — Core opportunity records
-- ==========================================================================

CREATE TABLE IF NOT EXISTS opportunity_intel (
    -- Primary key
    id                  BIGSERIAL PRIMARY KEY,

    -- Identity & dedup
    source              TEXT NOT NULL,
    source_id           TEXT NOT NULL,
    source_url          TEXT,
    content_hash        TEXT NOT NULL,
    numero_controle_pncp TEXT,

    -- Execution tracking
    crawl_batch_id      TEXT,
    run_id              BIGINT,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Entity/orgão
    orgao_cnpj          TEXT,
    orgao_nome          TEXT,
    ente_federativo     TEXT,
    uf                  TEXT NOT NULL,
    municipio           TEXT,
    codigo_ibge         TEXT,

    -- Process identification (for dedup)
    numero_processo     TEXT,
    numero_edital       TEXT,
    modalidade          TEXT,
    modalidade_id       INTEGER,

    -- Object
    objeto              TEXT NOT NULL,
    categoria           TEXT,

    -- Value + semantics
    valor_estimado      NUMERIC(18,2),
    valor_homologado    NUMERIC(18,2),
    valor_semantica     TEXT,

    -- Dates
    data_publicacao     TIMESTAMPTZ,
    data_abertura       TIMESTAMPTZ,
    data_encerramento   TIMESTAMPTZ,
    data_homologacao    TIMESTAMPTZ,

    -- Status
    status_fonte        TEXT,
    status_canonico     TEXT NOT NULL DEFAULT 'unknown',
    status_motivo       TEXT,
    status_data         TIMESTAMPTZ,

    -- Documents
    link_edital         TEXT,
    link_anexos         TEXT[],

    -- Quality
    qualidade_score     INTEGER DEFAULT 0,
    qualidade_fatores   JSONB DEFAULT '{}',
    dados_ausentes      TEXT[],

    -- Ranking
    ranking             TEXT DEFAULT 'REVIEW',
    ranking_score       INTEGER DEFAULT 0,
    ranking_fatores     JSONB DEFAULT '{}',
    ranking_regras      TEXT[],
    ranking_confianca   TEXT DEFAULT 'MEDIUM',

    -- Provenance
    proveniencia        JSONB DEFAULT '{}',

    -- Metadata
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    metadata            JSONB DEFAULT '{}'
);

-- ==========================================================================
-- Constraints
-- ==========================================================================

-- Unique content hash for dedup
ALTER TABLE opportunity_intel
    ADD CONSTRAINT uq_oi_content_hash UNIQUE (content_hash);

-- Status canonical check
ALTER TABLE opportunity_intel
    ADD CONSTRAINT ck_oi_status_canonico CHECK (
        status_canonico IN (
            'open', 'upcoming', 'closed', 'suspended',
            'revoked', 'annulled', 'failed', 'unknown'
        )
    );

-- Ranking check
ALTER TABLE opportunity_intel
    ADD CONSTRAINT ck_oi_ranking CHECK (
        ranking IN ('GO', 'REVIEW', 'NO_GO')
    );

-- Ranking confidence check
ALTER TABLE opportunity_intel
    ADD CONSTRAINT ck_oi_ranking_confianca CHECK (
        ranking_confianca IN ('HIGH', 'MEDIUM', 'LOW')
    );

-- Ranking score range
ALTER TABLE opportunity_intel
    ADD CONSTRAINT ck_oi_ranking_score CHECK (
        ranking_score >= 0 AND ranking_score <= 100
    );

-- Quality score range
ALTER TABLE opportunity_intel
    ADD CONSTRAINT ck_oi_qualidade_score CHECK (
        qualidade_score >= 0 AND qualidade_score <= 100
    );

-- ==========================================================================
-- Table 2: opportunity_checkpoints — Pagination resumption
-- ==========================================================================

CREATE TABLE IF NOT EXISTS opportunity_checkpoints (
    source          TEXT NOT NULL,
    scope_key       TEXT NOT NULL,
    last_page       INTEGER,
    last_date       DATE,
    last_id         TEXT,
    records_fetched INTEGER DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (source, scope_key)
);

-- ==========================================================================
-- Table 3: opportunity_runs — Crawl execution audit trail
-- ==========================================================================

CREATE TABLE IF NOT EXISTS opportunity_runs (
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

-- Run status check
ALTER TABLE opportunity_runs
    ADD CONSTRAINT ck_or_status CHECK (
        status IN ('running', 'completed', 'completed_zero', 'failed', 'partial')
    );

-- ==========================================================================
-- Table 4: opportunity_coverage — Per-entity per-source coverage
-- ==========================================================================

CREATE TABLE IF NOT EXISTS opportunity_coverage (
    entity_id         INTEGER NOT NULL REFERENCES sc_public_entities(id),
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

-- Coverage result check
ALTER TABLE opportunity_coverage
    ADD CONSTRAINT ck_oc_result CHECK (
        result IN ('success', 'success_zero', 'partial', 'error', 'pending')
    );

-- ==========================================================================
-- Trigger: auto-update updated_at on opportunity_intel
-- ==========================================================================

CREATE OR REPLACE FUNCTION trg_oi_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_opportunity_intel_updated_at ON opportunity_intel;
CREATE TRIGGER trg_opportunity_intel_updated_at
    BEFORE UPDATE ON opportunity_intel
    FOR EACH ROW
    EXECUTE FUNCTION trg_oi_updated_at();

-- ==========================================================================
-- Trigger: auto-update last_seen_at on re-ingestion
-- ==========================================================================

CREATE OR REPLACE FUNCTION trg_oi_last_seen()
RETURNS TRIGGER AS $$
BEGIN
    NEW.last_seen_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_opportunity_intel_last_seen ON opportunity_intel;
CREATE TRIGGER trg_opportunity_intel_last_seen
    BEFORE UPDATE ON opportunity_intel
    FOR EACH ROW
    EXECUTE FUNCTION trg_oi_last_seen();

-- ==========================================================================
-- Function: upsert_opportunity_intel(batch JSONB)
-- ==========================================================================

CREATE OR REPLACE FUNCTION upsert_opportunity_intel(batch JSONB)
RETURNS TABLE(
    action TEXT,
    record_id BIGINT,
    content_hash TEXT
) AS $$
DECLARE
    rec JSONB;
BEGIN
    FOR rec IN SELECT * FROM jsonb_array_elements(batch)
    LOOP
        INSERT INTO opportunity_intel (
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
            numero_controle_pncp = COALESCE(EXCLUDED.numero_controle_pncp, opportunity_intel.numero_controle_pncp),
            crawl_batch_id = EXCLUDED.crawl_batch_id,
            run_id = EXCLUDED.run_id,
            last_seen_at = NOW(),
            orgao_cnpj = COALESCE(EXCLUDED.orgao_cnpj, opportunity_intel.orgao_cnpj),
            orgao_nome = COALESCE(EXCLUDED.orgao_nome, opportunity_intel.orgao_nome),
            uf = COALESCE(EXCLUDED.uf, opportunity_intel.uf),
            municipio = COALESCE(EXCLUDED.municipio, opportunity_intel.municipio),
            codigo_ibge = COALESCE(EXCLUDED.codigo_ibge, opportunity_intel.codigo_ibge),
            numero_processo = COALESCE(EXCLUDED.numero_processo, opportunity_intel.numero_processo),
            numero_edital = COALESCE(EXCLUDED.numero_edital, opportunity_intel.numero_edital),
            modalidade = COALESCE(EXCLUDED.modalidade, opportunity_intel.modalidade),
            modalidade_id = COALESCE(EXCLUDED.modalidade_id, opportunity_intel.modalidade_id),
            objeto = COALESCE(EXCLUDED.objeto, opportunity_intel.objeto),
            categoria = COALESCE(EXCLUDED.categoria, opportunity_intel.categoria),
            valor_estimado = COALESCE(EXCLUDED.valor_estimado, opportunity_intel.valor_estimado),
            valor_homologado = COALESCE(EXCLUDED.valor_homologado, opportunity_intel.valor_homologado),
            valor_semantica = COALESCE(EXCLUDED.valor_semantica, opportunity_intel.valor_semantica),
            data_publicacao = COALESCE(EXCLUDED.data_publicacao, opportunity_intel.data_publicacao),
            data_abertura = COALESCE(EXCLUDED.data_abertura, opportunity_intel.data_abertura),
            data_encerramento = COALESCE(EXCLUDED.data_encerramento, opportunity_intel.data_encerramento),
            data_homologacao = COALESCE(EXCLUDED.data_homologacao, opportunity_intel.data_homologacao),
            status_fonte = EXCLUDED.status_fonte,
            status_canonico = EXCLUDED.status_canonico,
            status_motivo = EXCLUDED.status_motivo,
            status_data = EXCLUDED.status_data,
            link_edital = COALESCE(EXCLUDED.link_edital, opportunity_intel.link_edital),
            link_anexos = COALESCE(EXCLUDED.link_anexos, opportunity_intel.link_anexos),
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
            (CASE WHEN xmax = 0 THEN 'insert' ELSE 'update' END)::TEXT AS action,
            id AS record_id,
            content_hash
        INTO action, record_id, content_hash;

        RETURN NEXT;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- ==========================================================================
-- View: v_opportunity_open — Open/upcoming opportunities within 200km
-- ==========================================================================

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
  AND oi.is_active = TRUE;

-- ==========================================================================
-- View: v_opportunity_by_source — Count summary by source
-- ==========================================================================

CREATE OR REPLACE VIEW v_opportunity_by_source AS
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
FROM opportunity_intel
WHERE is_active = TRUE
GROUP BY source, status_canonico
ORDER BY source, status_canonico;

-- ==========================================================================
-- View: v_opportunity_coverage_summary — Coverage dashboard
-- ==========================================================================

CREATE OR REPLACE VIEW v_opportunity_coverage_summary AS
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
FROM opportunity_coverage oc
GROUP BY oc.source
ORDER BY oc.source;

COMMIT;
