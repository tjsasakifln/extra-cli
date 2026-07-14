-- ============================================================
-- Auto-generated baseline schema
-- Generated from all migrations in db/migrations/
-- Date: 2026-07-14
-- Total migrations: 46
-- WARNING: This file is auto-generated. Do not edit manually.
-- To regenerate: merge all db/migrations/*.sql in sorted order.
-- ============================================================


-- ============================================================
-- Migration: 001_pncp_raw_bids.sql
-- ============================================================
-- Migration 001: Core bids table (multi-source unified)
-- Based on smartlic.tech pncp_raw_bids schema, simplified for single-user

CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE pncp_raw_bids (
    pncp_id         TEXT PRIMARY KEY,
    objeto_compra   TEXT,
    valor_total_estimado NUMERIC(18,2),
    modalidade_id   INT,
    modalidade_nome TEXT,
    esfera_id       INT,
    uf              TEXT,
    municipio       TEXT,
    codigo_municipio_ibge TEXT,
    orgao_razao_social TEXT,
    orgao_cnpj      TEXT,
    data_publicacao DATE,
    data_abertura   DATE,
    data_encerramento DATE,
    link_pncp       TEXT,
    content_hash    TEXT UNIQUE,                  -- dedup across sources
    tsv             TSVECTOR,                     -- pre-computed full-text search (PT-BR)
    source          TEXT NOT NULL DEFAULT 'pncp', -- 'pncp'|'dom_sc'|'pcp'|'compras_gov'|'sc_compras'
    source_id       TEXT,                         -- original ID at source
    matched_entity_id INT,                        -- FK → sc_public_entities (added in 007)
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE
);

-- Full-text search index (Portuguese)
CREATE INDEX idx_bids_tsv ON pncp_raw_bids USING GIN (tsv);

-- Common query indexes
CREATE INDEX idx_bids_uf_data ON pncp_raw_bids (uf, data_publicacao DESC);
CREATE INDEX idx_bids_modalidade ON pncp_raw_bids (modalidade_id, data_publicacao DESC);
CREATE INDEX idx_bids_valor ON pncp_raw_bids (valor_total_estimado);
CREATE INDEX idx_bids_esfera ON pncp_raw_bids (esfera_id);
CREATE INDEX idx_bids_encerramento ON pncp_raw_bids (data_encerramento)
    WHERE data_encerramento IS NOT NULL;
CREATE INDEX idx_bids_source ON pncp_raw_bids (source);
CREATE INDEX idx_bids_orgao_cnpj ON pncp_raw_bids (orgao_cnpj);
CREATE INDEX idx_bids_matched_entity ON pncp_raw_bids (matched_entity_id)
    WHERE matched_entity_id IS NOT NULL;
CREATE INDEX idx_bids_ingested ON pncp_raw_bids (ingested_at DESC);

-- Soft-delete index (exclude inactive from most queries)
CREATE INDEX idx_bids_active ON pncp_raw_bids (is_active, data_publicacao DESC)
    WHERE is_active = TRUE;

-- Trigger: auto-update updated_at
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_bids_updated_at
    BEFORE UPDATE ON pncp_raw_bids
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- Migration: 002_pncp_supplier_contracts.sql
-- ============================================================
-- Migration 002: Supplier contracts table
-- Tracks all contracts published on PNCP, indexed by supplier CNPJ

CREATE TABLE pncp_supplier_contracts (
    id              SERIAL PRIMARY KEY,
    contrato_id     TEXT UNIQUE,                  -- external contract identifier
    orgao_cnpj      TEXT,                         -- contracting authority CNPJ
    orgao_nome      TEXT,                         -- contracting authority name
    fornecedor_cnpj TEXT,                         -- supplier CNPJ (indexed!)
    fornecedor_nome TEXT,                         -- supplier name
    objeto_contrato TEXT,                         -- contract object description
    valor_total     NUMERIC(18,2),
    data_inicio     DATE,
    data_fim        DATE,
    data_publicacao DATE,
    uf              TEXT,
    municipio       TEXT,
    source          TEXT NOT NULL DEFAULT 'pncp', -- data source
    source_id       TEXT,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- High-performance indexes for competitor analysis
CREATE INDEX idx_psc_fornecedor ON pncp_supplier_contracts (fornecedor_cnpj, data_publicacao DESC);
CREATE INDEX idx_psc_orgao ON pncp_supplier_contracts (orgao_cnpj);
CREATE INDEX idx_psc_uf ON pncp_supplier_contracts (uf, data_publicacao DESC);
CREATE INDEX idx_psc_valor ON pncp_supplier_contracts (valor_total);
CREATE INDEX idx_psc_objeto_trgm ON pncp_supplier_contracts USING GIN (objeto_contrato gin_trgm_ops);
CREATE INDEX idx_psc_data ON pncp_supplier_contracts (data_publicacao DESC);


-- ============================================================
-- Migration: 003_enriched_entities.sql
-- ============================================================
-- Migration 003: Enriched entities cache
-- Stores BrasilAPI + IBGE enrichment results with TTL

CREATE TABLE enriched_entities (
    cnpj            TEXT PRIMARY KEY,
    razao_social    TEXT,
    nome_fantasia   TEXT,
    cnae_principal  TEXT,
    cnae_secundarios TEXT[],
    municipio       TEXT,
    uf              TEXT,
    codigo_ibge     TEXT,
    natureza_juridica TEXT,
    logradouro      TEXT,
    bairro          TEXT,
    cep             TEXT,
    telefone        TEXT,
    email           TEXT,
    situacao        TEXT,                         -- 'ATIVA'|'INATIVA'|etc.
    enriched_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    enriched_source TEXT NOT NULL DEFAULT 'brasilapi'
);

-- TTL index: find stale entries (>30 days)
CREATE INDEX idx_ee_enriched_at ON enriched_entities (enriched_at);
CREATE INDEX idx_ee_uf ON enriched_entities (uf);


-- ============================================================
-- Migration: 004_ingestion_tables.sql
-- ============================================================
-- Migration 004: Ingestion tracking tables
-- Checkpoints for resumable crawls + audit trail

-- Resumable ingestion checkpoints (one per source+scope)
CREATE TABLE ingestion_checkpoints (
    source          TEXT NOT NULL DEFAULT 'pncp', -- 'pncp'|'dom_sc'|'pcp'|'compras_gov'
    scope_key       TEXT NOT NULL,                -- uf, municipality, or modality identifier
    last_page       INT NOT NULL DEFAULT 0,
    last_date       DATE,
    last_id         TEXT,                         -- last seen record ID (source-specific)
    records_fetched INT NOT NULL DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (source, scope_key)
);

-- Audit trail: every ingestion run
CREATE TABLE ingestion_runs (
    id              SERIAL PRIMARY KEY,
    source          TEXT NOT NULL,                -- 'pncp'|'dom_sc'|'pcp'|'compras_gov'|'sc_compras'
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    records_fetched INT NOT NULL DEFAULT 0,
    records_upserted INT NOT NULL DEFAULT 0,
    entities_covered INT NOT NULL DEFAULT 0,      -- how many sc_public_entities matched
    status          TEXT NOT NULL DEFAULT 'running', -- 'running'|'completed'|'failed'
    error_message   TEXT,
    metadata        JSONB                         -- extra context (UF list, date range, etc.)
);

CREATE INDEX idx_ir_source_status ON ingestion_runs (source, status);
CREATE INDEX idx_ir_started ON ingestion_runs (started_at DESC);


-- ============================================================
-- Migration: 005_search_datalake_rpc.sql
-- ============================================================
-- Migration 005: search_datalake RPC
-- Multi-filter full-text search in Portuguese
-- Ported from smartlic.tech supabase/migrations

CREATE OR REPLACE FUNCTION search_datalake(
    p_ufs          TEXT[]   DEFAULT NULL,
    p_date_start   DATE     DEFAULT NULL,
    p_date_end     DATE     DEFAULT NULL,
    p_tsquery      TEXT     DEFAULT NULL,
    p_modalidades  INT[]    DEFAULT NULL,
    p_valor_min    NUMERIC  DEFAULT NULL,
    p_valor_max    NUMERIC  DEFAULT NULL,
    p_esferas      INT[]    DEFAULT NULL,
    p_sources      TEXT[]   DEFAULT NULL,
    p_limit        INT      DEFAULT 100
)
RETURNS TABLE (
    pncp_id              TEXT,
    objeto_compra        TEXT,
    valor_total_estimado NUMERIC,
    modalidade_nome      TEXT,
    uf                   TEXT,
    municipio            TEXT,
    orgao_razao_social   TEXT,
    orgao_cnpj           TEXT,
    data_publicacao      DATE,
    data_encerramento    DATE,
    link_pncp            TEXT,
    source               TEXT,
    rank                 REAL
) LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        b.pncp_id,
        b.objeto_compra,
        b.valor_total_estimado,
        b.modalidade_nome,
        b.uf,
        b.municipio,
        b.orgao_razao_social,
        b.orgao_cnpj,
        b.data_publicacao,
        b.data_encerramento,
        b.link_pncp,
        b.source,
        CASE
            WHEN p_tsquery IS NOT NULL AND b.tsv IS NOT NULL
            THEN ts_rank(b.tsv, to_tsquery('portuguese', p_tsquery))
            ELSE 0.0
        END AS rank
    FROM pncp_raw_bids b
    WHERE b.is_active = TRUE
      AND (p_ufs IS NULL OR b.uf = ANY(p_ufs))
      AND (p_date_start IS NULL OR b.data_publicacao >= p_date_start)
      AND (p_date_end IS NULL OR b.data_publicacao <= p_date_end)
      AND (p_modalidades IS NULL OR b.modalidade_id = ANY(p_modalidades))
      AND (p_valor_min IS NULL OR b.valor_total_estimado >= p_valor_min)
      AND (p_valor_max IS NULL OR b.valor_total_estimado <= p_valor_max)
      AND (p_esferas IS NULL OR b.esfera_id = ANY(p_esferas))
      AND (p_sources IS NULL OR b.source = ANY(p_sources))
      AND (
          p_tsquery IS NULL
          OR b.tsv @@ to_tsquery('portuguese', p_tsquery)
          OR b.objeto_compra ILIKE '%' || p_tsquery || '%'
      )
    ORDER BY
        CASE WHEN p_tsquery IS NOT NULL
             THEN ts_rank(b.tsv, to_tsquery('portuguese', p_tsquery))
             ELSE 0.0
        END DESC,
        b.data_publicacao DESC
    LIMIT p_limit;
END;
$$;


-- ============================================================
-- Migration: 006_upsert_rpcs.sql
-- ============================================================
-- Migration 006: Upsert RPCs — Set-Based
-- Batch upsert with dedup by content_hash
--
-- Refatorado em Story 1.2 (Task 7): FOR loop → SET-BASED (INSERT ... SELECT)
-- Performance: <= 30% do tempo do row-by-row original (AC #10 / DT-05)
--
-- Principios do refactoring set-based:
--   1. Uma unica instrucao INSERT/SELECT processa TODOS os registros
--   2. Sem cursor/FOR loop — PostgreSQL otimiza o plano de execucao
--   3. CTE de saida retorna acao por registro (inserted/skipped/updated)
--   4. Idempotente: CREATE OR REPLACE FUNCTION
--
-- Batch upsert for bids (multi-source)
CREATE OR REPLACE FUNCTION upsert_pncp_raw_bids(p_records JSONB)
RETURNS TABLE (
    action      TEXT,
    pncp_id     TEXT,
    content_hash TEXT
) LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    WITH input AS (
        SELECT
            rec->>'pncp_id' AS pncp_id,
            rec->>'objeto_compra' AS objeto_compra,
            (rec->>'valor_total_estimado')::NUMERIC AS valor_total_estimado,
            (rec->>'modalidade_id')::INT AS modalidade_id,
            rec->>'modalidade_nome' AS modalidade_nome,
            (rec->>'esfera_id')::INT AS esfera_id,
            rec->>'uf' AS uf,
            rec->>'municipio' AS municipio,
            rec->>'codigo_municipio_ibge' AS codigo_municipio_ibge,
            rec->>'orgao_razao_social' AS orgao_razao_social,
            rec->>'orgao_cnpj' AS orgao_cnpj,
            (rec->>'data_publicacao')::DATE AS data_publicacao,
            (rec->>'data_abertura')::DATE AS data_abertura,
            (rec->>'data_encerramento')::DATE AS data_encerramento,
            rec->>'link_pncp' AS link_pncp,
            rec->>'content_hash' AS content_hash,
            COALESCE(rec->>'source', 'pncp') AS source,
            rec->>'source_id' AS source_id
        FROM jsonb_array_elements(p_records) AS rec
    ),
    inserted AS (
        INSERT INTO pncp_raw_bids (
            pncp_id, objeto_compra, valor_total_estimado,
            modalidade_id, modalidade_nome, esfera_id,
            uf, municipio, codigo_municipio_ibge,
            orgao_razao_social, orgao_cnpj,
            data_publicacao, data_abertura, data_encerramento,
            link_pncp, content_hash, tsv,
            source, source_id
        )
        SELECT
            i.pncp_id, i.objeto_compra, i.valor_total_estimado,
            i.modalidade_id, i.modalidade_nome, i.esfera_id,
            i.uf, i.municipio, i.codigo_municipio_ibge,
            i.orgao_razao_social, i.orgao_cnpj,
            i.data_publicacao, i.data_abertura, i.data_encerramento,
            i.link_pncp, i.content_hash,
            to_tsvector('portuguese', COALESCE(i.objeto_compra, '')),
            i.source, i.source_id
        FROM input i
        WHERE NOT EXISTS (
            SELECT 1 FROM pncp_raw_bids t
            WHERE t.content_hash = i.content_hash
        )
        ON CONFLICT ON CONSTRAINT pncp_raw_bids_content_hash_key DO NOTHING
        RETURNING pncp_id, content_hash
    )
    SELECT 'inserted'::TEXT, i.pncp_id, i.content_hash
    FROM inserted i
    UNION ALL
    SELECT 'skipped'::TEXT, i.pncp_id, i.content_hash
    FROM input i
    WHERE EXISTS (
        SELECT 1 FROM pncp_raw_bids t
        WHERE t.content_hash = i.content_hash
    );
END;
$$;

-- Batch upsert for supplier contracts — SET-BASED
-- Refatorado de FOR loop para INSERT ... SELECT (Story 1.2, Task 7)
CREATE OR REPLACE FUNCTION upsert_pncp_supplier_contracts(p_records JSONB)
RETURNS TABLE (
    action      TEXT,
    contrato_id TEXT
) LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    WITH input AS (
        SELECT
            rec->>'contrato_id' AS contrato_id,
            rec->>'orgao_cnpj' AS orgao_cnpj,
            rec->>'orgao_nome' AS orgao_nome,
            rec->>'fornecedor_cnpj' AS fornecedor_cnpj,
            rec->>'fornecedor_nome' AS fornecedor_nome,
            rec->>'objeto_contrato' AS objeto_contrato,
            (rec->>'valor_total')::NUMERIC AS valor_total,
            (rec->>'data_inicio')::DATE AS data_inicio,
            (rec->>'data_fim')::DATE AS data_fim,
            (rec->>'data_publicacao')::DATE AS data_publicacao,
            rec->>'uf' AS uf,
            rec->>'municipio' AS municipio,
            COALESCE(rec->>'source', 'pncp') AS source,
            rec->>'source_id' AS source_id
        FROM jsonb_array_elements(p_records) AS rec
    ),
    inserted AS (
        INSERT INTO pncp_supplier_contracts (
            contrato_id, orgao_cnpj, orgao_nome,
            fornecedor_cnpj, fornecedor_nome,
            objeto_contrato, valor_total,
            data_inicio, data_fim, data_publicacao,
            uf, municipio, source, source_id
        )
        SELECT
            i.contrato_id, i.orgao_cnpj, i.orgao_nome,
            i.fornecedor_cnpj, i.fornecedor_nome,
            i.objeto_contrato, i.valor_total,
            i.data_inicio, i.data_fim, i.data_publicacao,
            i.uf, i.municipio, i.source, i.source_id
        FROM input i
        WHERE NOT EXISTS (
            SELECT 1 FROM pncp_supplier_contracts t
            WHERE t.contrato_id = i.contrato_id
        )
        ON CONFLICT (contrato_id) DO NOTHING
        RETURNING contrato_id
    )
    SELECT 'inserted'::TEXT, i.contrato_id
    FROM inserted i
    UNION ALL
    SELECT 'skipped'::TEXT, i.contrato_id
    FROM input i
    WHERE EXISTS (
        SELECT 1 FROM pncp_supplier_contracts t
        WHERE t.contrato_id = i.contrato_id
    );
END;
$$;


-- ============================================================
-- Migration: 007_sc_public_entities.sql
-- ============================================================
-- Migration 007: SC Public Entities table
-- From spreadsheet "Extra - alvos de licitação. R-0.xlsx"
-- 2,085 public entities in Santa Catarina state

CREATE TABLE sc_public_entities (
    id                  SERIAL PRIMARY KEY,
    razao_social        TEXT NOT NULL,
    cnpj_8              TEXT NOT NULL,              -- 8-digit CNPJ base (raiz)
    municipio           TEXT,
    codigo_ibge         TEXT,                       -- 7-digit IBGE municipality code
    natureza_juridica   TEXT,                       -- legal nature description
    cod_natureza        TEXT,                       -- legal nature code
    latitude            DOUBLE PRECISION,
    longitude           DOUBLE PRECISION,
    distancia_fk        DOUBLE PRECISION,           -- distance from Florianópolis (km)
    raio_200km          BOOLEAN NOT NULL DEFAULT FALSE,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Search indexes
CREATE INDEX idx_spe_cnpj ON sc_public_entities (cnpj_8);
CREATE INDEX idx_spe_municipio ON sc_public_entities (municipio);
CREATE INDEX idx_spe_ibge ON sc_public_entities (codigo_ibge);
CREATE INDEX idx_spe_raio ON sc_public_entities (raio_200km, is_active);
CREATE INDEX idx_spe_natureza ON sc_public_entities (cod_natureza);

-- Foreign key from bids table
ALTER TABLE pncp_raw_bids
    ADD CONSTRAINT fk_bids_matched_entity
    FOREIGN KEY (matched_entity_id)
    REFERENCES sc_public_entities(id)
    ON DELETE SET NULL;


-- ============================================================
-- Migration: 008_purge_rpc.sql
-- ============================================================
-- Migration 008: Purge RPC and entity coverage tracking

-- Purge old bids (soft-delete) — retention in days
CREATE OR REPLACE FUNCTION purge_old_bids(p_retention_days INT DEFAULT 400)
RETURNS TABLE (
    purged_count INT,
    remaining_count INT
) LANGUAGE plpgsql AS $$
DECLARE
    cutoff_date DATE;
    v_purged INT;
BEGIN
    cutoff_date := CURRENT_DATE - p_retention_days;

    -- Soft-delete old inactive records
    UPDATE pncp_raw_bids
    SET is_active = FALSE
    WHERE is_active = TRUE
      AND data_publicacao < cutoff_date;

    GET DIAGNOSTICS v_purged = ROW_COUNT;

    RETURN QUERY
    SELECT
        v_purged,
        COUNT(*)::INT
    FROM pncp_raw_bids
    WHERE is_active = TRUE;
END;
$$;


-- ============================================================
-- Migration: 009_indexes_and_coverage.sql
-- ============================================================
-- Migration 009: Entity coverage tracking + indexes

-- Coverage tracking per entity per source
CREATE TABLE entity_coverage (
    entity_id       INT NOT NULL REFERENCES sc_public_entities(id) ON DELETE CASCADE,
    source          TEXT NOT NULL,                  -- 'pncp'|'dom_sc'|'pcp'|'compras_gov'|'sc_compras'|'tce_sc'|'transparencia'
    last_seen_at    TIMESTAMPTZ,                   -- last time this entity appeared in this source
    total_bids      INT NOT NULL DEFAULT 0,         -- total bids collected from this entity
    is_covered      BOOLEAN NOT NULL DEFAULT FALSE, -- has publications in last 90 days?
    within_200km    BOOLEAN NOT NULL DEFAULT FALSE, -- denormalized from sc_public_entities
    PRIMARY KEY (entity_id, source)
);

-- Fast gap detection queries
CREATE INDEX idx_cov_covered ON entity_coverage (is_covered, within_200km);
CREATE INDEX idx_cov_last_seen ON entity_coverage (last_seen_at);
CREATE INDEX idx_cov_source ON entity_coverage (source, is_covered);

-- Update entity_coverage after bid insert
CREATE OR REPLACE FUNCTION update_entity_coverage()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.matched_entity_id IS NOT NULL THEN
        INSERT INTO entity_coverage (entity_id, source, last_seen_at, total_bids, is_covered, within_200km)
        VALUES (
            NEW.matched_entity_id,
            NEW.source,
            NEW.data_publicacao,
            1,
            COALESCE(NEW.data_publicacao >= CURRENT_DATE - 90, FALSE),
            COALESCE((SELECT raio_200km FROM sc_public_entities WHERE id = NEW.matched_entity_id), FALSE)
        )
        ON CONFLICT (entity_id, source) DO UPDATE
        SET
            last_seen_at = GREATEST(
                COALESCE(entity_coverage.last_seen_at, '1970-01-01'::date),
                COALESCE(NEW.data_publicacao, '1970-01-01'::date)
            ),
            total_bids = entity_coverage.total_bids + 1,
            is_covered = (
                GREATEST(
                    COALESCE(entity_coverage.last_seen_at, '1970-01-01'::date),
                    COALESCE(NEW.data_publicacao, '1970-01-01'::date)
                ) >= CURRENT_DATE - 90
            );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- INSERT trigger
CREATE TRIGGER trg_bids_coverage
    AFTER INSERT ON pncp_raw_bids
    FOR EACH ROW
    EXECUTE FUNCTION update_entity_coverage();

-- UPDATE trigger (when matched_entity_id is set after initial insert)
CREATE OR REPLACE FUNCTION update_entity_coverage_on_update()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.matched_entity_id IS NOT NULL AND (OLD.matched_entity_id IS NULL OR OLD.matched_entity_id <> NEW.matched_entity_id) THEN
        INSERT INTO entity_coverage (entity_id, source, last_seen_at, total_bids, is_covered, within_200km)
        VALUES (
            NEW.matched_entity_id,
            NEW.source,
            NEW.data_publicacao,
            1,
            COALESCE(NEW.data_publicacao >= CURRENT_DATE - 90, FALSE),
            COALESCE((SELECT raio_200km FROM sc_public_entities WHERE id = NEW.matched_entity_id), FALSE)
        )
        ON CONFLICT (entity_id, source) DO UPDATE
        SET
            last_seen_at = GREATEST(
                COALESCE(entity_coverage.last_seen_at, '1970-01-01'::date),
                COALESCE(NEW.data_publicacao, '1970-01-01'::date)
            ),
            total_bids = entity_coverage.total_bids + 1,
            is_covered = (
                GREATEST(
                    COALESCE(entity_coverage.last_seen_at, '1970-01-01'::date),
                    COALESCE(NEW.data_publicacao, '1970-01-01'::date)
                ) >= CURRENT_DATE - 90
            );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_bids_coverage_update
    AFTER UPDATE ON pncp_raw_bids
    FOR EACH ROW
    EXECUTE FUNCTION update_entity_coverage_on_update();

-- Initialize coverage for all entities (will be populated by triggers)
INSERT INTO entity_coverage (entity_id, source, is_covered, within_200km)
SELECT
    e.id,
    'pncp',
    FALSE,
    e.raio_200km
FROM sc_public_entities e
ON CONFLICT (entity_id, source) DO NOTHING;

INSERT INTO entity_coverage (entity_id, source, is_covered, within_200km)
SELECT
    e.id,
    'dom_sc',
    FALSE,
    e.raio_200km
FROM sc_public_entities e
ON CONFLICT (entity_id, source) DO NOTHING;

INSERT INTO entity_coverage (entity_id, source, is_covered, within_200km)
SELECT
    e.id,
    'pcp',
    FALSE,
    e.raio_200km
FROM sc_public_entities e
ON CONFLICT (entity_id, source) DO NOTHING;

INSERT INTO entity_coverage (entity_id, source, is_covered, within_200km)
SELECT
    e.id,
    'compras_gov',
    FALSE,
    e.raio_200km
FROM sc_public_entities e
ON CONFLICT (entity_id, source) DO NOTHING;

-- Additional performance indexes
CREATE INDEX idx_bids_orgao_hash ON pncp_raw_bids (orgao_cnpj, content_hash);
CREATE INDEX idx_bids_uf_source ON pncp_raw_bids (uf, source, data_publicacao DESC);

-- Verify coverage (utility view)
CREATE OR REPLACE VIEW v_coverage_summary AS
SELECT
    ec.source,
    ec.within_200km,
    ec.is_covered,
    COUNT(*) AS entity_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY ec.within_200km), 1) AS pct
FROM entity_coverage ec
WHERE EXISTS (SELECT 1 FROM sc_public_entities e WHERE e.id = ec.entity_id AND e.is_active = TRUE)
GROUP BY ec.source, ec.within_200km, ec.is_covered
ORDER BY ec.source, ec.within_200km, ec.is_covered;


-- ============================================================
-- Migration: 010_match_logging.sql
-- ============================================================
-- Migration 010: Match logging columns for entity name-matching refinement
-- Story 001.3: Entity Name-Matching Refinement
--
-- Adiciona colunas de metadata de matching à pncp_raw_bids para rastrear
-- qual estratégia (CNPJ, nome normalizado, fuzzy) foi usada e qual a
-- confiança do match.
--
-- Uso no monitor.py:
--   _match_entities_cascade() grava estas colunas após cada tentativa de match

-- Add match-method column (which strategy produced the match)
ALTER TABLE pncp_raw_bids
    ADD COLUMN IF NOT EXISTS match_method TEXT;

-- Add match-score column (0.000 = no match, 1.000 = exact)
ALTER TABLE pncp_raw_bids
    ADD COLUMN IF NOT EXISTS match_score DECIMAL(4,3);

-- Add match-confidence column (high, medium, low)
ALTER TABLE pncp_raw_bids
    ADD COLUMN IF NOT EXISTS match_confidence TEXT;

-- Index for analysing match quality / debugging unmatched bids
CREATE INDEX IF NOT EXISTS idx_bids_match_method
    ON pncp_raw_bids (match_method)
    WHERE match_method IS NOT NULL;

-- Composite index for coverage analysis: which methods are producing matches
CREATE INDEX IF NOT EXISTS idx_bids_match_coverage
    ON pncp_raw_bids (match_method, matched_entity_id)
    WHERE matched_entity_id IS NOT NULL;

COMMENT ON COLUMN pncp_raw_bids.match_method IS
    'Estrategia de matching: cnpj | name_normalized | fuzzy | unmatched';
COMMENT ON COLUMN pncp_raw_bids.match_score IS
    'Score do match (0.000-1.000). 1.000 = exact match.';
COMMENT ON COLUMN pncp_raw_bids.match_confidence IS
    'Confianca: high (>=0.95) | medium (>=threshold) | low (<threshold)';


-- ============================================================
-- Migration: 011_unmatched_bids_view.sql
-- ============================================================
-- Migration 011: Unmatched bids view for debugging
-- Story 001.3: Entity Name-Matching Refinement
--
-- View para debugging de bids que nao conseguiram match com nenhum ente.
-- Facilita identificacao de:
--   - Bids com orgao_cnpj valido sem ente correspondente (entes faltando?)
--   - Bids com nome incompleto/inconsistente (normalizacao insuficiente?)
--   - Bids com threshold de fuzzy abaixo do configurado

CREATE OR REPLACE VIEW v_unmatched_bids AS
SELECT
    pncp_id,
    source,
    orgao_cnpj,
    orgao_razao_social,
    municipio,
    codigo_municipio_ibge,
    data_publicacao,
    match_method,
    match_score,
    match_confidence,
    ingested_at,
    CASE
        WHEN orgao_cnpj IS NOT NULL AND orgao_cnpj != '' THEN 'has_cnpj'
        ELSE 'name_only'
    END AS match_opportunity,
    CASE
        WHEN data_publicacao >= CURRENT_DATE - 90 THEN 'recent'
        ELSE 'historical'
    END AS recency
FROM pncp_raw_bids
WHERE matched_entity_id IS NULL
  AND (
    (orgao_cnpj IS NOT NULL AND orgao_cnpj != '')
    OR (orgao_razao_social IS NOT NULL AND orgao_razao_social != '')
  )
ORDER BY data_publicacao DESC NULLS LAST, ingested_at DESC;

COMMENT ON VIEW v_unmatched_bids IS
    'Bids sem matched_entity_id — para debugging do entity name-matching (Story 001.3)';

COMMENT ON COLUMN v_unmatched_bids.match_opportunity IS
    'Indica se o bid tem CNPJ (has_cnpj) ou apenas nome (name_only) para match';
COMMENT ON COLUMN v_unmatched_bids.recency IS
    'Indica se o bid e recente (90 dias) ou historico';


-- ============================================================
-- Migration: 012_coverage_snapshots.sql
-- ============================================================
-- Migration 012: Coverage snapshots + gap views for weekly report
-- Story 001.7: Weekly Coverage Report Automation
--
-- Dependencias: Migration 009 (entity_coverage, v_coverage_summary)
--               Migration 007 (sc_public_entities)

-- ============================================================
-- 1. coverage_snapshots — tracking historico semanal
-- ============================================================
CREATE TABLE IF NOT EXISTS coverage_snapshots (
    id              SERIAL PRIMARY KEY,
    snapshot_date   DATE NOT NULL DEFAULT CURRENT_DATE,
    source          TEXT NOT NULL,
    total_entities  INT NOT NULL,
    covered_entities INT NOT NULL,
    pct_covered     DECIMAL(5,2) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cov_snap_date ON coverage_snapshots (snapshot_date);
CREATE INDEX IF NOT EXISTS idx_cov_snap_source ON coverage_snapshots (source, snapshot_date);

COMMENT ON TABLE coverage_snapshots IS
    'Snapshots semanais de cobertura por fonte — usado para tendencia no relatorio semanal (Story 001.7)';

-- ============================================================
-- 2. v_coverage_gaps — entes sem cobertura em NENHUMA fonte
-- ============================================================
CREATE OR REPLACE VIEW v_coverage_gaps AS
SELECT
    e.id,
    e.razao_social,
    e.cnpj_8,
    e.municipio,
    e.natureza_juridica,
    -- e.uf, (removed - column does not exist)
    e.raio_200km,
    e.distancia_fk,
    ARRAY(
        SELECT ec.source
        FROM entity_coverage ec
        WHERE ec.entity_id = e.id AND ec.is_covered = TRUE
    ) AS fontes_ativas,
    (
        SELECT COUNT(DISTINCT ec2.source)
        FROM entity_coverage ec2
        WHERE ec2.entity_id = e.id AND ec2.is_covered = TRUE
    ) = 0 AS gap_total
FROM sc_public_entities e
WHERE e.is_active = TRUE
  AND NOT EXISTS (
      SELECT 1 FROM entity_coverage ec
      WHERE ec.entity_id = e.id AND ec.is_covered = TRUE
  )
ORDER BY e.municipio, e.razao_social;

COMMENT ON VIEW v_coverage_gaps IS
    'Entes publicos com gap TOTAL de cobertura (is_covered = FALSE em todas as fontes) — Story 001.5/001.7';

-- ============================================================
-- 3. v_coverage_gaps_by_municipio — gaps agregados por cidade
-- ============================================================
CREATE OR REPLACE VIEW v_coverage_gaps_by_municipio AS
SELECT
    e.municipio,
    COUNT(*) AS total_entes,
    COUNT(*) FILTER (WHERE NOT EXISTS (
        SELECT 1 FROM entity_coverage ec
        WHERE ec.entity_id = e.id AND ec.is_covered = TRUE
    )) AS entes_descobertos,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE NOT EXISTS (
            SELECT 1 FROM entity_coverage ec
            WHERE ec.entity_id = e.id AND ec.is_covered = TRUE
        )) / NULLIF(COUNT(*), 0),
        1
    ) AS pct_gap,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE EXISTS (
            SELECT 1 FROM entity_coverage ec
            WHERE ec.entity_id = e.id AND ec.is_covered = TRUE
        )) / NULLIF(COUNT(*), 0),
        1
    ) AS pct_coberto
FROM sc_public_entities e
WHERE e.is_active = TRUE
GROUP BY e.municipio
ORDER BY entes_descobertos DESC, pct_gap DESC;

COMMENT ON VIEW v_coverage_gaps_by_municipio IS
    'Agregacao de gaps de cobertura por municipio — Story 001.5/001.7';

-- ============================================================
-- 4. v_coverage_trend — evolucao semanal da cobertura
-- ============================================================
CREATE OR REPLACE VIEW v_coverage_trend AS
SELECT
    snapshot_date,
    source,
    total_entities,
    covered_entities,
    pct_covered,
    pct_covered - LAG(pct_covered) OVER (
        PARTITION BY source ORDER BY snapshot_date
    ) AS variacao_pct,
    ROW_NUMBER() OVER (PARTITION BY source ORDER BY snapshot_date DESC) AS rn_desc
FROM coverage_snapshots
ORDER BY snapshot_date DESC, source;

COMMENT ON VIEW v_coverage_trend IS
    'Evolucao semanal da cobertura com calculo de variacao — Story 001.5/001.7';

-- ============================================================
-- 5. generate_coverage_snapshot() — funcao para gerar snapshot manual
-- ============================================================
CREATE OR REPLACE FUNCTION generate_coverage_snapshot(snap_date DATE DEFAULT CURRENT_DATE)
RETURNS INT AS $$
DECLARE
    inserted INT := 0;
    rec RECORD;
BEGIN
    FOR rec IN
        SELECT
            ec.source,
            COUNT(*) AS total_entities,
            SUM(CASE WHEN ec.is_covered THEN 1 ELSE 0 END) AS covered_entities
        FROM entity_coverage ec
        WHERE EXISTS (
            SELECT 1 FROM sc_public_entities e
            WHERE e.id = ec.entity_id AND e.is_active = TRUE
        )
        GROUP BY ec.source
    LOOP
        INSERT INTO coverage_snapshots (snapshot_date, source, total_entities, covered_entities, pct_covered)
        VALUES (
            snap_date,
            rec.source,
            rec.total_entities,
            rec.covered_entities,
            ROUND(100.0 * rec.covered_entities / NULLIF(rec.total_entities, 0), 2)
        )
        ON CONFLICT DO NOTHING;
        inserted := inserted + 1;
    END LOOP;

    RETURN inserted;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION generate_coverage_snapshot IS
    'Gera snapshot de cobertura para todos as fontes — chamado pelo timer semanal (Story 001.7)';


-- ============================================================
-- Migration: 013_td-1.1_gin_index_objeto_contrato.sql
-- ============================================================
-- Migration 013: GIN trigram index on pncp_supplier_contracts.objeto_contrato
-- Story TD-1.1: Otimizacao de Queries
-- Deficit TD-DB-08 (HIGH): Tabela pncp_supplier_contracts (~3.69M registros)
-- nao tem GIN index em objeto_contrato, forcando full table scan em todas
-- as buscas textuais por objeto de contrato.
--
-- Uso no datalake_helper.py:
--   supplier_contracts() faz ILIKE chain em keywords → objeto_contrato
--   (linhas ~493-500 em scripts/datalake_helper.py)
--
-- Uso no backend/local_datalake.py:
--   get_supplier_contracts(), get_contracts_by_orgao() filtram por is_active
--
-- Index parcial (WHERE is_active = true) porque registros soft-deleted
-- nunca sao consultados. GIN com gin_trgm_ops para suportar ILIKE e
-- similaridade trigram.
--
-- NOTA: O migration 002 original criava idx_psc_objeto_trgm na tabela,
-- mas o schema atual (com is_active, numero_controle_pncp, etc.) foi
-- evoluido diretamente via DDL e perdeu esse index. A SCHEMA.md lista
-- 36 indexes em pncp_supplier_contracts — nenhum GIN em objeto_contrato.

-- ============================================================
-- Garantir extensao pg_trgm (necessaria para gin_trgm_ops)
-- ============================================================
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================
-- 1. GIN index com gin_trgm_ops em objeto_contrato
-- ============================================================
--
-- CREATE INDEX CONCURRENTLY permite que a tabela permaneca disponivel
-- para leitura/escrita durante a criacao do index (nao bloqueia escritas).
--
-- Partial index: WHERE is_active = TRUE porque:
--   1. soft-deleted records (is_active = FALSE) nunca sao consultados
--   2. Reduz tamanho do index em ~30% (menos registros para indexar)
--   3. Melhor selectivity ratio no planner

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_psc_objeto_contrato_gin
    ON pncp_supplier_contracts
    USING GIN (objeto_contrato gin_trgm_ops)
    WHERE is_active = TRUE;

COMMENT ON INDEX idx_psc_objeto_contrato_gin IS
    'TD-DB-08: GIN trigram index on objeto_contrato for fast textual search (Story TD-1.1)';

-- ============================================================
-- 2. Verificacao do index (query de diagnostico)
-- ============================================================
--
-- Para verificar se o index esta sendo usado:
--
--   EXPLAIN ANALYZE
--   SELECT * FROM pncp_supplier_contracts
--   WHERE is_active = TRUE
--     AND objeto_contrato ILIKE '%limpeza%'
--   LIMIT 100;
--
-- Deve mostrar: "Index Scan using idx_psc_objeto_contrato_gin"
-- (NÃO "Seq Scan on pncp_supplier_contracts")


-- ============================================================
-- Migration: 014_td-1.1_fix_hnsw_expression.sql
-- ============================================================
-- Migration 014: Fix HNSW vector similarity expression in search_datalake
-- Story TD-1.1: Otimizacao de Queries
-- Deficit TD-DB-11 (HIGH): A funcao search_datalake tem expressao
-- matematica incorreta que impede o uso do HNSW index de similaridade
-- vetorial, fazendo toda busca hibrida com embedding rodar full scan.
--
-- CHANGE LOG (v1.2.1 — QA fixes DOC-001, DOC-002):
--   DOC-001: p_esferas mudou de INT[] para TEXT[] (compatibilidade com callers
--            que passam strings como '{1,2,3}' em vez de arrays Postgres).
--   DOC-002: p_sources removido — todos os callers ativos (datalake_helper.py,
--            local_datalake.py) chamam a funcao sem este parametro.
--
-- Expressao ORIGINAL (incorreta):
--   (1.0 - (vec <=> p_embedding)) >= threshold
--
-- Expressao CORRIGIDA:
--   (vec <=> p_embedding) < (1.0 - threshold)
--
-- Explicacao:
--   O operador <=> (cosine distance) retorna valores em [0, 2], onde
--   0 = mesmo vetor e 2 = direcoes opostas. O HNSW index do pgvector
--   so pode ser utilizado quando a comparacao e feita DIRETAMENTE
--   contra o operador de distancia. Envolver a expressao em aritmetica
--   (1.0 - distance) impede o planner de reconhecer a oportunidade de
--   Index Scan, forcando um Seq Scan na tabela pncp_raw_bids.
--
--   A correcao inverte a logica: em vez de converter distancia para
--   similaridade e comparar, compara a distancia bruta diretamente
--   contra o complemento do threshold.

-- ============================================================
-- 1. Garantir extensao pgvector (necessaria para <=> operator)
-- ============================================================
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- 2. Recreate search_datalake with corrected HNSW expression
-- ============================================================
--
-- Esta funcao tem 13 parametros e suporta hybrid search (FTS + embedding).
-- A correcao esta no WHERE clause da hybrid search: linha com p_embedding.
--
-- Comparacao com a versao anterior (migration 005):
--   - Adicionados: p_websearch_text, p_modo, p_offset, p_embedding
--   - Retorno estendido para incluir colunas do schema real
--   - Expressao HNSW corrigida
--   - Suporte a websearch_to_tsquery para texto livre do usuario
--   - Modo "abertas" (encerramento futuro) adicionado

CREATE OR REPLACE FUNCTION search_datalake(
    p_ufs          TEXT[]   DEFAULT NULL,
    p_date_start   DATE     DEFAULT NULL,
    p_date_end     DATE     DEFAULT NULL,
    p_tsquery      TEXT     DEFAULT NULL,
    p_websearch_text TEXT   DEFAULT NULL,
    p_modalidades  INT[]    DEFAULT NULL,
    p_valor_min    NUMERIC  DEFAULT NULL,
    p_valor_max    NUMERIC  DEFAULT NULL,
    p_esferas      TEXT[]   DEFAULT NULL,
    p_modo         TEXT     DEFAULT 'publicacao',
    p_limit        INT      DEFAULT 100,
    p_offset       INT      DEFAULT 0,
    p_embedding    VECTOR(256) DEFAULT NULL
)
RETURNS TABLE (
    pncp_id              TEXT,
    objeto_compra        TEXT,
    valor_total_estimado NUMERIC,
    modalidade_id        INT,
    modalidade_nome      TEXT,
    situacao_compra      TEXT,
    esfera_id            TEXT,
    uf                   TEXT,
    municipio            TEXT,
    codigo_municipio_ibge TEXT,
    orgao_razao_social   TEXT,
    orgao_cnpj           TEXT,
    unidade_nome         TEXT,
    data_publicacao      TIMESTAMPTZ,
    data_abertura        TIMESTAMPTZ,
    data_encerramento    TIMESTAMPTZ,
    link_sistema_origem  TEXT,
    link_pncp            TEXT,
    content_hash         TEXT,
    source               TEXT,
    ingested_at          TIMESTAMPTZ,
    updated_at           TIMESTAMPTZ,
    ts_rank              REAL
) LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_threshold CONSTANT REAL := 0.7; -- minimum cosine similarity for embedding match
    v_webquery  TSQUERY;
BEGIN
    -- Convert websearch text to tsquery if provided
    IF p_websearch_text IS NOT NULL AND p_websearch_text != '' THEN
        BEGIN
            v_webquery := websearch_to_tsquery('portuguese', p_websearch_text);
        EXCEPTION WHEN OTHERS THEN
            v_webquery := NULL;
        END;
    END IF;

    RETURN QUERY
    SELECT
        b.pncp_id,
        b.objeto_compra,
        b.valor_total_estimado,
        b.modalidade_id,
        b.modalidade_nome,
        b.situacao_compra,
        b.esfera_id,
        b.uf,
        b.municipio,
        b.codigo_municipio_ibge,
        b.orgao_razao_social,
        b.orgao_cnpj,
        b.unidade_nome,
        b.data_publicacao,
        b.data_abertura,
        b.data_encerramento,
        b.link_sistema_origem,
        b.link_pncp,
        b.content_hash,
        b.source,
        b.ingested_at,
        b.updated_at,
        CASE
            WHEN p_tsquery IS NOT NULL AND b.tsv IS NOT NULL
            THEN ts_rank(b.tsv, to_tsquery('portuguese', p_tsquery))
            WHEN v_webquery IS NOT NULL AND b.tsv IS NOT NULL
            THEN ts_rank(b.tsv, v_webquery)
            ELSE 0.0
        END::REAL AS ts_rank
    FROM pncp_raw_bids b
    WHERE b.is_active = TRUE
      -- Filtros de metadados
      AND (p_ufs IS NULL OR b.uf = ANY(p_ufs))
      AND (p_date_start IS NULL OR b.data_publicacao >= p_date_start)
      AND (p_date_end IS NULL OR b.data_publicacao <= p_date_end)
      AND (p_modalidades IS NULL OR b.modalidade_id = ANY(p_modalidades))
      AND (p_valor_min IS NULL OR b.valor_total_estimado >= p_valor_min)
      AND (p_valor_max IS NULL OR b.valor_total_estimado <= p_valor_max)
      AND (p_esferas IS NULL OR b.esfera_id = ANY(p_esferas))
      -- Modo "abertas": encerramento futuro
      AND (p_modo IS DISTINCT FROM 'abertas' OR b.data_encerramento >= CURRENT_DATE)
      -- Filtro full-text search (tsquery classico)
      AND (
          p_tsquery IS NULL
          OR b.tsv @@ to_tsquery('portuguese', p_tsquery)
          OR b.objeto_compra ILIKE '%' || p_tsquery || '%'
      )
      -- Filtro websearch (texto livre do usuario)
      AND (
          v_webquery IS NULL
          OR b.tsv @@ v_webquery
      )
      -- Hybrid search: embedding similarity filter
      -- CORRECAO TD-DB-11: Expressao corrigida para permitir HNSW Index Scan
      -- ANTES: (1.0 - (vec <=> p_embedding)) >= v_threshold
      -- DEPOIS: (vec <=> p_embedding) < (1.0 - v_threshold)
      AND (
          p_embedding IS NULL
          OR b.embedding IS NULL
          OR (b.embedding <=> p_embedding) < (1.0 - v_threshold)
      )
    ORDER BY
        CASE
            WHEN p_tsquery IS NOT NULL AND b.tsv IS NOT NULL
            THEN ts_rank(b.tsv, to_tsquery('portuguese', p_tsquery))
            WHEN v_webquery IS NOT NULL AND b.tsv IS NOT NULL
            THEN ts_rank(b.tsv, v_webquery)
            ELSE 0.0
        END DESC,
        b.data_publicacao DESC
    OFFSET p_offset
    LIMIT p_limit;
END;
$$;

COMMENT ON FUNCTION search_datalake IS
    'TD-DB-11: Multi-filter hybrid search (FTS + embedding) com HNSW expression corrigida (Story TD-1.1)';


-- ============================================================
-- Migration: 015_td-2.3_enriched_entities_ttl.sql
-- ============================================================
-- Migration 015: TTL enforcement for enriched_entities
-- Story TD-2.3: Normalizacao e Constraints
-- Deficit TD-DB-03 (MEDIUM): enriched_entities sem TTL enforcement
--   13.8K registros sem politica de expiracao, risco de dados obsoletos acumulados
--
-- Estrategia:
--   1. Funcao de limpeza que remove registros com enriched_at > 90 dias
--   2. Script `scripts/cleanup-expired-entities.sql` para execucao periodica
--   3. Trigger BEFORE INSERT/UPDATE para validar TTL (opcional — ver abaixo)
--
-- NOTA: Nao implementamos trigger blocking porque a aplicacao precisa conseguir
--       inserir dados mesmo que estejam "expirados" (o cleanup e async).
--       A limpeza e feita por job periodico (cron) rodando o script.

-- ============================================================
-- 1. Funcao de limpeza TTL
-- ============================================================
--
-- Remove registros de enriched_entities que nao foram atualizados
-- nos ultimos 90 dias (configuravel via parametro p_ttl_days).
--
-- Uso:
--   SELECT ttl_cleanup_enriched_entities();          -- default 90 dias
--   SELECT ttl_cleanup_enriched_entities(30);         -- 30 dias
--   SELECT ttl_cleanup_enriched_entities(180);        -- 6 meses
--
-- Retorna: numero de registros removidos (INT)

CREATE OR REPLACE FUNCTION ttl_cleanup_enriched_entities(
    p_ttl_days INT DEFAULT 90
)
RETURNS INT
LANGUAGE plpgsql
VOLATILE
AS $$
DECLARE
    v_deleted INT;
BEGIN
    -- Validacao do parametro (COALESCE para tratar NULL)
    IF COALESCE(p_ttl_days, 0) < 1 THEN
        RAISE EXCEPTION 'p_ttl_days must be >= 1, got %', p_ttl_days;
    END IF;

    DELETE FROM enriched_entities
    WHERE enriched_at < CURRENT_DATE - p_ttl_days;

    GET DIAGNOSTICS v_deleted = ROW_COUNT;

    -- Log da operacao (via RAISE NOTICE para visibilidade em logs do cron)
    RAISE NOTICE 'TTL cleanup: removed % expired records from enriched_entities (TTL=% days)',
        v_deleted, p_ttl_days;

    RETURN v_deleted;
END;
$$;

COMMENT ON FUNCTION ttl_cleanup_enriched_entities IS
    'TD-DB-03: Remove registros expirados de enriched_entities baseado em enriched_at + TTL configurado (default 90 dias)';

-- ============================================================
-- 2. Refresh do index existente (garantir que cobre TTL)
-- ============================================================
--
-- O index idx_ee_enriched_at ja existe (criado na migration 003)
-- e cobre a coluna enriched_at usada na query de limpeza.
-- Nao e necessario recria-lo.
--
-- Verificacao:
--   SELECT schemaname, tablename, indexname, indexdef
--   FROM pg_indexes
--   WHERE tablename = 'enriched_entities';
--
-- Deve mostrar: idx_ee_enriched_at ON enriched_entities (enriched_at)

-- ============================================================
-- 3. Adicionar CHECK constraint enriched_at nao futura
-- ============================================================
--
-- Garantir que enriched_at nao esteja no futuro (dado inconsistente)

ALTER TABLE enriched_entities
    ADD CONSTRAINT chk_ee_enriched_at_not_future
    CHECK (enriched_at <= NOW() + INTERVAL '1 hour')
    NOT VALID;  -- NOT VALID para nao bloquear em producao (validacao gradual)

COMMENT ON CONSTRAINT chk_ee_enriched_at_not_future ON enriched_entities IS
    'TD-DB-03: enriched_at nao pode estar no futuro (tolerancia de 1h para fuso)';

-- ============================================================
-- 4. Adicionar NOT NULL onde apropriado
-- ============================================================

ALTER TABLE enriched_entities
    ADD CONSTRAINT chk_ee_cnpj_not_empty
    CHECK (cnpj <> '')
    NOT VALID;

ALTER TABLE enriched_entities
    ADD CONSTRAINT chk_ee_enriched_source_not_empty
    CHECK (enriched_source <> '')
    NOT VALID;

COMMENT ON CONSTRAINT chk_ee_cnpj_not_empty ON enriched_entities IS
    'TD-DB-03: CNPJ nao pode ser string vazia';
COMMENT ON CONSTRAINT chk_ee_enriched_source_not_empty ON enriched_entities IS
    'TD-DB-03: enriched_source nao pode ser string vazia';


-- ============================================================
-- Migration: 016_td-2.3_objeto_compra_gin.sql
-- ============================================================
-- Migration 016: GIN trigram index on pncp_raw_bids.objeto_compra
-- Story TD-2.3: Normalizacao e Constraints
-- Deficit TD-DB-06 (MEDIUM): GIST trigram index em pncp_raw_bids.objeto_compra
--   superdimensionado (294 MB para ~200K registros ativos), com relacao
--   index/dados de 1.1x.
--
-- Analise GIST vs GIN:
--
-- | Caracteristica        | GIST                          | GIN                            |
-- |-----------------------|-------------------------------|--------------------------------|
-- | Tamanho do index      | Maior (294 MB reportado)      | Menor (~40-60% do GIST)        |
-- | Velocidade INSERT     | Mais rapido                   | Mais lento (compressao)        |
-- | Velocidade SELECT     | Mais lento (mais IO)          | Mais rapido (bitmap scan)      |
-- | word_similarity()     | Suportado nativamente         | NAO suportado diretamente      |
-- | ILIKE / LIKE          | Suportado (gist_trgm_ops)     | Suportado (gin_trgm_ops)       |
-- | %term% wildcard       | Suportado                     | Suportado (mais rapido)        |
--
-- Decisao: GIN
--   - Codigo existente usa ILIKE e tsquery, NAO word_similarity()
--     (confirmado por grep em .sql e .py — zero ocorrencias de word_similarity)
--   - GIN e 40-60% menor que GIST para trigram search
--   - GIN e significativamente mais rapido para SELECT com ILIKE
--   - Caso word_similarity seja necessario no futuro, manter GIST como fallback
--
-- Riscos mitigados:
--   - NOTA: Se existir GIST index em producao (criado manualmente), ele
--     permanecera ate remocao explicita. Este migration ADD o GIN sem remover
--     o GIST. A remocao do GIST deve ser feita APOS validacao de que o GIN
--     atende todos os casos de uso.
--   - Comando para verificar GIST existente:
--       SELECT indexname, indexdef FROM pg_indexes
--       WHERE tablename = 'pncp_raw_bids' AND indexdef LIKE '%objeto_compra%';

-- ============================================================
-- Garantir extensao pg_trgm (necessaria para gin_trgm_ops)
-- ============================================================
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================
-- 1. GIN index com gin_trgm_ops em objeto_compra
-- ============================================================
--
-- Partial index: WHERE is_active = TRUE porque:
--   1. Soft-deleted records (is_active = FALSE) nunca sao consultados
--   2. Reduz tamanho do index (~15-20% menos registros)
--   3. Melhor selectivity ratio no planner
--
-- NOTA sobre CONCURRENTLY:
--   Usamos CREATE INDEX CONCURRENTLY para nao bloquear escritas em producao.
--   Importante: CONCURRENTLY exige que a transacao seja a unica operacao
--   (nao pode ser combinado com outros DDL na mesma transacao).
--   Como esta migration contem apenas este comando DDL, e seguro.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bids_objeto_compra_gin
    ON pncp_raw_bids
    USING GIN (objeto_compra gin_trgm_ops)
    WHERE is_active = TRUE;

COMMENT ON INDEX idx_bids_objeto_compra_gin IS
    'TD-DB-06: GIN trigram index on objeto_compra for fast ILIKE search (Story TD-2.3)';

-- ============================================================
-- 2. Remocao do GIST antigo (se existir em producao)
-- ============================================================
--
-- Descomente APOS validar que GIN atende todos os casos de uso:
--
--   DROP INDEX IF EXISTS idx_bids_objeto_compra_gist;
--
-- Para verificar se o GIST existe:
--   SELECT indexname FROM pg_indexes
--   WHERE tablename = 'pncp_raw_bids'
--     AND indexname LIKE '%objeto_compra%'
--     AND indexdef ILIKE '%gist%';

-- ============================================================
-- 3. Verificacao do index (query de diagnostico)
-- ============================================================
--
-- Para verificar se o index esta sendo usado:
--
--   EXPLAIN ANALYZE
--   SELECT pncp_id, objeto_compra
--   FROM pncp_raw_bids
--   WHERE is_active = TRUE
--     AND objeto_compra ILIKE '%obra%'
--   LIMIT 50;
--
-- Deve mostrar: "Index Scan using idx_bids_objeto_compra_gin"
-- (NAO "Seq Scan on pncp_raw_bids")


-- ============================================================
-- Migration: 017_td-2.3_matched_entity_id_index.sql
-- ============================================================
-- Migration 017: Reforcar index em matched_entity_id
-- Story TD-2.3: Normalizacao e Constraints
-- Deficit TD-DB-07 (MEDIUM): Tabela pncp_raw_bids sem index em matched_entity_id,
--   forcando nested loop scan em coverage queries com LEFT JOIN.
--
-- Contexto:
--   O index idx_bids_matched_entity foi definido na migration 001, mas o schema
--   real de producao pode nao te-lo (schema diverge das migrations — vide TD-2.1).
--   Esta migration garante que o index exista em producao usando IF NOT EXISTS.
--
-- Index partial:
--   WHERE matched_entity_id IS NOT NULL porque:
--   1. A maioria das coverage queries filtra por entidades com match
--   2. Registros sem match (~40% dos bids) sao irrelevantes para coverage
--   3. Reduz tamanho do index significativamente
--   4. Melhor selectivity para o planner

-- ============================================================
-- 1. Index em matched_entity_id (partial)
-- ============================================================
--
-- Usamos CONCURRENTLY para evitar lock em producao.
-- Mesmo que o index ja exista (criado na migration 001 e aplicado),
-- IF NOT EXISTS torna esta operacao segura para re-execucao.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bids_matched_entity
    ON pncp_raw_bids (matched_entity_id)
    WHERE matched_entity_id IS NOT NULL;

COMMENT ON INDEX idx_bids_matched_entity IS
    'TD-DB-07: Partial index on matched_entity_id for coverage JOIN performance (Story TD-2.3)';

-- ============================================================
-- 2. Index composto para match_logging (reforco)
-- ============================================================
--
-- O migration 010 define idx_match_logging_lookup para (match_method, matched_entity_id).
-- Reforcar com IF NOT EXISTS para garantir consistencia em producao.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_match_logging_lookup
    ON pncp_raw_bids (match_method, matched_entity_id)
    WHERE matched_entity_id IS NOT NULL;

COMMENT ON INDEX idx_match_logging_lookup IS
    'TD-DB-07: Composite index for match_logging lookup (match_method + matched_entity_id)';

-- ============================================================
-- 3. Verificacao (query de diagnostico)
-- ============================================================
--
-- Para confirmar que o index e usado em coverage queries:
--
--   EXPLAIN ANALYZE
--   SELECT ec.entity_id, ec.source, ec.is_covered, b.pncp_id
--   FROM entity_coverage ec
--   LEFT JOIN pncp_raw_bids b ON b.matched_entity_id = ec.entity_id
--   WHERE ec.is_covered = FALSE
--   LIMIT 100;
--
-- Deve mostrar: "Index Scan using idx_bids_matched_entity"
-- ao inves de "Nested Loop" ou "Seq Scan on pncp_raw_bids"


-- ============================================================
-- Migration: 018-td-5.3_esfera_id_check.sql
-- ============================================================
-- Migration 018: CHECK constraint para esfera_id em pncp_raw_bids
-- Story TD-5.3: Otimizacao de Performance
-- Deficit TD-DB-09 (LOW): Coluna esfera_id sem CHECK constraint,
--   permitindo valores invalidos.
--
-- Contexto:
--   A coluna esfera_id e INT e armazena codigos numericos:
--     1 = Federal (F)
--     2 = Estadual (E)
--     3 = Municipal (M)
--     4 = Distrital (D)
--
--   O assessment original sugeria CHECK (esfera_id IN ('F','E','M','D')),
--   mas a coluna e INT. Adaptado para valores inteiros.
--
--   O RPC search_datalake usa p_esferas INT[], entao a constraint
--   com inteiros e consistente com o resto do sistema.

-- ============================================================
-- 1. Limpeza preventiva: garantir que nao ha dados invalidos
-- ============================================================
--
-- Caso existam registros com esfera_id fora de {1,2,3,4},
-- resetamos para NULL (desconhecido) para nao bloquear a constraint.

UPDATE pncp_raw_bids
SET esfera_id = NULL
WHERE esfera_id IS NOT NULL
  AND esfera_id NOT IN (1, 2, 3, 4);

-- ============================================================
-- 2. CHECK constraint
-- ============================================================

ALTER TABLE pncp_raw_bids
ADD CONSTRAINT chk_pncp_raw_bids_esfera_id
CHECK (esfera_id IS NULL OR esfera_id IN (1, 2, 3, 4));

COMMENT ON CONSTRAINT chk_pncp_raw_bids_esfera_id ON pncp_raw_bids IS
    'TD-DB-09: esfera_id deve ser 1=Federal, 2=Estadual, 3=Municipal, 4=Distrital, ou NULL';

-- ============================================================
-- 3. Verificacao
-- ============================================================
--
-- Para confirmar que a constraint esta ativa:
--   INSERT INTO pncp_raw_bids (pncp_id, esfera_id, source)
--   VALUES ('test-constraint-999', 99, 'pncp');
--   -- ERROR: new row for relation "pncp_raw_bids" violates check constraint
--
-- Para listar registros com esfera_id invalido (antes da limpeza):
--   SELECT pncp_id, esfera_id FROM pncp_raw_bids
--   WHERE esfera_id IS NOT NULL AND esfera_id NOT IN (1, 2, 3, 4);


-- ============================================================
-- Migration: 019-td-5.3_soft_delete_purge_docs.sql
-- ============================================================
-- Migration 019: Documentacao do soft-delete em purge_old_bids
-- Story TD-5.3: Otimizacao de Performance
-- Deficit TD-DB-14 (MEDIUM): purge_old_bids fazia DELETE fisico.
--
-- Contexto:
--   A funcao purge_old_bids foi implementada originalmente na migration 008
--   como soft-delete (UPDATE is_active = FALSE), nao como DELETE fisico.
--   Esta migration e apenas documentacao confirmando que o comportamento
--   atual e soft-delete, e adiciona:
--     1. Confirmacao do soft-delete via COMMENT ON FUNCTION
--     2. Funcao auxiliar purge_old_bids_hard() para purga fisica
--        controlada (opcional, taxa de retencao explicita)
--
-- NOTA: A funcao purge_old_bids ja existe e JA FAZ SOFT-DELETE.
-- Esta migration apenas documenta e estende.

-- ============================================================
-- 1. Reforcar documentacao da funcao existente
-- ============================================================

COMMENT ON FUNCTION purge_old_bids IS
    'TD-DB-14: Soft-delete — marca is_active = FALSE para bids mais antigos que p_retention_days. '
    'Nao faz DELETE fisico. Registros permanecem na tabela e podem ser restaurados '
    'via UPDATE pncp_raw_bids SET is_active = TRUE WHERE ...';

-- ============================================================
-- 2. Funcao auxiliar: hard-delete seguro (opcional, controlado)
-- ============================================================
--
-- Uso apenas quando a retencao de soft-delete expirou.
-- Segunda camada de protecao: requer confirmaçao explicita.
--
-- Parametros:
--   p_soft_retention_days: idade minima para registros soft-deleted (default 90)
--     So registros que ja estao com is_active = FALSE ha pelo menos N dias
--     serao fisicamente removidos.

CREATE OR REPLACE FUNCTION purge_old_bids_hard(
    p_soft_retention_days INT DEFAULT 90
)
RETURNS TABLE (
    hard_deleted_count INT,
    remaining_soft_deleted INT
) LANGUAGE plpgsql AS $$
DECLARE
    v_cutoff DATE;
    v_deleted INT;
    v_remaining INT;
BEGIN
    v_cutoff := CURRENT_DATE - p_soft_retention_days;

    -- Hard-delete apenas registros ja soft-deleted ha mais de N dias
    DELETE FROM pncp_raw_bids
    WHERE is_active = FALSE
      AND updated_at < v_cutoff::TIMESTAMPTZ;

    GET DIAGNOSTICS v_deleted = ROW_COUNT;

    SELECT COUNT(*)::INT INTO v_remaining
    FROM pncp_raw_bids
    WHERE is_active = FALSE;

    RETURN QUERY SELECT v_deleted, v_remaining;
END;
$$;

COMMENT ON FUNCTION purge_old_bids_hard IS
    'TD-DB-14: Hard-delete controlado — remove fisicamente registros soft-deleted '
    'ha mais de p_soft_retention_days dias. So executa quando a retencao de '
    'soft-delete expirou. Use com cautela.';

-- ============================================================
-- 3. Garantir que a funcao principal usa soft-delete
-- ============================================================
--
-- A funcao purge_old_bids ja existe (criada na 008) e ja implementa
-- soft-delete. Re-criamos aqui para confirmar e documentar:

CREATE OR REPLACE FUNCTION purge_old_bids(p_retention_days INT DEFAULT 400)
RETURNS TABLE (
    purged_count INT,
    remaining_count INT
) LANGUAGE plpgsql AS $$
DECLARE
    cutoff_date DATE;
    v_purged INT;
BEGIN
    cutoff_date := CURRENT_DATE - p_retention_days;

    -- Soft-delete: marca como inativo (NAO remove fisicamente)
    UPDATE pncp_raw_bids
    SET is_active = FALSE
    WHERE is_active = TRUE
      AND data_publicacao < cutoff_date;

    GET DIAGNOSTICS v_purged = ROW_COUNT;

    RETURN QUERY
    SELECT
        v_purged,
        COUNT(*)::INT
    FROM pncp_raw_bids
    WHERE is_active = TRUE;
END;
$$;

COMMENT ON FUNCTION purge_old_bids IS
    'TD-DB-14 (confirmado): Soft-delete — UPDATE is_active = FALSE. '
    'Nunca faz DELETE. Registros permanecem recuperaveis.';

-- ============================================================
-- 4. Verificacao
-- ============================================================
--
-- Para testar soft-delete:
--   SELECT * FROM purge_old_bids(400);
--   -- Verificar que registros antigos tem is_active = FALSE
--   SELECT COUNT(*) FROM pncp_raw_bids WHERE is_active = FALSE;
--
-- Para restaurar um registro soft-deleted:
--   UPDATE pncp_raw_bids SET is_active = TRUE WHERE pncp_id = '<id>';
--
-- Para hard-delete (cuidado):
--   SELECT * FROM purge_old_bids_hard(90);


-- ============================================================
-- Migration: 020_td-2.4_sync_local_schema.sql
-- ============================================================
-- Migration 020: TD-2.4 — Sync local DataLake schema with expected schema
-- Aplica correcoes de schema drift identificadas durante validacao E2E.
--
-- Problemas corrigidos:
--   1. entity_coverage table missing
--   2. v_coverage_gaps_by_municipio view missing
--   3. ingestion_runs.source column missing
--   4. 3 stuck ingestion runs (IDs 3, 4, 5) reset to 'failed'
--   5. ingestion_checkpoints structure — add columns for sync API (checkpoint.py)
--
-- ADAPTACAO VS STORY ORIGINAL:
--   O banco local usa schema v2 (baseline 001-v2, nao v1 004/009/012).
--   Esta migration foi adaptada para:
--     - Usar public. prefix (v2 pattern)
--     - DO $$ blocks com IF NOT EXISTS para constraints (v2 pattern)
--     - ingestion_runs usa completed_at (nao finished_at) e metadata (jsonb)
--       em vez de error_message (colunas v2)
--     - ingestion_checkpoints adiciona scope_key, last_id, updated_at para
--       sync API mantendo colunas v2 existentes (uf, modalidade_id, etc.)
--     - Triggers criados condicionalmente (se matched_entity_id existir)
--       para evitar runtime error em INSERT
--
-- Depende de: supabase/migrations/001-v2_initial_schema.sql (ou equivalente)
--             sc_public_entities, pncp_raw_bids, ingestion_runs existentes
-- Idempotente: Sim (IF NOT EXISTS, CREATE OR REPLACE, DO $$ blocks)

BEGIN;

-- ============================================================
-- 1. entity_coverage table (schema v2 pattern)
-- Fonte: supabase/migrations/002-v2-td-2.2_entity_coverage.sql
-- ============================================================
CREATE TABLE IF NOT EXISTS public.entity_coverage (
    entity_id    INTEGER NOT NULL,
    source       TEXT NOT NULL,
    last_seen_at TIMESTAMPTZ,
    total_bids   INTEGER NOT NULL DEFAULT 0,
    is_covered   BOOLEAN NOT NULL DEFAULT FALSE,
    within_200km BOOLEAN NOT NULL DEFAULT FALSE
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'entity_coverage_pkey') THEN
        ALTER TABLE ONLY public.entity_coverage
            ADD CONSTRAINT entity_coverage_pkey PRIMARY KEY (entity_id, source);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'entity_coverage_entity_id_fkey') THEN
        ALTER TABLE ONLY public.entity_coverage
            ADD CONSTRAINT entity_coverage_entity_id_fkey
            FOREIGN KEY (entity_id) REFERENCES public.sc_public_entities(id)
            ON DELETE CASCADE;
    END IF;
END $$;

-- Indexes for fast gap detection
CREATE INDEX IF NOT EXISTS idx_cov_covered ON public.entity_coverage USING btree (is_covered, within_200km);
CREATE INDEX IF NOT EXISTS idx_cov_last_seen ON public.entity_coverage USING btree (last_seen_at);
CREATE INDEX IF NOT EXISTS idx_cov_source ON public.entity_coverage USING btree (source, is_covered);

-- Popula registros iniciais para entidades ativas (se vazia)
INSERT INTO public.entity_coverage (entity_id, source, is_covered, within_200km)
SELECT e.id, s.source, FALSE, COALESCE(e.raio_200km, FALSE)
FROM public.sc_public_entities e
CROSS JOIN (VALUES ('pncp'), ('dom_sc'), ('pcp'), ('compras_gov')) AS s(source)
WHERE e.is_active = TRUE
ON CONFLICT (entity_id, source) DO NOTHING;

-- ============================================================
-- 1a. Trigger functions and triggers
-- Criados condicionalmente: so vinculam a pncp_raw_bids se a
-- coluna matched_entity_id existir. Caso contrario, as funcoes
-- sao criadas mas os triggers nao — evitando runtime error
-- em INSERT INTO pncp_raw_bids.
-- ============================================================

-- Trigger function: update entity_coverage on bid insert
CREATE OR REPLACE FUNCTION public.update_entity_coverage()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.matched_entity_id IS NOT NULL THEN
        INSERT INTO public.entity_coverage (entity_id, source, last_seen_at, total_bids, is_covered, within_200km)
        VALUES (
            NEW.matched_entity_id,
            NEW.source,
            NEW.data_publicacao,
            1,
            COALESCE(NEW.data_publicacao >= CURRENT_DATE - 90, FALSE),
            COALESCE((SELECT raio_200km FROM public.sc_public_entities WHERE id = NEW.matched_entity_id), FALSE)
        )
        ON CONFLICT (entity_id, source) DO UPDATE
        SET
            last_seen_at = GREATEST(COALESCE(public.entity_coverage.last_seen_at, '1970-01-01'::date), COALESCE(NEW.data_publicacao, '1970-01-01'::date)),
            total_bids = public.entity_coverage.total_bids + 1,
            is_covered = GREATEST(COALESCE(public.entity_coverage.last_seen_at, '1970-01-01'::date), COALESCE(NEW.data_publicacao, '1970-01-01'::date)) >= CURRENT_DATE - 90;
    END IF;
    RETURN NEW;
END;
$$;

-- Trigger function: update when matched_entity_id is set after initial insert
CREATE OR REPLACE FUNCTION public.update_entity_coverage_on_update()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.matched_entity_id IS NOT NULL AND (OLD.matched_entity_id IS NULL OR OLD.matched_entity_id <> NEW.matched_entity_id) THEN
        INSERT INTO public.entity_coverage (entity_id, source, last_seen_at, total_bids, is_covered, within_200km)
        VALUES (
            NEW.matched_entity_id,
            NEW.source,
            NEW.data_publicacao,
            1,
            COALESCE(NEW.data_publicacao >= CURRENT_DATE - 90, FALSE),
            COALESCE((SELECT raio_200km FROM public.sc_public_entities WHERE id = NEW.matched_entity_id), FALSE)
        )
        ON CONFLICT (entity_id, source) DO UPDATE
        SET
            last_seen_at = GREATEST(COALESCE(public.entity_coverage.last_seen_at, '1970-01-01'::date), COALESCE(NEW.data_publicacao, '1970-01-01'::date)),
            total_bids = public.entity_coverage.total_bids + 1,
            is_covered = GREATEST(COALESCE(public.entity_coverage.last_seen_at, '1970-01-01'::date), COALESCE(NEW.data_publicacao, '1970-01-01'::date)) >= CURRENT_DATE - 90;
    END IF;
    RETURN NEW;
END;
$$;

-- Cria triggers apenas se matched_entity_id existir em pncp_raw_bids
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'pncp_raw_bids'
          AND column_name = 'matched_entity_id'
    ) THEN
        DROP TRIGGER IF EXISTS trg_bids_coverage ON public.pncp_raw_bids;
        CREATE TRIGGER trg_bids_coverage
            AFTER INSERT ON public.pncp_raw_bids
            FOR EACH ROW EXECUTE FUNCTION public.update_entity_coverage();

        DROP TRIGGER IF EXISTS trg_bids_coverage_update ON public.pncp_raw_bids;
        CREATE TRIGGER trg_bids_coverage_update
            AFTER UPDATE ON public.pncp_raw_bids
            FOR EACH ROW EXECUTE FUNCTION public.update_entity_coverage_on_update();
    END IF;
END $$;

-- Comments
COMMENT ON TABLE public.entity_coverage IS 'Cobertura de licitacoes por ente publico e fonte — Story TD-2.4';
COMMENT ON COLUMN public.entity_coverage.entity_id IS 'FK → sc_public_entities.id';
COMMENT ON COLUMN public.entity_coverage.source IS 'Fonte de dados: pncp|dom_sc|pcp|compras_gov';
COMMENT ON COLUMN public.entity_coverage.last_seen_at IS 'Ultima vez que este ente foi visto nesta fonte';
COMMENT ON COLUMN public.entity_coverage.total_bids IS 'Total de licitacoes coletadas deste ente';
COMMENT ON COLUMN public.entity_coverage.is_covered IS 'Tem publicacoes nos ultimos 90 dias?';
COMMENT ON COLUMN public.entity_coverage.within_200km IS 'Desnormalizado de sc_public_entities.raio_200km';

-- ============================================================
-- 2. v_coverage_gaps_by_municipio view
-- Fonte: supabase/migrations/003-v2 + db/migrations/012
-- ============================================================
CREATE OR REPLACE VIEW public.v_coverage_gaps_by_municipio AS
SELECT
    e.municipio,
    COUNT(*) AS total_entes,
    COUNT(*) FILTER (WHERE NOT EXISTS (
        SELECT 1 FROM public.entity_coverage ec
        WHERE ec.entity_id = e.id AND ec.is_covered = TRUE
    )) AS entes_descobertos,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE NOT EXISTS (
            SELECT 1 FROM public.entity_coverage ec
            WHERE ec.entity_id = e.id AND ec.is_covered = TRUE
        )) / NULLIF(COUNT(*), 0),
        1
    ) AS pct_gap,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE EXISTS (
            SELECT 1 FROM public.entity_coverage ec
            WHERE ec.entity_id = e.id AND ec.is_covered = TRUE
        )) / NULLIF(COUNT(*), 0),
        1
    ) AS pct_coberto
FROM public.sc_public_entities e
WHERE e.is_active = TRUE
GROUP BY e.municipio
ORDER BY entes_descobertos DESC, pct_gap DESC;

COMMENT ON VIEW public.v_coverage_gaps_by_municipio IS
    'Agregacao de gaps de cobertura por municipio — Story TD-2.4';

-- ============================================================
-- 3. ingestion_runs — add source column + reset stuck runs
-- ============================================================

-- 3a. Add source column (se ausente)
ALTER TABLE public.ingestion_runs ADD COLUMN IF NOT EXISTS source TEXT;

-- 3b. Reset stuck ingestion runs (IDs 3, 4, 5)
-- Adaptado para schema v2: usa completed_at (nao finished_at)
-- e metadata jsonb (nao error_message text)
UPDATE public.ingestion_runs
SET
    status = 'failed',
    completed_at = NOW(),
    metadata = jsonb_build_object(
        'reset_reason', 'Stuck run reset by Story TD-2.4 migration 020',
        'reset_timestamp', NOW() AT TIME ZONE 'UTC',
        'original_started_at', started_at AT TIME ZONE 'UTC',
        'stuck_duration_days', ROUND(EXTRACT(EPOCH FROM (NOW() - started_at)) / 86400, 1)
    )
WHERE id IN (3, 4, 5)
  AND status = 'running';

-- ============================================================
-- 4. ingestion_checkpoints — add columns for sync API
-- O schema v2 existente tem colunas: id, source, uf,
-- modalidade_id, last_date, last_page, records_fetched, status,
-- error_message, started_at, completed_at, crawl_batch_id.
-- Precisamos adicionar scope_key, last_id, updated_at para a
-- sync API (scripts/crawl/checkpoint.py) que usa PK (source, scope_key).
-- ============================================================

ALTER TABLE public.ingestion_checkpoints ADD COLUMN IF NOT EXISTS scope_key TEXT;
ALTER TABLE public.ingestion_checkpoints ADD COLUMN IF NOT EXISTS last_id TEXT;
ALTER TABLE public.ingestion_checkpoints ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;

-- Popula scope_key para registros existentes (converte uf+modalidade_id)
UPDATE public.ingestion_checkpoints
SET scope_key = COALESCE(uf || '_' || modalidade_id::TEXT, 'default')
WHERE scope_key IS NULL;

-- Seta default para scope_key
ALTER TABLE public.ingestion_checkpoints ALTER COLUMN scope_key SET DEFAULT 'default';

-- Adiciona constraint UNIQUE (source, scope_key) para ON CONFLICT na sync API
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_ingestion_checkpoints_source_scope'
    ) THEN
        ALTER TABLE public.ingestion_checkpoints
            ADD CONSTRAINT uq_ingestion_checkpoints_source_scope
            UNIQUE (source, scope_key);
    END IF;
END $$;

-- Seta default para updated_at
ALTER TABLE public.ingestion_checkpoints ALTER COLUMN updated_at SET DEFAULT NOW();

-- Popula updated_at para registros existentes
UPDATE public.ingestion_checkpoints
SET updated_at = COALESCE(completed_at, NOW())
WHERE updated_at IS NULL;

-- Comments
COMMENT ON COLUMN public.ingestion_checkpoints.scope_key IS
    'Sync API scope identifier (default ou uf_modalidade_id) — adicionado por Story TD-2.4';
COMMENT ON COLUMN public.ingestion_checkpoints.last_id IS
    'Ultimo record ID (source-specific) — adicionado por Story TD-2.4';
COMMENT ON COLUMN public.ingestion_checkpoints.updated_at IS
    'Timestamp da ultima atualizacao — adicionado por Story TD-2.4';

-- ============================================================
-- 5. v_coverage_summary — recreate if missing
-- Fonte: supabase/migrations/003-v2
-- ============================================================
CREATE OR REPLACE VIEW public.v_coverage_summary AS
SELECT
    ec.source,
    ec.within_200km,
    ec.is_covered,
    COUNT(*) AS entity_count,
    ROUND(
        (COUNT(*)::NUMERIC * 100.0) / SUM(COUNT(*)) OVER (PARTITION BY ec.within_200km), 1
    ) AS pct
FROM public.entity_coverage ec
WHERE EXISTS (
    SELECT 1 FROM public.sc_public_entities e
    WHERE e.id = ec.entity_id AND e.is_active = TRUE
)
GROUP BY ec.source, ec.within_200km, ec.is_covered
ORDER BY ec.source, ec.within_200km, ec.is_covered;

COMMENT ON VIEW public.v_coverage_summary IS
    'Sumario de cobertura por source e raio_200km — Story TD-2.4';

-- ============================================================
-- 6. Register in tracking (se tabela _migrations existir)
-- ============================================================
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = '_migrations') THEN
        INSERT INTO public._migrations (version, name, applied_at, checksum, rollback_sql)
        VALUES (
            '020',
            'td-2.4_sync_local_schema',
            NOW(),
            'sha256=manual-td-2-4',
            'DROP TABLE IF EXISTS public.entity_coverage CASCADE; DROP VIEW IF EXISTS public.v_coverage_gaps_by_municipio CASCADE; DROP VIEW IF EXISTS public.v_coverage_summary CASCADE; ALTER TABLE public.ingestion_runs DROP COLUMN IF EXISTS source; ALTER TABLE public.ingestion_checkpoints DROP COLUMN IF EXISTS scope_key; ALTER TABLE public.ingestion_checkpoints DROP COLUMN IF EXISTS last_id; ALTER TABLE public.ingestion_checkpoints DROP COLUMN IF EXISTS updated_at;'
        )
        ON CONFLICT (version) DO NOTHING;
    END IF;
END $$;

COMMIT;


-- ============================================================
-- Migration: 021_entity_coverage_rebuild.sql
-- ============================================================
-- Migration 021: COVERAGE-2.4 — Entity Coverage Rebuild
-- Reconstroi a tabela entity_coverage com dados de todas as fontes das Fases 1 e 2,
-- adiciona suporte a match_method, corrige triggers, e implementa comandos de rebuild.
--
-- Fonte: Story COVERAGE-2.4
--
-- Problemas corrigidos:
--   1. entity_coverage sem coluna match_method (necessario para COVERAGE-1.8 hierarquico)
--   2. Triggers de coverage desativados (nao acionam em INSERT/UPDATE)
--   3. Apenas fontes pncp e ciga_ckan populadas — faltam dom_sc, pcp, compras_gov,
--      sc_compras, doe_sc, mides_bigquery, transparencia
--   4. v_unmatched_bids nao existe no banco (definido na migration 011 mas nunca aplicado)
--   5. View v_coverage_trend ausente
--   6. Funcao generate_coverage_snapshot ausente
--
-- Depende de: migration 020 (entity_coverage table, sc_public_entities, pncp_raw_bids)
-- Idempotente: Sim (CREATE OR REPLACE, IF NOT EXISTS, DO $$ blocks)

BEGIN;

-- ============================================================
-- 1. Add match_method column to entity_coverage
-- ============================================================
ALTER TABLE public.entity_coverage
    ADD COLUMN IF NOT EXISTS match_method TEXT;

COMMENT ON COLUMN public.entity_coverage.match_method IS
    'Metodo de match: direct|cnpj_fallback|hierarchical|name_match — adicionado por COVERAGE-2.4';

-- ============================================================
-- 2. Initialize coverage for ALL known sources
-- Fontes das Fases 1 e 2 do EPIC-COVERAGE-100PCT:
--   - pncp (PNCP API)
--   - dom_sc (DOM-SC)
--   - pcp (Portal de Compras Publicas)
--   - compras_gov (Compras Governamentais)
--   - ciga_ckan (CIGA CKAN)
--   - sc_compras (SC Compras)
--   - doe_sc (DOE-SC)
--   - mides_bigquery (MiDES BigQuery)
--   - transparencia (Portal Transparencia)
-- ============================================================
INSERT INTO public.entity_coverage (entity_id, source, is_covered, within_200km)
SELECT e.id, s.source, FALSE, COALESCE(e.raio_200km, FALSE)
FROM public.sc_public_entities e
CROSS JOIN (VALUES
    ('pncp'),
    ('dom_sc'),
    ('pcp'),
    ('compras_gov'),
    ('ciga_ckan'),
    ('sc_compras'),
    ('doe_sc'),
    ('mides_bigquery'),
    ('transparencia')
) AS s(source)
WHERE e.is_active = TRUE
ON CONFLICT (entity_id, source) DO NOTHING;

-- ============================================================
-- 3. Rebuild coverage from actual bid data
-- ============================================================

-- Step 3a: Direct matches via matched_entity_id
UPDATE public.entity_coverage ec
SET
    is_covered = TRUE,
    last_seen_at = b.latest_pub,
    total_bids = b.bid_count,
    match_method = 'direct'
FROM (
    SELECT
        matched_entity_id AS entity_id,
        source,
        MAX(data_publicacao) AS latest_pub,
        COUNT(*) AS bid_count
    FROM public.pncp_raw_bids
    WHERE matched_entity_id IS NOT NULL
      AND is_active = TRUE
    GROUP BY matched_entity_id, source
) b
WHERE ec.entity_id = b.entity_id
  AND ec.source = b.source;

-- Step 3b: CNPJ-8 fallback for matched bids
UPDATE public.entity_coverage ec
SET
    is_covered = TRUE,
    last_seen_at = b.latest_pub,
    total_bids = b.bid_count,
    match_method = 'cnpj_fallback'
FROM (
    SELECT
        e.id AS entity_id,
        b.source,
        MAX(b.data_publicacao) AS latest_pub,
        COUNT(*) AS bid_count
    FROM public.pncp_raw_bids b
    JOIN public.sc_public_entities e ON LEFT(b.orgao_cnpj, 8) = e.cnpj_8
    WHERE b.matched_entity_id IS NULL
      AND b.orgao_cnpj IS NOT NULL
      AND b.is_active = TRUE
      AND e.is_active = TRUE
    GROUP BY e.id, b.source
) b
WHERE ec.entity_id = b.entity_id
  AND ec.source = b.source
  AND ec.is_covered = FALSE;  -- so update if not already covered

-- Step 3c: Name-based matches (using match_method from pncp_raw_bids)
UPDATE public.entity_coverage ec
SET
    is_covered = TRUE,
    last_seen_at = b.latest_pub,
    total_bids = b.bid_count,
    match_method = 'name_match'
FROM (
    SELECT
        matched_entity_id AS entity_id,
        source,
        MAX(data_publicacao) AS latest_pub,
        COUNT(*) AS bid_count
    FROM public.pncp_raw_bids
    WHERE matched_entity_id IS NOT NULL
      AND match_method IN ('name_fuzzy', 'name_contains', 'name_normalized')
      AND is_active = TRUE
    GROUP BY matched_entity_id, source
) b
WHERE ec.entity_id = b.entity_id
  AND ec.source = b.source
  AND ec.is_covered = FALSE;

-- ============================================================
-- 4. Recreate trigger functions with full source support
-- ============================================================

-- Trigger function: update entity_coverage on bid INSERT
CREATE OR REPLACE FUNCTION public.update_entity_coverage()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.matched_entity_id IS NOT NULL THEN
        INSERT INTO public.entity_coverage (
            entity_id, source, last_seen_at, total_bids, is_covered, within_200km, match_method
        )
        VALUES (
            NEW.matched_entity_id,
            NEW.source,
            NEW.data_publicacao,
            1,
            COALESCE(NEW.data_publicacao >= CURRENT_DATE - 90, FALSE),
            COALESCE((SELECT raio_200km FROM public.sc_public_entities WHERE id = NEW.matched_entity_id), FALSE),
            COALESCE(NEW.match_method, 'direct')
        )
        ON CONFLICT (entity_id, source) DO UPDATE
        SET
            last_seen_at = GREATEST(
                COALESCE(public.entity_coverage.last_seen_at, '1970-01-01'::date),
                COALESCE(NEW.data_publicacao, '1970-01-01'::date)
            ),
            total_bids = public.entity_coverage.total_bids + 1,
            is_covered = GREATEST(
                COALESCE(public.entity_coverage.last_seen_at, '1970-01-01'::date),
                COALESCE(NEW.data_publicacao, '1970-01-01'::date)
            ) >= CURRENT_DATE - 90,
            match_method = CASE
                WHEN public.entity_coverage.match_method IN ('direct', 'hierarchical') THEN public.entity_coverage.match_method
                ELSE COALESCE(NEW.match_method, 'direct')
            END;
    END IF;
    RETURN NEW;
END;
$$;

-- Trigger function: update when matched_entity_id is set after initial insert
CREATE OR REPLACE FUNCTION public.update_entity_coverage_on_update()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.matched_entity_id IS NOT NULL
       AND (OLD.matched_entity_id IS NULL OR OLD.matched_entity_id <> NEW.matched_entity_id)
    THEN
        INSERT INTO public.entity_coverage (
            entity_id, source, last_seen_at, total_bids, is_covered, within_200km, match_method
        )
        VALUES (
            NEW.matched_entity_id,
            NEW.source,
            NEW.data_publicacao,
            1,
            COALESCE(NEW.data_publicacao >= CURRENT_DATE - 90, FALSE),
            COALESCE((SELECT raio_200km FROM public.sc_public_entities WHERE id = NEW.matched_entity_id), FALSE),
            COALESCE(NEW.match_method, 'direct')
        )
        ON CONFLICT (entity_id, source) DO UPDATE
        SET
            last_seen_at = GREATEST(
                COALESCE(public.entity_coverage.last_seen_at, '1970-01-01'::date),
                COALESCE(NEW.data_publicacao, '1970-01-01'::date)
            ),
            total_bids = public.entity_coverage.total_bids + 1,
            is_covered = GREATEST(
                COALESCE(public.entity_coverage.last_seen_at, '1970-01-01'::date),
                COALESCE(NEW.data_publicacao, '1970-01-01'::date)
            ) >= CURRENT_DATE - 90,
            match_method = CASE
                WHEN public.entity_coverage.match_method IN ('direct', 'hierarchical')
                THEN public.entity_coverage.match_method
                ELSE COALESCE(NEW.match_method, 'direct')
            END;
    END IF;
    RETURN NEW;
END;
$$;

-- Recreate triggers (drop first to avoid duplicates)
DROP TRIGGER IF EXISTS trg_bids_coverage ON public.pncp_raw_bids;
CREATE TRIGGER trg_bids_coverage
    AFTER INSERT ON public.pncp_raw_bids
    FOR EACH ROW
    EXECUTE FUNCTION public.update_entity_coverage();

DROP TRIGGER IF EXISTS trg_bids_coverage_update ON public.pncp_raw_bids;
CREATE TRIGGER trg_bids_coverage_update
    AFTER UPDATE ON public.pncp_raw_bids
    FOR EACH ROW
    WHEN (OLD.matched_entity_id IS DISTINCT FROM NEW.matched_entity_id)
    EXECUTE FUNCTION public.update_entity_coverage_on_update();

-- ============================================================
-- 5. Recreate v_unmatched_bids view (from migration 011)
-- ============================================================
CREATE OR REPLACE VIEW public.v_unmatched_bids AS
SELECT
    pncp_id,
    source,
    orgao_cnpj,
    orgao_razao_social,
    municipio,
    codigo_municipio_ibge,
    data_publicacao,
    match_method,
    match_score,
    match_confidence,
    ingested_at,
    CASE
        WHEN orgao_cnpj IS NOT NULL AND orgao_cnpj != '' THEN 'has_cnpj'
        ELSE 'name_only'
    END AS match_opportunity,
    CASE
        WHEN data_publicacao >= CURRENT_DATE - 90 THEN 'recent'
        ELSE 'historical'
    END AS recency
FROM public.pncp_raw_bids
WHERE matched_entity_id IS NULL
  AND (
    (orgao_cnpj IS NOT NULL AND orgao_cnpj != '')
    OR (orgao_razao_social IS NOT NULL AND orgao_razao_social != '')
  )
ORDER BY data_publicacao DESC NULLS LAST, ingested_at DESC;

COMMENT ON VIEW public.v_unmatched_bids IS
    'Bids sem matched_entity_id — para debugging do entity name-matching';

COMMENT ON COLUMN public.v_unmatched_bids.match_opportunity IS
    'Indica se o bid tem CNPJ (has_cnpj) ou apenas nome (name_only) para match';
COMMENT ON COLUMN public.v_unmatched_bids.recency IS
    'Indica se o bid e recente (90 dias) ou historico';

-- ============================================================
-- 6. Create missing views (v_coverage_trend, generate_coverage_snapshot)
-- ============================================================

-- v_coverage_trend — from migration 012
CREATE OR REPLACE VIEW public.v_coverage_trend AS
SELECT
    snapshot_date,
    source,
    total_entities,
    covered_entities,
    pct_covered,
    pct_covered - LAG(pct_covered) OVER (
        PARTITION BY source ORDER BY snapshot_date
    ) AS variacao_pct,
    ROW_NUMBER() OVER (PARTITION BY source ORDER BY snapshot_date DESC) AS rn_desc
FROM public.coverage_snapshots
ORDER BY snapshot_date DESC, source;

COMMENT ON VIEW public.v_coverage_trend IS
    'Evolucao semanal da cobertura com calculo de variacao';

-- generate_coverage_snapshot() function — from migration 012
CREATE OR REPLACE FUNCTION public.generate_coverage_snapshot(snap_date DATE DEFAULT CURRENT_DATE)
RETURNS INT
LANGUAGE plpgsql AS $$
DECLARE
    inserted INT := 0;
    rec RECORD;
BEGIN
    FOR rec IN
        SELECT
            ec.source,
            COUNT(*) AS total_entities,
            SUM(CASE WHEN ec.is_covered THEN 1 ELSE 0 END) AS covered_entities
        FROM public.entity_coverage ec
        WHERE EXISTS (
            SELECT 1 FROM public.sc_public_entities e
            WHERE e.id = ec.entity_id AND e.is_active = TRUE
        )
        GROUP BY ec.source
    LOOP
        INSERT INTO public.coverage_snapshots (snapshot_date, source, total_entities, covered_entities, pct_covered)
        VALUES (
            snap_date,
            rec.source,
            rec.total_entities,
            rec.covered_entities,
            ROUND(100.0 * rec.covered_entities / NULLIF(rec.total_entities, 0), 2)
        )
        ON CONFLICT DO NOTHING;
        inserted := inserted + 1;
    END LOOP;

    RETURN inserted;
END;
$$;

COMMENT ON FUNCTION public.generate_coverage_snapshot IS
    'Gera snapshot de cobertura para todas as fontes';

-- ============================================================
-- 7. Recreate v_coverage_summary (with public prefix)
-- ============================================================
CREATE OR REPLACE VIEW public.v_coverage_summary AS
SELECT
    ec.source,
    ec.within_200km,
    ec.is_covered,
    COUNT(*) AS entity_count,
    ROUND(
        (COUNT(*)::NUMERIC * 100.0) / NULLIF(SUM(COUNT(*)) OVER (PARTITION BY ec.within_200km), 0), 1
    ) AS pct
FROM public.entity_coverage ec
WHERE EXISTS (
    SELECT 1 FROM public.sc_public_entities e
    WHERE e.id = ec.entity_id AND e.is_active = TRUE
)
GROUP BY ec.source, ec.within_200km, ec.is_covered
ORDER BY ec.source, ec.within_200km, ec.is_covered;

COMMENT ON VIEW public.v_coverage_summary IS
    'Sumario de cobertura por source e raio_200km — COVERAGE-2.4';

-- ============================================================
-- 8. Consistency check: find entities with bids but no coverage
-- ============================================================

-- Log inconsistencies (these should be resolved by the rebuild above)
DO $$
DECLARE
    inconsistent_count INT;
BEGIN
    SELECT COUNT(*) INTO inconsistent_count
    FROM public.sc_public_entities e
    WHERE e.id IN (
        SELECT DISTINCT matched_entity_id FROM public.pncp_raw_bids
        WHERE matched_entity_id IS NOT NULL
    )
    AND NOT EXISTS (
        SELECT 1 FROM public.entity_coverage ec
        WHERE ec.entity_id = e.id AND ec.is_covered = TRUE
    );

    IF inconsistent_count > 0 THEN
        RAISE WARNING 'Entities with bids but no coverage after rebuild: %', inconsistent_count;
    ELSE
        RAISE NOTICE 'All entities with bids now have coverage — consistent.';
    END IF;
END $$;

-- ============================================================
-- 9. Recreate v_coverage_gaps (public schema)
-- ============================================================
CREATE OR REPLACE VIEW public.v_coverage_gaps AS
SELECT
    e.id,
    e.razao_social,
    e.cnpj_8,
    e.municipio,
    e.natureza_juridica,
    e.raio_200km,
    e.distancia_fk,
    ARRAY(
        SELECT ec.source
        FROM public.entity_coverage ec
        WHERE ec.entity_id = e.id AND ec.is_covered = TRUE
    ) AS fontes_ativas,
    (
        SELECT COUNT(DISTINCT ec2.source)
        FROM public.entity_coverage ec2
        WHERE ec2.entity_id = e.id AND ec2.is_covered = TRUE
    ) = 0 AS gap_total
FROM public.sc_public_entities e
WHERE e.is_active = TRUE
  AND NOT EXISTS (
      SELECT 1 FROM public.entity_coverage ec
      WHERE ec.entity_id = e.id AND ec.is_covered = TRUE
  )
ORDER BY e.municipio, e.razao_social;

COMMENT ON VIEW public.v_coverage_gaps IS
    'Entes publicos com gap TOTAL de cobertura — COVERAGE-2.4';

-- ============================================================
-- 10. Metadata tracking
-- ============================================================
CREATE TABLE IF NOT EXISTS public._migrations (
    version     TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    checksum    TEXT,
    rollback_sql TEXT
);

INSERT INTO public._migrations (version, name, applied_at, checksum, rollback_sql)
VALUES (
    '021',
    'coverage-2.4_entity_coverage_rebuild',
    NOW(),
    'sha256=coverage-2-4-manual',
    'ALTER TABLE public.entity_coverage DROP COLUMN IF EXISTS match_method; DROP TRIGGER IF EXISTS trg_bids_coverage ON public.pncp_raw_bids; DROP TRIGGER IF EXISTS trg_bids_coverage_update ON public.pncp_raw_bids; DROP VIEW IF EXISTS public.v_unmatched_bids CASCADE; DROP VIEW IF EXISTS public.v_coverage_trend CASCADE; DROP FUNCTION IF EXISTS public.generate_coverage_snapshot;'
)
ON CONFLICT (version) DO NOTHING;

COMMIT;


-- ============================================================
-- Migration: 021_entity_hierarchy.sql
-- ============================================================
-- Migration 021: Entity hierarchy table for hierarchical matching
-- Story COVERAGE-1.8: Match Hierarquico Secretaria → Prefeitura
--
-- Cria tabela entity_hierarchy para vincular entidades municipais
-- (secretarias, fundacoes, autarquias, fundos) as respectivas prefeituras,
-- permitindo que entes sem match direto herdem cobertura da prefeitura.
--
-- Dependencias: Migration 007 (sc_public_entities)
--               Migration 009 (entity_coverage)

-- ============================================================
-- 1. entity_hierarchy — mapeamento hierarquico por municipio
-- ============================================================
CREATE TABLE IF NOT EXISTS entity_hierarchy (
    entity_id           INTEGER PRIMARY KEY REFERENCES sc_public_entities(id),
    parent_entity_id    INTEGER NOT NULL REFERENCES sc_public_entities(id),
    relationship        VARCHAR(32) NOT NULL CHECK (relationship IN (
                            'prefeitura', 'camara', 'autarquia',
                            'fundacao', 'fundo', 'conselho', 'outros'
                        )),
    match_confidence    VARCHAR(16) NOT NULL CHECK (match_confidence IN (
                            'direct', 'hierarchical', 'inferred'
                        )),
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

COMMENT ON TABLE entity_hierarchy IS
    'Mapeamento hierarquico de entidades municipais para suas respectivas prefeituras — Story COVERAGE-1.8';

COMMENT ON COLUMN entity_hierarchy.entity_id IS
    'ID da entidade filha (secretaria, fundacao, autarquia, etc.)';
COMMENT ON COLUMN entity_hierarchy.parent_entity_id IS
    'ID da entidade pai (prefeitura/municipio)';
COMMENT ON COLUMN entity_hierarchy.relationship IS
    'Tipo de relacao: prefeitura | camara | autarquia | fundacao | fundo | conselho | outros';
COMMENT ON COLUMN entity_hierarchy.match_confidence IS
    'Confianca do vinculo: direct | hierarchical | inferred';

-- Index para buscas por parent (prefeitura)
CREATE INDEX IF NOT EXISTS idx_entity_hierarchy_parent
    ON entity_hierarchy(parent_entity_id);

-- Index para buscas por relationship
CREATE INDEX IF NOT EXISTS idx_entity_hierarchy_relationship
    ON entity_hierarchy(relationship);

-- Index composto para cobertura hierarquica
CREATE INDEX IF NOT EXISTS idx_entity_hierarchy_coverage
    ON entity_hierarchy(entity_id, parent_entity_id)
    INCLUDE (relationship);

-- ============================================================
-- 2. Funcao para atualizar updated_at automaticamente
-- ============================================================
CREATE OR REPLACE FUNCTION update_entity_hierarchy_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_entity_hierarchy_timestamp
    BEFORE UPDATE ON entity_hierarchy
    FOR EACH ROW
    EXECUTE FUNCTION update_entity_hierarchy_timestamp();

-- ============================================================
-- 3. View para cobertura hierarquica (entes com cobertura herdada)
-- ============================================================
CREATE OR REPLACE VIEW v_hierarchical_coverage AS
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
FROM sc_public_entities e
JOIN entity_hierarchy h ON h.entity_id = e.id
JOIN sc_public_entities p ON p.id = h.parent_entity_id
LEFT JOIN entity_coverage ec ON ec.entity_id = e.id AND ec.source = 'pncp'
LEFT JOIN entity_coverage pec ON pec.entity_id = h.parent_entity_id AND pec.source = 'pncp'
WHERE e.is_active = TRUE;

COMMENT ON VIEW v_hierarchical_coverage IS
    'Visao consolidada da cobertura hierarquica — Story COVERAGE-1.8';


-- ============================================================
-- Migration: 021_sc_dados_abertos_municipio.sql
-- ============================================================
-- Migration 021: Add codigo_municipio_ibge to pncp_supplier_contracts + audit log
--
-- Context: COVERAGE-1.9 backfill for 75.523 SC Dados Abertos contracts
-- without municipio. Adds columns needed for entity matching enrichment,
-- and an audit log table to track inference success/failure per CNPJ.

-- ---------------------------------------------------------------------------
-- 1. Add codigo_municipio_ibge to pncp_supplier_contracts
-- ---------------------------------------------------------------------------
ALTER TABLE pncp_supplier_contracts
    ADD COLUMN IF NOT EXISTS codigo_municipio_ibge TEXT;

COMMENT ON COLUMN pncp_supplier_contracts.codigo_municipio_ibge
    IS '7-digit IBGE municipality code, backfilled by sc_dados_abertos_backfill.py';

-- ---------------------------------------------------------------------------
-- 2. Add municipio_inferido flag (optional, for audit traceability)
-- ---------------------------------------------------------------------------
ALTER TABLE pncp_supplier_contracts
    ADD COLUMN IF NOT EXISTS municipio_inferido BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN pncp_supplier_contracts.municipio_inferido
    IS 'TRUE when municipio was inferred (not from original source)';

-- ---------------------------------------------------------------------------
-- 3. Audit log table for backfill execution traceability
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sc_dados_abertos_backfill_log (
    id              SERIAL PRIMARY KEY,
    orgao_cnpj      TEXT NOT NULL,                    -- contracting authority CNPJ
    match_method    TEXT,                             -- 'sc_public_entities', 'brasil_api', NULL
    municipio       TEXT,                             -- inferred municipio (NULL if failed)
    codigo_ibge     TEXT,                             -- inferred IBGE code (NULL if failed)
    motivo          TEXT,                             -- success reason or failure motivo
    executed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE sc_dados_abertos_backfill_log
    IS 'Audit log for COVERAGE-1.9 municipio backfill: tracks every CNPJ attempt and its outcome';

CREATE INDEX IF NOT EXISTS idx_sdabfl_orgao_cnpj
    ON sc_dados_abertos_backfill_log (orgao_cnpj);

CREATE INDEX IF NOT EXISTS idx_sdabfl_motivo
    ON sc_dados_abertos_backfill_log (motivo);

CREATE INDEX IF NOT EXISTS idx_sdabfl_executed_at
    ON sc_dados_abertos_backfill_log (executed_at DESC);


-- ============================================================
-- Migration: 021b_views_functions.sql
-- ============================================================
-- Migration 021b: Views and functions for COVERAGE-2.4
-- Executed after 021a (column, data, triggers)

BEGIN;

-- 5. v_unmatched_bids view
CREATE OR REPLACE VIEW public.v_unmatched_bids AS
SELECT
    pncp_id, source, orgao_cnpj, orgao_razao_social,
    municipio, codigo_municipio_ibge, data_publicacao,
    match_method, match_score, match_confidence, ingested_at,
    CASE
        WHEN orgao_cnpj IS NOT NULL AND orgao_cnpj != '' THEN 'has_cnpj'
        ELSE 'name_only'
    END AS match_opportunity,
    CASE
        WHEN data_publicacao >= CURRENT_DATE - 90 THEN 'recent'
        ELSE 'historical'
    END AS recency
FROM public.pncp_raw_bids
WHERE matched_entity_id IS NULL
  AND ((orgao_cnpj IS NOT NULL AND orgao_cnpj != '')
       OR (orgao_razao_social IS NOT NULL AND orgao_razao_social != ''))
ORDER BY data_publicacao DESC NULLS LAST, ingested_at DESC;

COMMENT ON VIEW public.v_unmatched_bids IS
    'Bids sem matched_entity_id — para debugging do entity name-matching';

-- 6. v_coverage_trend
CREATE OR REPLACE VIEW public.v_coverage_trend AS
SELECT
    snapshot_date, source, total_entities, covered_entities, pct_covered,
    pct_covered - LAG(pct_covered) OVER (
        PARTITION BY source ORDER BY snapshot_date
    ) AS variacao_pct,
    ROW_NUMBER() OVER (PARTITION BY source ORDER BY snapshot_date DESC) AS rn_desc
FROM public.coverage_snapshots
ORDER BY snapshot_date DESC, source;

COMMENT ON VIEW public.v_coverage_trend IS
    'Evolucao semanal da cobertura com calculo de variacao';

-- generate_coverage_snapshot function
CREATE OR REPLACE FUNCTION public.generate_coverage_snapshot(snap_date DATE DEFAULT CURRENT_DATE)
RETURNS INT
LANGUAGE plpgsql AS $$
DECLARE
    inserted INT := 0;
    rec RECORD;
BEGIN
    FOR rec IN
        SELECT ec.source,
               COUNT(*) AS total_entities,
               SUM(CASE WHEN ec.is_covered THEN 1 ELSE 0 END) AS covered_entities
        FROM public.entity_coverage ec
        WHERE EXISTS (
            SELECT 1 FROM public.sc_public_entities e
            WHERE e.id = ec.entity_id AND e.is_active = TRUE
        )
        GROUP BY ec.source
    LOOP
        INSERT INTO public.coverage_snapshots (snapshot_date, source, total_entities, covered_entities, pct_covered)
        VALUES (snap_date, rec.source, rec.total_entities, rec.covered_entities,
                ROUND(100.0 * rec.covered_entities / NULLIF(rec.total_entities, 0), 2))
        ON CONFLICT DO NOTHING;
        inserted := inserted + 1;
    END LOOP;
    RETURN inserted;
END;
$$;

COMMENT ON FUNCTION public.generate_coverage_snapshot IS
    'Gera snapshot de cobertura para todas as fontes';

-- 7. v_coverage_summary (recreate with public schema)
CREATE OR REPLACE VIEW public.v_coverage_summary AS
SELECT ec.source, ec.within_200km, ec.is_covered,
       COUNT(*) AS entity_count,
       ROUND((COUNT(*)::NUMERIC * 100.0) / NULLIF(SUM(COUNT(*)) OVER (PARTITION BY ec.within_200km), 0), 1) AS pct
FROM public.entity_coverage ec
WHERE EXISTS (SELECT 1 FROM public.sc_public_entities e WHERE e.id = ec.entity_id AND e.is_active = TRUE)
GROUP BY ec.source, ec.within_200km, ec.is_covered
ORDER BY ec.source, ec.within_200km, ec.is_covered;

COMMENT ON VIEW public.v_coverage_summary IS
    'Sumario de cobertura por source e raio_200km — COVERAGE-2.4';

-- 9. v_coverage_gaps (recreate with public schema — drop first to avoid column mismatch)
DROP VIEW IF EXISTS public.v_coverage_gaps CASCADE;
CREATE OR REPLACE VIEW public.v_coverage_gaps AS
SELECT e.id, e.razao_social, e.cnpj_8, e.municipio,
       e.natureza_juridica, e.raio_200km,
       ARRAY(SELECT ec.source FROM public.entity_coverage ec
             WHERE ec.entity_id = e.id AND ec.is_covered = TRUE) AS fontes_ativas,
       (SELECT COUNT(DISTINCT ec2.source) FROM public.entity_coverage ec2
        WHERE ec2.entity_id = e.id AND ec2.is_covered = TRUE) = 0 AS gap_total
FROM public.sc_public_entities e
WHERE e.is_active = TRUE
  AND NOT EXISTS (SELECT 1 FROM public.entity_coverage ec
                  WHERE ec.entity_id = e.id AND ec.is_covered = TRUE)
ORDER BY e.municipio, e.razao_social;

COMMENT ON VIEW public.v_coverage_gaps IS
    'Entes publicos com gap TOTAL de cobertura — COVERAGE-2.4';

COMMIT;


-- ============================================================
-- Migration: 022_match_method_coverage.sql
-- ============================================================
-- Migration 022: Add match_method column to entity_coverage
-- Story COVERAGE-1.8: Match Hierarquico Secretaria → Prefeitura
--
-- Adiciona coluna match_method a entity_coverage para distinguir
-- cobertura direta (CNPJ match) de cobertura hierarquica (herdada
-- da prefeitura via entity_hierarchy).
--
-- Dependencias: Migration 021 (entity_hierarchy)
--               Migration 009 (entity_coverage)

-- ============================================================
-- 1. Add match_method column
-- ============================================================
ALTER TABLE entity_coverage
    ADD COLUMN IF NOT EXISTS match_method TEXT;

COMMENT ON COLUMN entity_coverage.match_method IS
    'Metodo de cobertura: direct (match CNPJ) | hierarchical (herdado via entity_hierarchy) | null (sem cobertura)';

-- ============================================================
-- 2. Update trigger functions to include match_method
-- ============================================================

-- Recreate INSERT trigger with match_method support
CREATE OR REPLACE FUNCTION update_entity_coverage()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.matched_entity_id IS NOT NULL THEN
        INSERT INTO entity_coverage (entity_id, source, last_seen_at, total_bids, is_covered, within_200km, match_method)
        VALUES (
            NEW.matched_entity_id,
            NEW.source,
            NEW.data_publicacao,
            1,
            COALESCE(NEW.data_publicacao >= CURRENT_DATE - 90, FALSE),
            COALESCE((SELECT raio_200km FROM sc_public_entities WHERE id = NEW.matched_entity_id), FALSE),
            COALESCE(NEW.match_method, 'direct')
        )
        ON CONFLICT (entity_id, source) DO UPDATE
        SET
            last_seen_at = GREATEST(
                COALESCE(entity_coverage.last_seen_at, '1970-01-01'::date),
                COALESCE(NEW.data_publicacao, '1970-01-01'::date)
            ),
            total_bids = entity_coverage.total_bids + 1,
            is_covered = (
                GREATEST(
                    COALESCE(entity_coverage.last_seen_at, '1970-01-01'::date),
                    COALESCE(NEW.data_publicacao, '1970-01-01'::date)
                ) >= CURRENT_DATE - 90
            ),
            match_method = CASE
                WHEN entity_coverage.match_method IS NULL OR entity_coverage.match_method = 'hierarchical' THEN
                    COALESCE(NEW.match_method, 'direct')
                ELSE entity_coverage.match_method
            END;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Recreate UPDATE trigger with match_method support
CREATE OR REPLACE FUNCTION update_entity_coverage_on_update()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.matched_entity_id IS NOT NULL
       AND (OLD.matched_entity_id IS NULL OR OLD.matched_entity_id <> NEW.matched_entity_id)
    THEN
        INSERT INTO entity_coverage (entity_id, source, last_seen_at, total_bids, is_covered, within_200km, match_method)
        VALUES (
            NEW.matched_entity_id,
            NEW.source,
            NEW.data_publicacao,
            1,
            COALESCE(NEW.data_publicacao >= CURRENT_DATE - 90, FALSE),
            COALESCE((SELECT raio_200km FROM sc_public_entities WHERE id = NEW.matched_entity_id), FALSE),
            COALESCE(NEW.match_method, 'direct')
        )
        ON CONFLICT (entity_id, source) DO UPDATE
        SET
            last_seen_at = GREATEST(
                COALESCE(entity_coverage.last_seen_at, '1970-01-01'::date),
                COALESCE(NEW.data_publicacao, '1970-01-01'::date)
            ),
            total_bids = entity_coverage.total_bids + 1,
            is_covered = (
                GREATEST(
                    COALESCE(entity_coverage.last_seen_at, '1970-01-01'::date),
                    COALESCE(NEW.data_publicacao, '1970-01-01'::date)
                ) >= CURRENT_DATE - 90
            ),
            match_method = CASE
                WHEN entity_coverage.match_method IS NULL OR entity_coverage.match_method = 'hierarchical' THEN
                    COALESCE(NEW.match_method, 'direct')
                ELSE entity_coverage.match_method
            END;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- 3. Index for match_method queries
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_cov_match_method
    ON entity_coverage (match_method)
    WHERE match_method IS NOT NULL;

-- ============================================================
-- 4. Update v_coverage_summary to include match_method
-- ============================================================
CREATE OR REPLACE VIEW v_coverage_summary AS
SELECT
    ec.source,
    ec.within_200km,
    ec.is_covered,
    ec.match_method,
    COUNT(*) AS entity_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY ec.within_200km), 1) AS pct
FROM entity_coverage ec
WHERE EXISTS (SELECT 1 FROM sc_public_entities e WHERE e.id = ec.entity_id AND e.is_active = TRUE)
GROUP BY ec.source, ec.within_200km, ec.is_covered, ec.match_method
ORDER BY ec.source, ec.within_200km, ec.is_covered, ec.match_method;


-- ============================================================
-- Migration: 023_pncp_engineering_pipeline.sql
-- ============================================================
BEGIN;

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

UPDATE public.pncp_raw_bids
SET numero_controle_pncp = COALESCE(numero_controle_pncp, pncp_id)
WHERE numero_controle_pncp IS NULL;

CREATE INDEX IF NOT EXISTS idx_bids_numero_controle_pncp ON public.pncp_raw_bids (numero_controle_pncp);
CREATE INDEX IF NOT EXISTS idx_bids_ano_sequencial ON public.pncp_raw_bids (ano_compra, sequencial_compra);
CREATE INDEX IF NOT EXISTS idx_bids_source_id ON public.pncp_raw_bids (source_id);

CREATE TABLE IF NOT EXISTS public.sc_municipalities (
    codigo_ibge TEXT PRIMARY KEY,
    municipio TEXT NOT NULL,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    source TEXT NOT NULL DEFAULT 'sc_public_entities_seed',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO public.sc_municipalities (codigo_ibge, municipio, latitude, longitude, source)
SELECT DISTINCT ON (codigo_ibge)
    e.codigo_ibge,
    e.municipio,
    e.latitude,
    e.longitude,
    'sc_public_entities_seed'
FROM public.sc_public_entities e
WHERE e.codigo_ibge IS NOT NULL
  AND e.codigo_ibge <> ''
  AND e.municipio IS NOT NULL
ORDER BY e.codigo_ibge, e.raio_200km DESC, e.id
ON CONFLICT (codigo_ibge) DO UPDATE
SET municipio = EXCLUDED.municipio,
    latitude = COALESCE(public.sc_municipalities.latitude, EXCLUDED.latitude),
    longitude = COALESCE(public.sc_municipalities.longitude, EXCLUDED.longitude),
    updated_at = NOW();

CREATE TABLE IF NOT EXISTS public.pncp_enrichment_cache (
    pncp_id TEXT PRIMARY KEY REFERENCES public.pncp_raw_bids(pncp_id) ON DELETE CASCADE,
    detail_payload JSONB,
    items_payload JSONB,
    documents_payload JSONB,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.engineering_opportunities (
    id BIGSERIAL PRIMARY KEY,
    pncp_id TEXT NOT NULL UNIQUE REFERENCES public.pncp_raw_bids(pncp_id) ON DELETE CASCADE,
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

CREATE INDEX IF NOT EXISTS idx_eng_op_is_engineering ON public.engineering_opportunities (is_engineering);
CREATE INDEX IF NOT EXISTS idx_eng_op_engineering_score ON public.engineering_opportunities (engineering_score DESC);
CREATE INDEX IF NOT EXISTS idx_eng_op_within_200km ON public.engineering_opportunities (within_200km);
CREATE INDEX IF NOT EXISTS idx_eng_op_ibge ON public.engineering_opportunities (codigo_municipio_ibge);
CREATE INDEX IF NOT EXISTS idx_eng_op_orgao_cnpj ON public.engineering_opportunities (orgao_cnpj);
CREATE INDEX IF NOT EXISTS idx_eng_op_data_publicacao ON public.engineering_opportunities (data_publicacao DESC);
CREATE INDEX IF NOT EXISTS idx_eng_op_data_encerramento ON public.engineering_opportunities (data_encerramento DESC);
CREATE INDEX IF NOT EXISTS idx_eng_op_modalidade_id ON public.engineering_opportunities (modalidade_id);

COMMENT ON TABLE public.sc_municipalities IS
    'Referencia municipal usada na geolocalizacao do pipeline PNCP. Origem inicial: distinct de sc_public_entities seed.';

COMMENT ON TABLE public.engineering_opportunities IS
    'Camada derivada com classificacao de engenharia civil, geografia SC e links separados do PNCP.';

CREATE OR REPLACE FUNCTION public.upsert_pncp_raw_bids(p_records JSONB)
RETURNS TABLE (inserted INTEGER, updated INTEGER, unchanged INTEGER)
LANGUAGE plpgsql
SET search_path TO public
AS $$
DECLARE
    v_total     INT;
    v_inserted  INT;
    v_updated   INT;
BEGIN
    IF p_records IS NULL OR jsonb_array_length(p_records) = 0 THEN
        RETURN QUERY SELECT 0, 0, 0;
        RETURN;
    END IF;

    v_total := jsonb_array_length(p_records);

    WITH src AS (
        SELECT
            rec->>'pncp_id' AS pncp_id,
            COALESCE(rec->>'numero_controle_pncp', rec->>'pncp_id') AS numero_controle_pncp,
            rec->>'objeto_compra' AS objeto_compra,
            rec->>'informacao_complementar' AS informacao_complementar,
            NULLIF(rec->>'valor_total_estimado', '')::NUMERIC AS valor_total_estimado,
            NULLIF(rec->>'modalidade_id', '')::INTEGER AS modalidade_id,
            rec->>'modalidade_nome' AS modalidade_nome,
            rec->>'situacao_compra' AS situacao_compra,
            rec->>'esfera_id' AS esfera_id,
            rec->>'uf' AS uf,
            rec->>'municipio' AS municipio,
            rec->>'codigo_municipio_ibge' AS codigo_municipio_ibge,
            rec->>'orgao_razao_social' AS orgao_razao_social,
            rec->>'orgao_cnpj' AS orgao_cnpj,
            rec->>'unidade_nome' AS unidade_nome,
            NULLIF(rec->>'data_publicacao', '')::TIMESTAMPTZ AS data_publicacao,
            NULLIF(rec->>'data_abertura', '')::TIMESTAMPTZ AS data_abertura,
            NULLIF(rec->>'data_encerramento', '')::TIMESTAMPTZ AS data_encerramento,
            rec->>'link_sistema_origem' AS link_sistema_origem,
            rec->>'link_pncp' AS link_pncp,
            rec->>'content_hash' AS content_hash,
            COALESCE(rec->>'source', 'pncp') AS source,
            rec->>'source_id' AS source_id,
            rec->>'crawl_batch_id' AS crawl_batch_id,
            NULLIF(rec->>'ano_compra', '')::INTEGER AS ano_compra,
            NULLIF(rec->>'sequencial_compra', '')::INTEGER AS sequencial_compra,
            COALESCE(NULLIF(rec->>'synthetic_id', '')::BOOLEAN, FALSE) AS synthetic_id,
            rec->>'synthetic_id_reason' AS synthetic_id_reason,
            COALESCE(NULLIF(rec->>'is_active', '')::BOOLEAN, TRUE) AS is_active
        FROM jsonb_array_elements(p_records) AS rec
    ),
    upserted AS (
        INSERT INTO public.pncp_raw_bids (
            pncp_id, numero_controle_pncp, objeto_compra, informacao_complementar,
            valor_total_estimado, modalidade_id, modalidade_nome, situacao_compra,
            esfera_id, uf, municipio, codigo_municipio_ibge, orgao_razao_social,
            orgao_cnpj, unidade_nome, data_publicacao, data_abertura, data_encerramento,
            link_sistema_origem, link_pncp, content_hash, source, source_id,
            crawl_batch_id, ano_compra, sequencial_compra, synthetic_id,
            synthetic_id_reason, is_active
        )
        SELECT
            pncp_id, numero_controle_pncp, objeto_compra, informacao_complementar,
            valor_total_estimado, modalidade_id, modalidade_nome, situacao_compra,
            esfera_id, uf, municipio, codigo_municipio_ibge, orgao_razao_social,
            orgao_cnpj, unidade_nome, data_publicacao, data_abertura, data_encerramento,
            link_sistema_origem, link_pncp, content_hash, source, source_id,
            crawl_batch_id, ano_compra, sequencial_compra, synthetic_id,
            synthetic_id_reason, is_active
        FROM src
        ON CONFLICT (pncp_id) DO UPDATE
        SET
            numero_controle_pncp = EXCLUDED.numero_controle_pncp,
            objeto_compra = EXCLUDED.objeto_compra,
            informacao_complementar = EXCLUDED.informacao_complementar,
            valor_total_estimado = EXCLUDED.valor_total_estimado,
            modalidade_id = EXCLUDED.modalidade_id,
            modalidade_nome = EXCLUDED.modalidade_nome,
            situacao_compra = EXCLUDED.situacao_compra,
            esfera_id = EXCLUDED.esfera_id,
            uf = EXCLUDED.uf,
            municipio = EXCLUDED.municipio,
            codigo_municipio_ibge = EXCLUDED.codigo_municipio_ibge,
            orgao_razao_social = EXCLUDED.orgao_razao_social,
            orgao_cnpj = EXCLUDED.orgao_cnpj,
            unidade_nome = EXCLUDED.unidade_nome,
            data_publicacao = EXCLUDED.data_publicacao,
            data_abertura = EXCLUDED.data_abertura,
            data_encerramento = EXCLUDED.data_encerramento,
            link_sistema_origem = EXCLUDED.link_sistema_origem,
            link_pncp = EXCLUDED.link_pncp,
            content_hash = EXCLUDED.content_hash,
            source = EXCLUDED.source,
            source_id = EXCLUDED.source_id,
            crawl_batch_id = EXCLUDED.crawl_batch_id,
            ano_compra = EXCLUDED.ano_compra,
            sequencial_compra = EXCLUDED.sequencial_compra,
            synthetic_id = EXCLUDED.synthetic_id,
            synthetic_id_reason = EXCLUDED.synthetic_id_reason,
            is_active = EXCLUDED.is_active,
            updated_at = NOW()
        RETURNING (xmax = 0) AS was_inserted
    )
    SELECT
        COALESCE(SUM(CASE WHEN was_inserted THEN 1 ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN NOT was_inserted THEN 1 ELSE 0 END), 0)
    INTO v_inserted, v_updated
    FROM upserted;

    RETURN QUERY
    SELECT v_inserted, v_updated, GREATEST(0, v_total - v_inserted - v_updated);
END;
$$;

COMMIT;


-- ============================================================
-- Migration: 024_coverage_evidence_ledger.sql
-- ============================================================
-- Migration 024: Coverage Evidence Ledger
-- Canonical entity/source evidence table for auditable coverage truth.
-- Each row records one observation: an entity checked against a source
-- during a specific run, with exactly one machine-readable state.
--
-- Design constraints:
--   - Idempotent: all CREATE use IF NOT EXISTS.
--   - Never converts an exception into an empty success.
--   - One state per row — no NULL state after insert.

BEGIN;

-- ---------------------------------------------------------------------------
-- Evidence state enum
-- ---------------------------------------------------------------------------

DO $$ BEGIN
    CREATE TYPE evidence_state AS ENUM (
        'success_with_data',   -- Source returned data for this entity
        'success_zero',        -- Source checked, confirmed zero records (legitimate empty)
        'partial',             -- Source returned partial data (incomplete run)
        'connection_failed',   -- Network/DNS/TCP-level failure
        'auth_failed',         -- Credentials rejected or expired
        'parse_failed',        -- Response received but could not be parsed
        'transform_failed',    -- Parsed OK but transform step failed
        'persist_failed',      -- Transformed OK but DB persist failed
        'not_applicable',      -- Source does not apply to this entity type
        'not_investigated'     -- Source exists but has never been checked for this entity
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- ---------------------------------------------------------------------------
-- Evidence ledger table
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS coverage_evidence (
    id              BIGSERIAL PRIMARY KEY,
    entity_id       INT,                          -- NULL = source-level aggregate record
    source          TEXT NOT NULL,
    data_type       TEXT NOT NULL DEFAULT 'bids',
    -- queried_period: when the source was asked about
    queried_start   DATE,
    queried_end     DATE,
    -- Run identity
    run_id          TEXT NOT NULL,
    -- Timestamps
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Counts
    count_obtained     INT NOT NULL DEFAULT 0,
    count_transformed  INT NOT NULL DEFAULT 0,
    count_persisted    INT NOT NULL DEFAULT 0,
    -- State machine
    state           evidence_state NOT NULL DEFAULT 'not_investigated',
    -- Error context (populated when state indicates failure)
    error_message   TEXT,
    error_code      TEXT,
    -- Arbitrary metadata
    metadata        JSONB DEFAULT '{}'::jsonb,

    -- One evidence row per entity+source+data_type+run_id
    UNIQUE (entity_id, source, data_type, run_id)
);

-- ---------------------------------------------------------------------------
-- Indexes for metric queries
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_ce_state
    ON coverage_evidence (state);

CREATE INDEX IF NOT EXISTS idx_ce_entity_source
    ON coverage_evidence (entity_id, source);

CREATE INDEX IF NOT EXISTS idx_ce_run
    ON coverage_evidence (run_id);

CREATE INDEX IF NOT EXISTS idx_ce_completed
    ON coverage_evidence (completed_at);

CREATE INDEX IF NOT EXISTS idx_ce_source_state
    ON coverage_evidence (source, state);

-- ---------------------------------------------------------------------------
-- Helper: get latest evidence state per (entity, source) combination
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_latest_evidence AS
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
    error_code
FROM coverage_evidence
ORDER BY entity_id, source, data_type, completed_at DESC;

-- ---------------------------------------------------------------------------
-- Helper: source health summary
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_source_health AS
SELECT
    source,
    COUNT(*) AS total_evidence_rows,
    COUNT(*) FILTER (WHERE state = 'success_with_data') AS success_with_data,
    COUNT(*) FILTER (WHERE state = 'success_zero') AS success_zero,
    COUNT(*) FILTER (WHERE state = 'partial') AS partial,
    COUNT(*) FILTER (WHERE state = 'connection_failed') AS connection_failed,
    COUNT(*) FILTER (WHERE state = 'auth_failed') AS auth_failed,
    COUNT(*) FILTER (WHERE state = 'parse_failed') AS parse_failed,
    COUNT(*) FILTER (WHERE state = 'transform_failed') AS transform_failed,
    COUNT(*) FILTER (WHERE state = 'persist_failed') AS persist_failed,
    COUNT(*) FILTER (WHERE state = 'not_applicable') AS not_applicable,
    COUNT(*) FILTER (WHERE state = 'not_investigated') AS not_investigated,
    MAX(completed_at) AS last_check_at
FROM v_latest_evidence
GROUP BY source
ORDER BY source;

COMMIT;


-- ============================================================
-- Migration: 025_contract_intel_views.sql
-- ============================================================
-- Migration 025: Contract Intelligence Analytical Views
-- Canonical SQL views for the Contract Intelligence vertical slice.
--
-- Provides:
--   1. v_contract_intel_historico    — Historical contracts for target universe
--   2. v_contract_intel_fornecedores  — Supplier/competitor analytics
--   3. v_contract_intel_ativos_90_180 — Active contracts ending in 90–180 days
--   4. v_contract_intel_percentis     — P25/P50/P75 value/ticket by category
--
-- Design constraints:
--   - Idempotent: all CREATE use IF NOT EXISTS / OR REPLACE.
--   - Never invents metrics (deságio, win rate, etc.) without data.
--   - "Valor global de contrato" is NOT called "preço praticado".
--   - Percentiles use PERCENTILE_CONT (SQL standard, not approximations).
--   - All views are read-only analytical layers over pncp_supplier_contracts.
--
-- IMPORTANT: These views require the target universe table (sc_public_entities
-- with raio_200km flag populated) and pncp_supplier_contracts populated.
-- If tables are empty, views return zero rows — not an error.

BEGIN;

-- ---------------------------------------------------------------------------
-- View 1: Historical contracts for target universe entities
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_contract_intel_historico AS
SELECT
    c.contrato_id,
    c.orgao_cnpj,
    c.orgao_nome,
    c.fornecedor_cnpj,
    c.fornecedor_nome,
    c.objeto_contrato,
    c.valor_total,
    c.data_inicio,
    c.data_fim,
    c.data_publicacao,
    c.uf,
    c.municipio,
    e.razao_social AS ente_razao_social,
    e.municipio AS ente_municipio,
    e.distancia_fk AS ente_distancia_km,
    e.raio_200km,
    c.ingested_at
FROM pncp_supplier_contracts c
JOIN sc_public_entities e
    ON c.orgao_cnpj LIKE e.cnpj_raiz || '%'
WHERE e.raio_200km IS TRUE
   OR e.distancia_fk <= 200.0;

COMMENT ON VIEW v_contract_intel_historico IS
'Historical contracts for public entities within 200 km of Florianópolis.';

-- ---------------------------------------------------------------------------
-- View 2: Supplier/competitor analytics by quantity, value, concentration
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_contract_intel_fornecedores AS
WITH fornecedor_orgao_agg AS (
    -- Aggregate contract values per supplier per agency first
    SELECT
        c.fornecedor_cnpj,
        c.fornecedor_nome,
        c.orgao_cnpj,
        c.orgao_nome,
        SUM(COALESCE(c.valor_total, 0)) AS valor_orgao,
        COUNT(*) AS qtd_contratos_orgao
    FROM pncp_supplier_contracts c
    JOIN sc_public_entities e
        ON c.orgao_cnpj LIKE e.cnpj_raiz || '%'
    WHERE (e.raio_200km IS TRUE OR e.distancia_fk <= 200.0)
      AND c.fornecedor_cnpj IS NOT NULL
      AND c.fornecedor_cnpj != ''
    GROUP BY c.fornecedor_cnpj, c.fornecedor_nome, c.orgao_cnpj, c.orgao_nome
),
fornecedor_totals AS (
    SELECT
        fornecedor_cnpj,
        fornecedor_nome,
        SUM(qtd_contratos_orgao)                                               AS qtd_contratos,
        SUM(valor_orgao)                                                       AS valor_total_contratos,
        ROUND(AVG(valor_orgao), 2)                                             AS valor_medio_contrato,
        COUNT(DISTINCT orgao_cnpj)                                             AS qtd_orgaos_distintos,
        -- HHI computed from per-agency shares (correct formula)
        ROUND(
            SUM(POWER(
                valor_orgao * 1.0 / NULLIF(SUM(valor_orgao) OVER (
                    PARTITION BY fornecedor_cnpj
                ), 0), 2
            )) * 10000,
            0
        )                                                                       AS hhi_concentracao,
        STRING_AGG(DISTINCT orgao_nome, '; ' ORDER BY orgao_nome)              AS orgaos_lista
    FROM fornecedor_orgao_agg
    GROUP BY fornecedor_cnpj, fornecedor_nome
)
SELECT * FROM fornecedor_totals
ORDER BY valor_total_contratos DESC;

COMMENT ON VIEW v_contract_intel_fornecedores IS
'Supplier analytics: count, total value, average, distinct agencies, concentration (HHI).';

-- ---------------------------------------------------------------------------
-- View 3: Active contracts ending in 90–180 days
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_contract_intel_ativos_90_180 AS
SELECT
    c.contrato_id,
    c.orgao_cnpj,
    c.orgao_nome,
    c.fornecedor_cnpj,
    c.fornecedor_nome,
    c.objeto_contrato,
    c.valor_total,
    c.data_inicio,
    c.data_fim,
    (c.data_fim::date - CURRENT_DATE)                                          AS dias_ate_fim,
    c.uf,
    c.municipio,
    e.razao_social AS ente_razao_social
FROM pncp_supplier_contracts c
JOIN sc_public_entities e
    ON c.orgao_cnpj LIKE e.cnpj_raiz || '%'
WHERE (e.raio_200km IS TRUE OR e.distancia_fk <= 200.0)
  AND c.data_fim IS NOT NULL
  AND c.data_fim::date BETWEEN (CURRENT_DATE + INTERVAL '90 days')
                           AND (CURRENT_DATE + INTERVAL '180 days')
ORDER BY c.data_fim, c.valor_total DESC;

COMMENT ON VIEW v_contract_intel_ativos_90_180 IS
'Active contracts ending between 90 and 180 days from today (renewal window).';

-- ---------------------------------------------------------------------------
-- View 4: P25/P50/P75 value/ticket percentiles by contract category
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_contract_intel_percentis AS
WITH categorias AS (
    SELECT
        COALESCE(c.objeto_contrato, 'NÃO CLASSIFICADO')                        AS categoria,
        c.valor_total                                                           AS valor,
        -- Simple keyword-based category extraction (extensible)
        CASE
            WHEN c.objeto_contrato ILIKE '%obra%'
              OR c.objeto_contrato ILIKE '%construção%'
              OR c.objeto_contrato ILIKE '%pavimentação%'
              OR c.objeto_contrato ILIKE '%edificação%'
              OR c.objeto_contrato ILIKE '%engenharia%'
            THEN 'OBRAS'
            WHEN c.objeto_contrato ILIKE '%limpeza%'
              OR c.objeto_contrato ILIKE '%conservação%'
              OR c.objeto_contrato ILIKE '%manutenção%'
              OR c.objeto_contrato ILIKE '%zeladoria%'
            THEN 'FACILITIES'
            WHEN c.objeto_contrato ILIKE '%software%'
              OR c.objeto_contrato ILIKE '%ti%'
              OR c.objeto_contrato ILIKE '%tecnologia%'
              OR c.objeto_contrato ILIKE '%sistema%'
              OR c.objeto_contrato ILIKE '%informática%'
            THEN 'TI'
            WHEN c.objeto_contrato ILIKE '%saúde%'
              OR c.objeto_contrato ILIKE '%medicamento%'
              OR c.objeto_contrato ILIKE '%hospitalar%'
              OR c.objeto_contrato ILIKE '%medico%'
              OR c.objeto_contrato ILIKE '%farmacêutico%'
              OR c.objeto_contrato ILIKE '%laboratório%'
            THEN 'SAÚDE'
            WHEN c.objeto_contrato ILIKE '%alimentação%'
              OR c.objeto_contrato ILIKE '%alimento%'
              OR c.objeto_contrato ILIKE '%merenda%'
              OR c.objeto_contrato ILIKE '%gênero alimentício%'
            THEN 'ALIMENTAÇÃO'
            WHEN c.objeto_contrato ILIKE '%transporte%'
              OR c.objeto_contrato ILIKE '%veículo%'
              OR c.objeto_contrato ILIKE '%frota%'
              OR c.objeto_contrato ILIKE '%ônibus%'
              OR c.objeto_contrato ILIKE '%locação de veículo%'
            THEN 'TRANSPORTE'
            WHEN c.objeto_contrato ILIKE '%segurança%'
              OR c.objeto_contrato ILIKE '%vigilância%'
              OR c.objeto_contrato ILIKE '%monitoramento%'
              OR c.objeto_contrato ILIKE '%porteiro%'
            THEN 'SEGURANÇA'
            WHEN c.objeto_contrato ILIKE '%consultoria%'
              OR c.objeto_contrato ILIKE '%assessoria%'
              OR c.objeto_contrato ILIKE '%advocacia%'
              OR c.objeto_contrato ILIKE '%jurídico%'
              OR c.objeto_contrato ILIKE '%contábil%'
            THEN 'CONSULTORIA'
            WHEN c.objeto_contrato ILIKE '%combustível%'
              OR c.objeto_contrato ILIKE '%gasolina%'
              OR c.objeto_contrato ILIKE '%diesel%'
              OR c.objeto_contrato ILIKE '%etanol%'
            THEN 'COMBUSTÍVEL'
            ELSE 'OUTROS'
        END                                                                     AS categoria_agrupada
    FROM pncp_supplier_contracts c
    JOIN sc_public_entities e
        ON c.orgao_cnpj LIKE e.cnpj_raiz || '%'
    WHERE (e.raio_200km IS TRUE OR e.distancia_fk <= 200.0)
      AND c.valor_total IS NOT NULL
      AND c.valor_total > 0
)
SELECT
    categoria_agrupada                                                                                 AS categoria,
    COUNT(*)                                                                                           AS qtd_contratos,
    ROUND(SUM(valor)::numeric, 2)                                                                      AS valor_total,
    ROUND(AVG(valor)::numeric, 2)                                                                      AS ticket_medio,
    ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY valor)::numeric, 2)                             AS p25_valor,
    ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY valor)::numeric, 2)                             AS p50_valor,
    ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY valor)::numeric, 2)                             AS p75_valor,
    ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY valor)::numeric, 2)                             AS p25_ticket,
    ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY valor)::numeric, 2)                             AS p50_ticket,
    ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY valor)::numeric, 2)                             AS p75_ticket
FROM categorias
GROUP BY categoria_agrupada
ORDER BY valor_total DESC;

COMMENT ON VIEW v_contract_intel_percentis IS
'P25/P50/P75 value and ticket percentiles by contract category.
Values are in R$ (Brazilian Real). P50 is the median contract value.
These are NOT "preços praticados" — they are nominal values from PNCP.';

COMMIT;


-- ============================================================
-- Migration: 025_coverage_evidence_null_uniqueness.sql
-- ============================================================
-- Migration 025: Coverage Evidence — NULL uniqueness + completeness metadata
-- Fixes the NULL entity_id uniqueness gap in migration 024.
-- NULL != NULL in SQL, so the UNIQUE constraint on (entity_id, source, data_type, run_id)
-- allowed duplicate source-level aggregate rows.
--
-- This migration:
--   1. Drops the old UNIQUE constraint that doesn't work for NULL entity_id.
--   2. Adds two partial unique indexes that correctly enforce:
--      a. One entity-level row per (entity_id, source, data_type, run_id).
--      b. One source-level aggregate row per (source, data_type, run_id).
--   3. Adds a CHECK constraint requiring success_zero rows to carry
--      query-scope proof in metadata (queried_start + queried_end OR
--      a 'completeness' key).
--
-- Idempotent: all DDL uses IF NOT EXISTS / IF EXISTS. Safe to re-run.

BEGIN;

-- ---------------------------------------------------------------------------
-- Step 1: Drop old UNIQUE constraint (does not work for NULL entity_id)
-- ---------------------------------------------------------------------------

-- The constraint was created inline in CREATE TABLE. We must find and drop it.
-- PostgreSQL auto-names it; we locate it dynamically.
DO $$
DECLARE
    _constraint_name TEXT;
BEGIN
    SELECT conname INTO _constraint_name
    FROM pg_constraint
    WHERE conrelid = 'coverage_evidence'::regclass
      AND contype = 'u'
      AND array_length(conkey, 1) = 4
      AND conkey = ARRAY[
          (SELECT attnum FROM pg_attribute WHERE attrelid = 'coverage_evidence'::regclass AND attname = 'entity_id'),
          (SELECT attnum FROM pg_attribute WHERE attrelid = 'coverage_evidence'::regclass AND attname = 'source'),
          (SELECT attnum FROM pg_attribute WHERE attrelid = 'coverage_evidence'::regclass AND attname = 'data_type'),
          (SELECT attnum FROM pg_attribute WHERE attrelid = 'coverage_evidence'::regclass AND attname = 'run_id')
      ];

    IF _constraint_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE coverage_evidence DROP CONSTRAINT %I', _constraint_name);
        RAISE NOTICE 'Dropped unique constraint: %', _constraint_name;
    ELSE
        RAISE NOTICE 'No old unique constraint found — already migrated.';
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- Step 2: Partial unique indexes that correctly handle NULL entity_id
-- ---------------------------------------------------------------------------

-- Entity-level uniqueness: one row per entity+source+data_type+run_id
CREATE UNIQUE INDEX IF NOT EXISTS uq_ce_entity_run
    ON coverage_evidence (entity_id, source, data_type, run_id)
    WHERE entity_id IS NOT NULL;

-- Source-level aggregate uniqueness: exactly one aggregate row per run
CREATE UNIQUE INDEX IF NOT EXISTS uq_ce_source_aggregate_run
    ON coverage_evidence (source, data_type, run_id)
    WHERE entity_id IS NULL;

-- ---------------------------------------------------------------------------
-- Step 3: Completeness metadata CHECK for success_zero rows
-- ---------------------------------------------------------------------------
-- success_zero MUST carry proof that the query scope was fully covered.
-- Accept: (queried_start, queried_end) both non-NULL, OR
--          metadata->>'completeness' exists with a recognised value.

DO $$ BEGIN
    ALTER TABLE coverage_evidence ADD CONSTRAINT ck_success_zero_completeness
        CHECK (
            state != 'success_zero'
            OR (queried_start IS NOT NULL AND queried_end IS NOT NULL)
            OR (metadata ? 'completeness')
        );
EXCEPTION
    WHEN duplicate_object THEN
        RAISE NOTICE 'Constraint ck_success_zero_completeness already exists.';
END $$;

-- ---------------------------------------------------------------------------
-- Step 4: Recreate v_latest_evidence view (to pick up any column changes)
-- ---------------------------------------------------------------------------

DROP VIEW IF EXISTS v_source_health;
DROP VIEW IF EXISTS v_latest_evidence;

CREATE OR REPLACE VIEW v_latest_evidence AS
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
FROM coverage_evidence
ORDER BY entity_id, source, data_type, completed_at DESC;

-- v_source_health: per-source aggregates from latest evidence rows.
-- Filters to entity-level rows only (entity_id IS NOT NULL) for entity coverage;
-- source-level aggregates (entity_id IS NULL) contribute run-level health.
CREATE OR REPLACE VIEW v_source_health AS
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
FROM v_latest_evidence
GROUP BY source
ORDER BY source;

COMMIT;


-- ============================================================
-- Migration: 026_contract_intel_truth_v1.sql
-- ============================================================
-- Migration 026: Contract Intelligence Truth v1 — Analytical Views (corrected)
--
-- Fixes column-name drift between migrations 001-025 and the real PostgreSQL schema.
-- The real pncp_supplier_contracts uses:
--   numero_controle_pncp (NOT contrato_id)
--   ni_fornecedor          (NOT fornecedor_cnpj)
--   nome_fornecedor        (NOT fornecedor_nome)
--   valor_global           (NOT valor_total)
--   data_assinatura        (NOT data_inicio — data_inicio does NOT exist)
--   data_fim_vigencia      (NOT data_fim)
--   (NO data_publicacao column exists)
--
-- sc_public_entities uses:
--   cnpj_8                 (NOT cnpj_raiz)
--   distancia_fk           (NOT distancia_km)
--   raio_200km (boolean)   (NOT a text field)
--
-- SEMANTIC NOTE: valor_global is the PNCP "valorGlobal" field.
--   It is NOT "preço praticado" nor "valor homologado" nor "deságio".
--   When PNCP does not distinguish value semantics, we mark it as
--   "valor_global — semântica não desambiguada pela origem" and
--   block metrics that depend on precise value semantics.
--
-- DESIGN: All views use the REAL column names from the production PostgreSQL.
--   Views are idempotent (CREATE OR REPLACE).
--   Views are read-only analytical layer over pncp_supplier_contracts.

BEGIN;

-- ==========================================================================
-- View 1: v_contract_historical
-- Historical contracts (3-year window) for target universe entities.
-- ==========================================================================

CREATE OR REPLACE VIEW v_contract_historical AS
SELECT
    c.numero_controle_pncp                                   AS contrato_id,
    c.orgao_cnpj,
    c.orgao_nome,
    c.ni_fornecedor                                          AS fornecedor_cnpj,
    c.nome_fornecedor                                        AS fornecedor_nome,
    c.objeto_contrato,
    c.valor_global                                           AS valor_contrato,
    c.data_assinatura                                        AS data_inicio_contrato,
    c.data_fim_vigencia                                      AS data_fim_contrato,
    c.uf,
    c.municipio,
    c.esfera,
    c.nr_contrato,
    c.ano,
    e.razao_social                                           AS ente_razao_social,
    e.municipio                                              AS ente_municipio,
    e.codigo_ibge                                            AS ente_codigo_ibge,
    e.distancia_fk                                           AS ente_distancia_km,
    e.raio_200km,
    c.ingested_at
FROM pncp_supplier_contracts c
JOIN sc_public_entities e
    ON c.orgao_cnpj8 = e.cnpj_8
WHERE e.raio_200km IS TRUE
  AND c.is_active IS TRUE
  -- 3-year window: contracts signed in last 3 years
  AND c.data_assinatura >= (CURRENT_DATE - INTERVAL '3 years');

COMMENT ON VIEW v_contract_historical IS
'Historical contracts (3-year window) for public entities within 200 km of Florianópolis.
Value column is valor_global from PNCP — NOT preço praticado, NOT valor homologado.
When PNCP does not distinguish, the semantic is marked as unknown at the API level.';

-- ==========================================================================
-- View 2: v_supplier_winners
-- Supplier/competitor rankings by count, value, avg ticket, concentration.
-- Uses "vencedores históricos" (historical winners), NOT "todos os licitantes".
-- ==========================================================================

CREATE OR REPLACE VIEW v_supplier_winners AS
WITH fornecedor_orgao_agg AS (
    SELECT
        c.ni_fornecedor,
        c.nome_fornecedor,
        c.orgao_cnpj,
        c.orgao_nome,
        SUM(COALESCE(c.valor_global, 0))                       AS valor_orgao,
        COUNT(*)                                                AS qtd_contratos_orgao
    FROM pncp_supplier_contracts c
    JOIN sc_public_entities e
        ON c.orgao_cnpj8 = e.cnpj_8
    WHERE e.raio_200km IS TRUE
      AND c.is_active IS TRUE
      AND c.ni_fornecedor IS NOT NULL
      AND c.ni_fornecedor != ''
    GROUP BY c.ni_fornecedor, c.nome_fornecedor, c.orgao_cnpj, c.orgao_nome
),
fornecedor_totals AS (
    SELECT
        fo.ni_fornecedor,
        fo.nome_fornecedor,
        SUM(fo.qtd_contratos_orgao)                             AS qtd_contratos,
        SUM(fo.valor_orgao)                                     AS valor_total,
        ROUND(AVG(fo.valor_orgao)::numeric, 2)                  AS ticket_medio_contrato,
        COUNT(DISTINCT fo.orgao_cnpj)                           AS qtd_orgaos_distintos,
        STRING_AGG(DISTINCT fo.orgao_nome, '; ' ORDER BY fo.orgao_nome) AS orgaos_lista
    FROM fornecedor_orgao_agg fo
    GROUP BY fo.ni_fornecedor, fo.nome_fornecedor
),
hhi_calc AS (
    SELECT
        ft.*,
        -- HHI computed from per-agency value shares
        ROUND(
            (SELECT SUM(POWER(fo2.valor_orgao * 1.0 / NULLIF(ft.valor_total, 0), 2) * 10000)
             FROM fornecedor_orgao_agg fo2
             WHERE fo2.ni_fornecedor = ft.ni_fornecedor),
            0
        )                                                        AS hhi_concentracao
    FROM fornecedor_totals ft
)
SELECT
    ni_fornecedor                                               AS fornecedor_cnpj,
    nome_fornecedor                                             AS fornecedor_nome,
    qtd_contratos,
    ROUND(valor_total::numeric, 2)                              AS valor_total_contratos,
    ticket_medio_contrato,
    qtd_orgaos_distintos,
    hhi_concentracao,
    orgaos_lista
FROM hhi_calc
ORDER BY valor_total_contratos DESC;

COMMENT ON VIEW v_supplier_winners IS
'Supplier winner rankings: contract count, total value, average ticket per contract,
distinct agencies served, HHI concentration index (0-10000).
Uses historical winners only — NOT all bidders.
Value column is valor_global from PNCP — NOT preço praticado.';

-- ==========================================================================
-- View 3: v_expiring_contracts
-- Active contracts ending in 90-180 days (renewal/rebidding window).
-- ==========================================================================

CREATE OR REPLACE VIEW v_expiring_contracts AS
SELECT
    c.numero_controle_pncp                                   AS contrato_id,
    c.orgao_cnpj,
    c.orgao_nome,
    c.ni_fornecedor                                          AS fornecedor_cnpj,
    c.nome_fornecedor                                        AS fornecedor_nome,
    c.objeto_contrato,
    c.valor_global                                           AS valor_contrato,
    c.data_assinatura                                        AS data_inicio_contrato,
    c.data_fim_vigencia                                      AS data_fim_contrato,
    (c.data_fim_vigencia - CURRENT_DATE)                     AS dias_ate_fim,
    c.uf,
    c.municipio,
    e.razao_social                                           AS ente_razao_social,
    e.municipio                                              AS ente_municipio
FROM pncp_supplier_contracts c
JOIN sc_public_entities e
    ON c.orgao_cnpj8 = e.cnpj_8
WHERE e.raio_200km IS TRUE
  AND c.is_active IS TRUE
  AND c.data_fim_vigencia IS NOT NULL
  AND c.data_fim_vigencia BETWEEN (CURRENT_DATE + INTERVAL '90 days')
                               AND (CURRENT_DATE + INTERVAL '180 days')
ORDER BY c.data_fim_vigencia, c.valor_global DESC NULLS LAST;

COMMENT ON VIEW v_expiring_contracts IS
'Active contracts ending between 90 and 180 days from today (renewal/rebidding window).
REQUIRES non-NULL data_fim_vigencia — contracts without end date are EXCLUDED.
Value column is valor_global from PNCP — NOT preço praticado.';

-- ==========================================================================
-- View 4: v_contract_intel_percentis (corrected)
-- P25/P50/P75 value/ticket percentiles by contract category.
-- ==========================================================================

CREATE OR REPLACE VIEW v_contract_intel_percentis AS
WITH categorias AS (
    SELECT
        c.valor_global                                           AS valor,
        CASE
            WHEN c.objeto_contrato ILIKE '%obra%'
              OR c.objeto_contrato ILIKE '%construção%'
              OR c.objeto_contrato ILIKE '%pavimentação%'
              OR c.objeto_contrato ILIKE '%edificação%'
              OR c.objeto_contrato ILIKE '%engenharia%'
            THEN 'OBRAS'
            WHEN c.objeto_contrato ILIKE '%limpeza%'
              OR c.objeto_contrato ILIKE '%conservação%'
              OR c.objeto_contrato ILIKE '%manutenção%'
              OR c.objeto_contrato ILIKE '%zeladoria%'
            THEN 'FACILITIES'
            WHEN c.objeto_contrato ILIKE '%software%'
              OR c.objeto_contrato ILIKE '%ti%'
              OR c.objeto_contrato ILIKE '%tecnologia%'
              OR c.objeto_contrato ILIKE '%sistema%'
              OR c.objeto_contrato ILIKE '%informática%'
            THEN 'TI'
            WHEN c.objeto_contrato ILIKE '%saúde%'
              OR c.objeto_contrato ILIKE '%medicamento%'
              OR c.objeto_contrato ILIKE '%hospitalar%'
              OR c.objeto_contrato ILIKE '%medico%'
              OR c.objeto_contrato ILIKE '%farmacêutico%'
              OR c.objeto_contrato ILIKE '%laboratório%'
            THEN 'SAÚDE'
            WHEN c.objeto_contrato ILIKE '%alimentação%'
              OR c.objeto_contrato ILIKE '%alimento%'
              OR c.objeto_contrato ILIKE '%merenda%'
              OR c.objeto_contrato ILIKE '%gênero alimentício%'
            THEN 'ALIMENTAÇÃO'
            WHEN c.objeto_contrato ILIKE '%transporte%'
              OR c.objeto_contrato ILIKE '%veículo%'
              OR c.objeto_contrato ILIKE '%frota%'
              OR c.objeto_contrato ILIKE '%ônibus%'
              OR c.objeto_contrato ILIKE '%locação de veículo%'
            THEN 'TRANSPORTE'
            WHEN c.objeto_contrato ILIKE '%segurança%'
              OR c.objeto_contrato ILIKE '%vigilância%'
              OR c.objeto_contrato ILIKE '%monitoramento%'
              OR c.objeto_contrato ILIKE '%porteiro%'
            THEN 'SEGURANÇA'
            WHEN c.objeto_contrato ILIKE '%consultoria%'
              OR c.objeto_contrato ILIKE '%assessoria%'
              OR c.objeto_contrato ILIKE '%advocacia%'
              OR c.objeto_contrato ILIKE '%jurídico%'
              OR c.objeto_contrato ILIKE '%contábil%'
            THEN 'CONSULTORIA'
            WHEN c.objeto_contrato ILIKE '%combustível%'
              OR c.objeto_contrato ILIKE '%gasolina%'
              OR c.objeto_contrato ILIKE '%diesel%'
              OR c.objeto_contrato ILIKE '%etanol%'
            THEN 'COMBUSTÍVEL'
            ELSE 'OUTROS'
        END                                                      AS categoria_agrupada
    FROM pncp_supplier_contracts c
    JOIN sc_public_entities e
        ON c.orgao_cnpj8 = e.cnpj_8
    WHERE e.raio_200km IS TRUE
      AND c.is_active IS TRUE
      AND c.valor_global IS NOT NULL
      AND c.valor_global > 0
)
SELECT
    categoria_agrupada                                        AS categoria,
    COUNT(*)                                                  AS qtd_contratos,
    ROUND(SUM(valor)::numeric, 2)                             AS valor_total,
    ROUND(AVG(valor)::numeric, 2)                             AS ticket_medio,
    ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY valor)::numeric, 2) AS p25_valor,
    ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY valor)::numeric, 2) AS p50_valor,
    ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY valor)::numeric, 2) AS p75_valor
FROM categorias
GROUP BY categoria_agrupada
ORDER BY valor_total DESC;

COMMENT ON VIEW v_contract_intel_percentis IS
'P25/P50/P75 value percentiles by contract category (keyword-based).
Values in R$ (Brazilian Real). P50 is the median contract value.
These are nominal values from PNCP valor_global — NOT preços praticados.';

COMMIT;


-- ============================================================
-- Migration: 027_opportunity_intel.sql
-- ============================================================
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


-- ============================================================
-- Migration: 028_opportunity_indexes.sql
-- ============================================================
-- Migration 028: Opportunity Intelligence — Indexes & Dedup Constraints
--
-- Performance indexes + deduplication unique constraints.
-- Separate from 027 to keep core table creation clean.

BEGIN;

-- ==========================================================================
-- B-tree indexes — lookups
-- ==========================================================================

CREATE INDEX IF NOT EXISTS idx_oi_source ON opportunity_intel(source);
CREATE INDEX IF NOT EXISTS idx_oi_source_id ON opportunity_intel(source, source_id);
CREATE INDEX IF NOT EXISTS idx_oi_orgao_cnpj ON opportunity_intel(orgao_cnpj);
CREATE INDEX IF NOT EXISTS idx_oi_uf ON opportunity_intel(uf);
CREATE INDEX IF NOT EXISTS idx_oi_municipio ON opportunity_intel(municipio);
CREATE INDEX IF NOT EXISTS idx_oi_codigo_ibge ON opportunity_intel(codigo_ibge);
CREATE INDEX IF NOT EXISTS idx_oi_status_canonico ON opportunity_intel(status_canonico);
CREATE INDEX IF NOT EXISTS idx_oi_data_abertura ON opportunity_intel(data_abertura);
CREATE INDEX IF NOT EXISTS idx_oi_data_encerramento ON opportunity_intel(data_encerramento);
CREATE INDEX IF NOT EXISTS idx_oi_modalidade ON opportunity_intel(modalidade);
CREATE INDEX IF NOT EXISTS idx_oi_ranking ON opportunity_intel(ranking);
CREATE INDEX IF NOT EXISTS idx_oi_numero_processo ON opportunity_intel(numero_processo);
CREATE INDEX IF NOT EXISTS idx_oi_numero_edital ON opportunity_intel(numero_edital);
CREATE INDEX IF NOT EXISTS idx_oi_numero_controle_pncp ON opportunity_intel(numero_controle_pncp);
CREATE INDEX IF NOT EXISTS idx_oi_crawl_batch_id ON opportunity_intel(crawl_batch_id);
CREATE INDEX IF NOT EXISTS idx_oi_ingested_at ON opportunity_intel(ingested_at);
CREATE INDEX IF NOT EXISTS idx_oi_is_active ON opportunity_intel(is_active);

-- Composite indexes
CREATE INDEX IF NOT EXISTS idx_oi_uf_status ON opportunity_intel(uf, status_canonico);
CREATE INDEX IF NOT EXISTS idx_oi_source_status ON opportunity_intel(source, status_canonico);
CREATE INDEX IF NOT EXISTS idx_oi_ranking_score ON opportunity_intel(ranking, ranking_score DESC);

-- ==========================================================================
-- GIN indexes — full-text search
-- ==========================================================================

CREATE INDEX IF NOT EXISTS idx_oi_objeto_gin
    ON opportunity_intel USING gin(to_tsvector('portuguese', COALESCE(objeto, '')));

-- ==========================================================================
-- Partial unique indexes — dedup constraints
-- ==========================================================================

-- Level 1: Official PNCP ID (most reliable)
CREATE UNIQUE INDEX IF NOT EXISTS uq_oi_pncp_id
    ON opportunity_intel(numero_controle_pncp)
    WHERE numero_controle_pncp IS NOT NULL
      AND is_active = TRUE;

-- Level 2: orgão + processo + edital (same bid, different source)
-- Uses partial index — only applies when both fields present
CREATE UNIQUE INDEX IF NOT EXISTS uq_oi_orgao_processo_edital
    ON opportunity_intel(orgao_cnpj, numero_processo, numero_edital)
    WHERE orgao_cnpj IS NOT NULL
      AND numero_processo IS NOT NULL
      AND numero_edital IS NOT NULL
      AND is_active = TRUE;

-- ==========================================================================
-- Index on opportunity_runs
-- ==========================================================================

CREATE INDEX IF NOT EXISTS idx_or_source ON opportunity_runs(source);
CREATE INDEX IF NOT EXISTS idx_or_status ON opportunity_runs(status);
CREATE INDEX IF NOT EXISTS idx_or_started_at ON opportunity_runs(started_at DESC);

-- ==========================================================================
-- Index on opportunity_coverage
-- ==========================================================================

CREATE INDEX IF NOT EXISTS idx_oc_source ON opportunity_coverage(source);
CREATE INDEX IF NOT EXISTS idx_oc_result ON opportunity_coverage(result);
CREATE INDEX IF NOT EXISTS idx_oc_last_attempt ON opportunity_coverage(last_attempt DESC);

-- ==========================================================================
-- FK: opportunity_intel.run_id → opportunity_runs.id
-- ==========================================================================

ALTER TABLE opportunity_intel
    DROP CONSTRAINT IF EXISTS fk_oi_run_id;

ALTER TABLE opportunity_intel
    ADD CONSTRAINT fk_oi_run_id
    FOREIGN KEY (run_id) REFERENCES opportunity_runs(id)
    ON DELETE SET NULL;

COMMIT;


-- ============================================================
-- Migration: 029_qw01_auditable_radar.sql
-- ============================================================
-- QW-01: auditable opportunity radar evidence and run metadata.
-- Extends existing ledgers; does not alter or delete raw data.
-- Idempotent on PostgreSQL 16+.

BEGIN;

ALTER TYPE evidence_state ADD VALUE IF NOT EXISTS 'success';
ALTER TYPE evidence_state ADD VALUE IF NOT EXISTS 'error';
ALTER TYPE evidence_state ADD VALUE IF NOT EXISTS 'pending';
ALTER TYPE evidence_state ADD VALUE IF NOT EXISTS 'stale';
ALTER TYPE evidence_state ADD VALUE IF NOT EXISTS 'blocked';

ALTER TABLE coverage_evidence
    ADD COLUMN IF NOT EXISTS canonical_entity_key TEXT,
    ADD COLUMN IF NOT EXISTS applicability TEXT NOT NULL DEFAULT 'applicable',
    ADD COLUMN IF NOT EXISTS scope_key TEXT,
    ADD COLUMN IF NOT EXISTS checked_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS pages_expected INTEGER,
    ADD COLUMN IF NOT EXISTS pages_processed INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS records_fetched INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS open_records INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS freshness_status TEXT NOT NULL DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS evidence_metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

DO $$ BEGIN
    ALTER TABLE coverage_evidence ADD CONSTRAINT ck_ce_applicability
        CHECK (applicability IN ('applicable', 'not_applicable', 'unknown'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE coverage_evidence ADD CONSTRAINT ck_ce_freshness_status
        CHECK (freshness_status IN ('fresh', 'stale', 'never', 'unknown'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

ALTER TABLE coverage_evidence DROP CONSTRAINT IF EXISTS ck_success_zero_completeness;
ALTER TABLE coverage_evidence DROP CONSTRAINT IF EXISTS ck_ce_success_zero_scope;

ALTER TABLE coverage_evidence ADD CONSTRAINT ck_ce_success_zero_scope
    CHECK (
        state != 'success_zero'
        OR (
            queried_start IS NOT NULL
            AND queried_end IS NOT NULL
            AND scope_key IS NOT NULL
            AND pages_processed > 0
            AND (
                (pages_expected IS NOT NULL AND pages_processed >= pages_expected)
                OR (
                    pages_expected IS NULL
                    AND evidence_metadata->>'completion_rule' IN (
                        'short_page_without_total',
                        'empty_page_after_valid_scope',
                        'http_204_complete'
                    )
                )
            )
        )
    ) NOT VALID;

-- Migration 024 introduced ``partial`` as a valid enum state, but some local
-- databases carry a later trigger revision that rejects it. QW-01 requires an
-- explicit partial state whenever pagination cannot be proven complete.
CREATE OR REPLACE FUNCTION fn_validate_coverage_evidence()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.state = 'success_with_data' AND NEW.count_persisted <= 0 THEN
        RAISE EXCEPTION 'success_with_data requires count_persisted > 0 (got %)', NEW.count_persisted;
    END IF;
    IF NEW.state = 'success_zero' AND NEW.count_persisted > 0 THEN
        RAISE EXCEPTION 'success_zero requires count_persisted = 0 (got %)', NEW.count_persisted;
    END IF;
    RETURN NEW;
END;
$$;

DROP INDEX IF EXISTS uq_ce_entity_run;

CREATE UNIQUE INDEX IF NOT EXISTS uq_ce_legacy_entity_run
    ON coverage_evidence (entity_id, source, data_type, run_id)
    WHERE canonical_entity_key IS NULL AND entity_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_ce_canonical_entity_run
    ON coverage_evidence (canonical_entity_key, source, data_type, run_id)
    WHERE canonical_entity_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_ce_canonical_entity_source
    ON coverage_evidence (canonical_entity_key, source, checked_at DESC);

ALTER TABLE opportunity_runs
    ADD COLUMN IF NOT EXISTS external_run_id TEXT,
    ADD COLUMN IF NOT EXISTS source_strategy TEXT,
    ADD COLUMN IF NOT EXISTS period_start DATE,
    ADD COLUMN IF NOT EXISTS period_end DATE,
    ADD COLUMN IF NOT EXISTS records_expected INTEGER,
    ADD COLUMN IF NOT EXISTS scope_complete BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS completion_reason TEXT,
    ADD COLUMN IF NOT EXISTS error_code TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_or_external_run_id
    ON opportunity_runs (external_run_id)
    WHERE external_run_id IS NOT NULL;

ALTER TABLE opportunity_checkpoints
    ADD COLUMN IF NOT EXISTS external_run_id TEXT,
    ADD COLUMN IF NOT EXISTS pages_expected INTEGER,
    ADD COLUMN IF NOT EXISTS scope_complete BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS completion_reason TEXT;

CREATE OR REPLACE FUNCTION upsert_qw01_pncp_opportunities(batch JSONB)
RETURNS TABLE(action TEXT, record_id BIGINT, result_content_hash TEXT)
LANGUAGE plpgsql
AS $$
DECLARE
    rec JSONB;
BEGIN
    FOR rec IN SELECT * FROM jsonb_array_elements(batch)
    LOOP
        IF COALESCE(rec->>'numero_controle_pncp', '') = '' THEN
            RAISE EXCEPTION 'QW-01 PNCP record missing numero_controle_pncp';
        END IF;

        INSERT INTO opportunity_intel (
            source, source_id, source_url, content_hash, numero_controle_pncp,
            crawl_batch_id, run_id, orgao_cnpj, orgao_nome, ente_federativo,
            uf, municipio, codigo_ibge, numero_processo, numero_edital,
            modalidade, modalidade_id, objeto, categoria, valor_estimado,
            valor_semantica, data_publicacao, data_abertura, data_encerramento,
            status_fonte, status_canonico, status_motivo, status_data,
            link_edital, link_anexos, proveniencia, metadata
        ) VALUES (
            'pncp', rec->>'source_id', rec->>'source_url', rec->>'content_hash',
            rec->>'numero_controle_pncp', rec->>'crawl_batch_id', (rec->>'run_id')::BIGINT,
            rec->>'orgao_cnpj', rec->>'orgao_nome', rec->>'ente_federativo',
            COALESCE(rec->>'uf', 'SC'), rec->>'municipio', rec->>'codigo_ibge',
            rec->>'numero_processo', rec->>'numero_edital', rec->>'modalidade',
            (rec->>'modalidade_id')::INTEGER, rec->>'objeto', rec->>'categoria',
            (rec->>'valor_estimado')::NUMERIC, rec->>'valor_semantica',
            (rec->>'data_publicacao')::TIMESTAMPTZ, (rec->>'data_abertura')::TIMESTAMPTZ,
            (rec->>'data_encerramento')::TIMESTAMPTZ, rec->>'status_fonte',
            COALESCE(rec->>'status_canonico', 'unknown'), rec->>'status_motivo',
            (rec->>'status_data')::TIMESTAMPTZ, rec->>'link_edital',
            CASE WHEN jsonb_typeof(rec->'link_anexos') = 'array'
                THEN ARRAY(SELECT * FROM jsonb_array_elements_text(rec->'link_anexos')) END,
            COALESCE(rec->'proveniencia', '{}'::jsonb), COALESCE(rec->'metadata', '{}'::jsonb)
        )
        ON CONFLICT (numero_controle_pncp)
            WHERE numero_controle_pncp IS NOT NULL AND is_active = TRUE
        DO UPDATE SET
            source_url = COALESCE(EXCLUDED.source_url, opportunity_intel.source_url),
            content_hash = EXCLUDED.content_hash,
            crawl_batch_id = EXCLUDED.crawl_batch_id,
            run_id = EXCLUDED.run_id,
            last_seen_at = NOW(),
            orgao_cnpj = COALESCE(EXCLUDED.orgao_cnpj, opportunity_intel.orgao_cnpj),
            orgao_nome = COALESCE(EXCLUDED.orgao_nome, opportunity_intel.orgao_nome),
            municipio = COALESCE(EXCLUDED.municipio, opportunity_intel.municipio),
            codigo_ibge = COALESCE(EXCLUDED.codigo_ibge, opportunity_intel.codigo_ibge),
            numero_processo = COALESCE(EXCLUDED.numero_processo, opportunity_intel.numero_processo),
            numero_edital = COALESCE(EXCLUDED.numero_edital, opportunity_intel.numero_edital),
            modalidade = COALESCE(EXCLUDED.modalidade, opportunity_intel.modalidade),
            modalidade_id = COALESCE(EXCLUDED.modalidade_id, opportunity_intel.modalidade_id),
            objeto = EXCLUDED.objeto,
            categoria = COALESCE(EXCLUDED.categoria, opportunity_intel.categoria),
            valor_estimado = COALESCE(EXCLUDED.valor_estimado, opportunity_intel.valor_estimado),
            valor_semantica = COALESCE(EXCLUDED.valor_semantica, opportunity_intel.valor_semantica),
            data_publicacao = COALESCE(EXCLUDED.data_publicacao, opportunity_intel.data_publicacao),
            data_abertura = COALESCE(EXCLUDED.data_abertura, opportunity_intel.data_abertura),
            data_encerramento = COALESCE(EXCLUDED.data_encerramento, opportunity_intel.data_encerramento),
            status_fonte = EXCLUDED.status_fonte,
            status_canonico = EXCLUDED.status_canonico,
            status_motivo = EXCLUDED.status_motivo,
            status_data = EXCLUDED.status_data,
            link_edital = COALESCE(EXCLUDED.link_edital, opportunity_intel.link_edital),
            link_anexos = COALESCE(EXCLUDED.link_anexos, opportunity_intel.link_anexos),
            proveniencia = EXCLUDED.proveniencia,
            metadata = EXCLUDED.metadata,
            is_active = TRUE
        RETURNING
            CASE WHEN xmax = 0 THEN 'insert' ELSE 'update' END,
            id,
            content_hash
        INTO action, record_id, result_content_hash;
        RETURN NEXT;
    END LOOP;
END;
$$;

COMMIT;

COMMENT ON COLUMN coverage_evidence.canonical_entity_key IS
    'Stable seed identity hash; preserves legitimate duplicate CNPJ roots.';
COMMENT ON COLUMN opportunity_runs.scope_complete IS
    'True only when every declared source scope has auditable pagination completion.';


-- ============================================================
-- Migration: 030_schema_contract_and_canonical_views.sql
-- ============================================================
-- ============================================================================
-- Migration 030: Schema Contract + Canonical Views
-- ============================================================================
-- Story 1.2 (Unify Schema) — Task 5: Canonical Views
--
-- Define as 5 views canonicas estaveis que servem como CONTRATO entre o
-- schema fisico e os consumers (Python queries, reports, intel pipelines).
--
-- Principios (Secao 6.2 do Plano Mestre):
--   1. CREATE OR REPLACE VIEW — idempotente, seguro para reaplicacao
--   2. Nomes de colunas estaveis — NAO mudam sem major version bump
--   3. Prefixo v_*_canonical para views canonicas
--   4. Todas registradas em _migrations tracking
--
-- Contrato completo: docs/stories/story-1.2-canonical-views-contract.md
--
-- Depende de: 001-029 (sc_public_entities, pncp_raw_bids, pncp_supplier_contracts,
--             enriched_entities, entity_coverage existem)
-- Idempotente: Sim (OR REPLACE + IF NOT EXISTS)
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. v_entities_canonical — Entidades publicas de SC
-- ============================================================================
-- Proposito: Visao unificada de entidades + cobertura
-- Consumers: consulting_readiness.py, coverage_truth.py, intel_pipeline.py
-- ============================================================================
CREATE OR REPLACE VIEW public.v_entities_canonical AS
SELECT
    e.id                 AS entity_id,
    e.cnpj_8             AS cnpj_8_base,
    e.razao_social       AS razao_social,
    e.municipio          AS municipio,
    e.codigo_ibge        AS codigo_ibge,
    e.natureza_juridica  AS natureza_juridica,
    e.cod_natureza       AS cod_natureza,
    e.latitude,
    e.longitude,
    e.distancia_fk       AS distancia_fk,
    e.raio_200km         AS within_200km,
    e.is_active          AS is_active,
    ec.total_bids        AS total_bids,
    ec.is_covered        AS is_covered,
    ec.last_seen_at      AS last_coverage_at
FROM public.sc_public_entities e
LEFT JOIN public.entity_coverage ec ON ec.entity_id = e.id AND ec.source = 'pncp';

COMMENT ON VIEW public.v_entities_canonical IS
    'Canonical entity view v1.0 — entidades SC com metadados de cobertura. Story 1.2';

COMMENT ON COLUMN public.v_entities_canonical.entity_id IS 'PK da entidade (sc_public_entities.id)';
COMMENT ON COLUMN public.v_entities_canonical.cnpj_8_base IS 'CNPJ base 8 digitos';
COMMENT ON COLUMN public.v_entities_canonical.within_200km IS 'Dentro do raio 200km de Florianopolis';
COMMENT ON COLUMN public.v_entities_canonical.last_coverage_at IS 'Ultima vez que a entidade foi coberta por crawl';
COMMENT ON COLUMN public.v_entities_canonical.is_covered IS 'Se a entidade tem coverage ativa';

-- ============================================================================
-- 2. v_open_opportunities_canonical — Licitacoes abertas
-- ============================================================================
-- Proposito: Oportunidades abertas com dados normalizados
-- Consumers: opportunity_intel pipeline, ranking, radar
-- ============================================================================
CREATE OR REPLACE VIEW public.v_open_opportunities_canonical AS
SELECT
    b.pncp_id                AS bid_id,
    b.pncp_id                AS pncp_id,
    b.objeto_compra          AS objeto,
    b.valor_total_estimado   AS valor_estimado,
    b.modalidade_id,
    b.modalidade_nome        AS modalidade,
    b.esfera_id              AS esfera_id,
    b.uf,
    b.municipio,
    b.codigo_municipio_ibge  AS codigo_ibge,
    b.orgao_cnpj,
    b.orgao_razao_social     AS orgao_nome,
    b.data_publicacao,
    b.data_abertura,
    b.data_encerramento,
    b.link_pncp              AS link_edital,
    b.source,
    b.source_id,
    b.match_method,
    b.match_score,
    b.match_confidence,
    e.id                     AS matched_entity_id,
    e.razao_social           AS matched_entity_nome,
    e.raio_200km             AS within_200km,
    e.cnpj_8                 AS entity_cnpj_8
FROM public.pncp_raw_bids b
LEFT JOIN public.sc_public_entities e ON e.id = b.matched_entity_id
WHERE b.data_encerramento >= CURRENT_DATE
   OR (b.data_encerramento IS NULL AND b.data_publicacao >= CURRENT_DATE - INTERVAL '30 days');

COMMENT ON VIEW public.v_open_opportunities_canonical IS
    'Canonical open opportunities view v1.0 — licitacoes abertas. Story 1.2';

COMMENT ON COLUMN public.v_open_opportunities_canonical.within_200km IS
    'Se a entidade matched esta dentro do raio 200km';

-- ============================================================================
-- 3. v_contracts_canonical — Contratos de fornecedores
-- ============================================================================
-- Proposito: Contratos com dados de entidades e enriched_entities
-- Consumers: consulting_readiness.py (market share, HHI), contract_intel CLI
-- ============================================================================
CREATE OR REPLACE VIEW public.v_contracts_canonical AS
SELECT
    c.contrato_id,
    c.orgao_cnpj,
    c.orgao_nome,
    c.fornecedor_cnpj,
    c.fornecedor_nome,
    c.objeto_contrato        AS objeto,
    c.valor_total            AS valor,
    c.data_inicio,
    c.data_fim,
    c.data_publicacao,
    c.uf,
    c.municipio,
    c.codigo_municipio_ibge,
    c.municipio_inferido,
    c.source,
    c.source_id,
    e.id                     AS entity_id,
    e.razao_social           AS entity_nome,
    e.cnpj_8                 AS entity_cnpj_8,
    e.raio_200km             AS within_200km,
    enr.cnae_principal,
    enr.natureza_juridica
FROM public.pncp_supplier_contracts c
LEFT JOIN public.sc_public_entities e ON e.cnpj_8 = LEFT(c.fornecedor_cnpj, 8)
LEFT JOIN public.enriched_entities enr ON enr.cnpj = c.fornecedor_cnpj
WHERE c.data_inicio IS NOT NULL OR c.data_publicacao IS NOT NULL;

COMMENT ON VIEW public.v_contracts_canonical IS
    'Canonical contracts view v1.0 — contratos ativos com dados de fornecedores. Story 1.2';

-- ============================================================================
-- 4. v_suppliers_canonical — Cadastro de fornecedores
-- ============================================================================
-- Proposito: Fornecedores com metadados agregados de contratos
-- Consumers: intel pipeline, report generation
-- ============================================================================
CREATE OR REPLACE VIEW public.v_suppliers_canonical AS
SELECT
    e.cnpj                          AS cnpj_completo,
    e.razao_social,
    e.nome_fantasia,
    e.cnae_principal,
    e.cnae_secundarios,
    e.municipio,
    e.uf,
    e.codigo_ibge,
    e.natureza_juridica,
    e.situacao,
    e.enriched_at                   AS ultima_atualizacao,
    e.enriched_source,
    sc.cnpj_8                       AS entidade_cnpj_8,
    sc.razao_social                 AS entidade_nome,
    sc.raio_200km                   AS within_200km,
    COUNT(DISTINCT c.contrato_id)   AS total_contratos,
    SUM(c.valor_total)              AS valor_total_contratos
FROM public.enriched_entities e
LEFT JOIN public.sc_public_entities sc ON sc.cnpj_8 = LEFT(e.cnpj, 8)
LEFT JOIN public.pncp_supplier_contracts c ON c.fornecedor_cnpj = e.cnpj
GROUP BY e.cnpj, e.razao_social, e.nome_fantasia, e.cnae_principal,
         e.cnae_secundarios, e.municipio, e.uf, e.codigo_ibge,
         e.natureza_juridica, e.situacao, e.enriched_at, e.enriched_source,
         sc.cnpj_8, sc.razao_social, sc.raio_200km;

COMMENT ON VIEW public.v_suppliers_canonical IS
    'Canonical suppliers view v1.0 — fornecedores com agregacao de contratos. Story 1.2';

-- ============================================================================
-- 5. v_value_observations_canonical — Observacoes de valor
-- ============================================================================
-- Proposito: Valores de bids e contratos para analise estatistica
-- Consumers: lib/bid_simulator.py, lib/value_semantics.py
-- ============================================================================
CREATE OR REPLACE VIEW public.v_value_observations_canonical AS
SELECT
    'bid'::TEXT                      AS observation_type,
    b.pncp_id                        AS source_id,
    b.orgao_cnpj,
    b.municipio,
    b.uf,
    b.modalidade_id,
    b.modalidade_nome                AS modalidade,
    b.objeto_compra                  AS objeto,
    b.valor_total_estimado           AS valor,
    b.data_publicacao,
    e.cnpj_8                         AS entity_cnpj_8,
    e.raio_200km                     AS within_200km
FROM public.pncp_raw_bids b
LEFT JOIN public.sc_public_entities e ON e.id = b.matched_entity_id
WHERE b.valor_total_estimado IS NOT NULL AND b.valor_total_estimado > 0

UNION ALL

SELECT
    'contract'::TEXT                 AS observation_type,
    c.contrato_id                    AS source_id,
    c.orgao_cnpj,
    c.municipio,
    c.uf,
    NULL::INTEGER                    AS modalidade_id,
    NULL::TEXT                       AS modalidade,
    c.objeto_contrato                AS objeto,
    c.valor_total                    AS valor,
    c.data_publicacao,
    e.cnpj_8                         AS entity_cnpj_8,
    e.raio_200km                     AS within_200km
FROM public.pncp_supplier_contracts c
LEFT JOIN public.sc_public_entities e ON e.cnpj_8 = LEFT(c.fornecedor_cnpj, 8)
WHERE c.valor_total IS NOT NULL AND c.valor_total > 0;

COMMENT ON VIEW public.v_value_observations_canonical IS
    'Canonical value observations view v1.0 — bids e contracts para analise. Story 1.2';
COMMENT ON COLUMN public.v_value_observations_canonical.observation_type IS
    'Tipo: ''bid'' para licitacao, ''contract'' para contrato';

-- ============================================================================
-- Rollback SQL (remove views in reverse order)
-- ============================================================================
-- DROP VIEW IF EXISTS public.v_value_observations_canonical;
-- DROP VIEW IF EXISTS public.v_suppliers_canonical;
-- DROP VIEW IF EXISTS public.v_contracts_canonical;
-- DROP VIEW IF EXISTS public.v_open_opportunities_canonical;
-- DROP VIEW IF EXISTS public.v_entities_canonical;

COMMIT;


-- ============================================================
-- Migration: 031_source_snapshot_reconciliation.sql
-- ============================================================
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


-- ============================================================
-- Migration: 032_capability_coverage.sql
-- ============================================================
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


-- ============================================================
-- Migration: 033_contract_versioning.sql
-- ============================================================
-- ============================================================================
-- Migration 033: Contract Versioning
-- ============================================================================
-- Story 1.2 (Unify Schema) — Contract versioning support
--
-- Adiciona versionamento e auditoria de mudancas em pncp_supplier_contracts
-- usando uma tabela de historico com trigger para capturar todas as
-- alteracoes (INSERT, UPDATE, DELETE) sem modificar a tabela principal.
--
-- Depende de: 002 (pncp_supplier_contracts existe)
-- Idempotente: Sim (IF NOT EXISTS)
-- Uso de LOCK_TIMEOUT para evitar lock prolongado em producao
-- ============================================================================

BEGIN;

-- Set safety timeouts for this migration
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

-- ============================================================================
-- 1. Contract history table
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.contract_version_history (
    id              BIGSERIAL PRIMARY KEY,
    contrato_id     TEXT NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1,
    changed_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    changed_by      TEXT NOT NULL DEFAULT 'migration_033',
    change_type     TEXT NOT NULL DEFAULT 'snapshot',
    snapshot        JSONB NOT NULL,

    CONSTRAINT uq_contract_version UNIQUE (contrato_id, version)
);

COMMENT ON TABLE public.contract_version_history IS
    'Historical versions of pncp_supplier_contracts. Story 1.2';

COMMENT ON COLUMN public.contract_version_history.contrato_id IS
    'FK logica para pncp_supplier_contracts.contrato_id';
COMMENT ON COLUMN public.contract_version_history.version IS
    'Numero de versao incremental por contrato_id';
COMMENT ON COLUMN public.contract_version_history.change_type IS
    'Tipo: snapshot|upsert|correction|deletion';
COMMENT ON COLUMN public.contract_version_history.snapshot IS
    'Snapshot completo do registro no momento da captura';

-- Indexes
CREATE INDEX IF NOT EXISTS idx_cvh_contrato_id
    ON public.contract_version_history (contrato_id, version DESC);

CREATE INDEX IF NOT EXISTS idx_cvh_changed_at
    ON public.contract_version_history (changed_at DESC)
    WHERE change_type = 'snapshot';

-- ============================================================================
-- 2. Function to capture contract snapshots
-- ============================================================================
CREATE OR REPLACE FUNCTION public.fn_capture_contract_snapshot()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    max_version INTEGER;
BEGIN
    SELECT COALESCE(MAX(version), 0) + 1
    INTO max_version
    FROM public.contract_version_history
    WHERE contrato_id = COALESCE(NEW.contrato_id, OLD.contrato_id);

    INSERT INTO public.contract_version_history (
        contrato_id, version, changed_by, change_type, snapshot
    ) VALUES (
        COALESCE(NEW.contrato_id, OLD.contrato_id),
        max_version,
        current_user,
        CASE
            WHEN TG_OP = 'DELETE' THEN 'deletion'
            WHEN TG_OP = 'UPDATE' THEN 'snapshot'
            ELSE 'snapshot'
        END,
        row_to_json(COALESCE(NEW, OLD))::JSONB
    );

    RETURN COALESCE(NEW, OLD);
END;
$$;

-- ============================================================================
-- 3. Trigger to capture changes
-- ============================================================================
-- NOTE: Em producao com 3.7M contratos, este trigger pode ser INTENSO.
-- Ativar apenas se o versionamento for necessario.
-- Por seguranca, criamos como disabled — ativar manualmente se precisar.
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_contract_versioning') THEN
        CREATE TRIGGER trg_contract_versioning
            AFTER INSERT OR UPDATE OR DELETE ON public.pncp_supplier_contracts
            FOR EACH ROW
            EXECUTE FUNCTION public.fn_capture_contract_snapshot();

        -- Disable by default — ONLY enable when versioning is explicitly needed
        ALTER TABLE public.pncp_supplier_contracts DISABLE TRIGGER trg_contract_versioning;
    END IF;
END $$;

COMMENT ON TRIGGER trg_contract_versioning ON public.pncp_supplier_contracts IS
    'Contract versioning trigger — DISABLED by default. Enable via: ALTER TABLE ... ENABLE TRIGGER trg_contract_versioning; Story 1.2';

-- ============================================================================
-- Rollback SQL
-- ============================================================================
-- DROP TRIGGER IF EXISTS trg_contract_versioning ON public.pncp_supplier_contracts;
-- DROP FUNCTION IF EXISTS public.fn_capture_contract_snapshot;
-- DROP TABLE IF EXISTS public.contract_version_history;

COMMIT;


-- ============================================================
-- Migration: 034_supplier_identity.sql
-- ============================================================
-- ============================================================================
-- Migration 034: Supplier Identity — FK Constraints + UNIQUE cnpj_8 + ID Enhancements
-- ============================================================================
-- Story 1.2 (Unify Schema) — Tasks 8 (FK constraints DT-19/DT-20) and 9 (UNIQUE cnpj_8 DT-06)
--
-- 1. FK pncp_raw_bids.orgao_cnpj → sc_public_entities (DT-19)
-- 2. FK pncp_supplier_contracts → sc_public_entities (DT-20)
-- 3. UNIQUE constraint on sc_public_entities.cnpj_8 (DT-06) with pre-check
-- 4. Supplier identity index improvements
--
-- DESIGN DECISIONS:
--   - FKs usam NOT VALID + VALIDATE para evitar lock prolongado
--   - UNIQUE constraint usa pre-check com relatorio de duplicatas
--   - LOCK_TIMEOUT=5s para evitar lock de tabelas grandes em producao
--
-- Depende de: 001 (pncp_raw_bids), 002 (pncp_supplier_contracts), 007 (sc_public_entities)
-- Idempotente: Sim
-- ============================================================================

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

-- ============================================================================
-- PART 1: Pre-check for UNIQUE constraint on sc_public_entities.cnpj_8
-- ============================================================================
-- Gera relatorio de duplicatas ANTES de tentar criar a constraint.
-- A constraint so e criada se nao houver duplicatas.

DO $$
DECLARE
    dup_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO dup_count
    FROM (
        SELECT cnpj_8 FROM public.sc_public_entities
        WHERE cnpj_8 IS NOT NULL AND cnpj_8 != ''
        GROUP BY cnpj_8
        HAVING COUNT(*) > 1
    ) dups;

    IF dup_count > 0 THEN
        RAISE WARNING 'UNIQUE cnpj_8 pre-check: % duplicatas encontradas. Criando relatorio.', dup_count;
    ELSE
        RAISE NOTICE 'UNIQUE cnpj_8 pre-check: OK — nenhuma duplicata.';
    END IF;
END $$;

-- ============================================================================
-- PART 2: Add UNIQUE constraint on cnpj_8 (if no duplicates)
-- ============================================================================
-- NOTE: Em producao com duplicatas, executar manualmente:
--   1. Analisar duplicatas: SELECT cnpj_8, COUNT(*) FROM sc_public_entities
--      WHERE cnpj_8 IS NOT NULL GROUP BY cnpj_8 HAVING COUNT(*) > 1;
--   2. Resolver duplicatas
--   3. CREATE UNIQUE INDEX CONCURRENTLY uq_spe_cnpj_8 ON sc_public_entities (cnpj_8);
--   4. ALTER TABLE sc_public_entities ADD CONSTRAINT uq_spe_cnpj_8
--      UNIQUE USING INDEX uq_spe_cnpj_8;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_spe_cnpj_8') THEN
        -- Check for duplicates one more time
        IF NOT EXISTS (
            SELECT 1 FROM (
                SELECT cnpj_8 FROM public.sc_public_entities
                WHERE cnpj_8 IS NOT NULL AND cnpj_8 != ''
                GROUP BY cnpj_8 HAVING COUNT(*) > 1
            ) dups
        ) THEN
            ALTER TABLE public.sc_public_entities
                ADD CONSTRAINT uq_spe_cnpj_8 UNIQUE (cnpj_8);
            RAISE NOTICE 'UNIQUE constraint uq_spe_cnpj_8 created successfully.';
        ELSE
            RAISE WARNING 'Cannot create UNIQUE constraint: duplicates exist in sc_public_entities.cnpj_8. Execute dedup first.';
        END IF;
    ELSE
        RAISE NOTICE 'UNIQUE constraint uq_spe_cnpj_8 already exists.';
    END IF;
END $$;

COMMENT ON CONSTRAINT uq_spe_cnpj_8 ON public.sc_public_entities IS
    'Unique constraint on CNPJ base (8 digits). Created by Story 1.2 (DT-06).';

-- ============================================================================
-- PART 3: FK pncp_raw_bids.orgao_cnpj → sc_public_entities (DT-19)
-- ============================================================================
-- Usando NOT VALID para evitar lock full na tabela pncp_raw_bids.
-- A validacao pode ser feita em segundo plano.

DO $$
DECLARE
    orphan_count INTEGER;
BEGIN
    -- Pre-check: contar orfaos
    SELECT COUNT(*) INTO orphan_count
    FROM public.pncp_raw_bids b
    WHERE b.orgao_cnpj IS NOT NULL AND b.orgao_cnpj != ''
      AND NOT EXISTS (
          SELECT 1 FROM public.sc_public_entities e
          WHERE e.cnpj_8 = LEFT(b.orgao_cnpj, 8)
      );

    IF orphan_count > 0 THEN
        RAISE WARNING 'FK pre-check: % registros orfaos em pncp_raw_bids.orgao_cnpj (sem entidade correspondente).', orphan_count;
    END IF;
END $$;

-- FK: pncp_raw_bids.orgao_cnpj → sc_public_entities.cnpj_8 (via LEFT 8)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_bids_orgao_entity') THEN
        ALTER TABLE public.pncp_raw_bids
            ADD CONSTRAINT fk_bids_orgao_entity
            FOREIGN KEY (orgao_cnpj) REFERENCES public.sc_public_entities(cnpj_8)
            ON UPDATE CASCADE ON DELETE SET NULL
            NOT VALID;  -- Avoid full table scan during migration
        RAISE NOTICE 'FK fk_bids_orgao_entity created (NOT VALID). Run VALIDATE later.';
    END IF;
END $$;

COMMENT ON CONSTRAINT fk_bids_orgao_entity ON public.pncp_raw_bids IS
    'FK orgao_cnpj → sc_public_entities.cnpj_8. Created NOT VALID por Story 1.2 (DT-19). Validar: ALTER TABLE pncp_raw_bids VALIDATE CONSTRAINT fk_bids_orgao_entity;';

-- ============================================================================
-- PART 4: FK pncp_supplier_contracts → sc_public_entities (DT-20)
-- ============================================================================
-- Mapeia fornecedor_cnpj → sc_public_entities (LEFT 8)
DO $$
DECLARE
    orphan_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO orphan_count
    FROM public.pncp_supplier_contracts c
    WHERE c.fornecedor_cnpj IS NOT NULL AND c.fornecedor_cnpj != ''
      AND NOT EXISTS (
          SELECT 1 FROM public.sc_public_entities e
          WHERE e.cnpj_8 = LEFT(c.fornecedor_cnpj, 8)
      );

    IF orphan_count > 0 THEN
        RAISE WARNING 'FK pre-check: % registros orfaos em pncp_supplier_contracts.fornecedor_cnpj.', orphan_count;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_contracts_supplier_entity') THEN
        ALTER TABLE public.pncp_supplier_contracts
            ADD CONSTRAINT fk_contracts_supplier_entity
            FOREIGN KEY (fornecedor_cnpj) REFERENCES public.sc_public_entities(cnpj_8)
            ON UPDATE CASCADE ON DELETE SET NULL
            NOT VALID;
        RAISE NOTICE 'FK fk_contracts_supplier_entity created (NOT VALID).';
    END IF;
END $$;

COMMENT ON CONSTRAINT fk_contracts_supplier_entity ON public.pncp_supplier_contracts IS
    'FK fornecedor_cnpj → sc_public_entities.cnpj_8. Story 1.2 (DT-20).';

-- FK: contract orgao_cnpj → sc_public_entities
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_contracts_orgao_entity') THEN
        ALTER TABLE public.pncp_supplier_contracts
            ADD CONSTRAINT fk_contracts_orgao_entity
            FOREIGN KEY (orgao_cnpj) REFERENCES public.sc_public_entities(cnpj_8)
            ON UPDATE CASCADE ON DELETE SET NULL
            NOT VALID;
        RAISE NOTICE 'FK fk_contracts_orgao_entity created (NOT VALID).';
    END IF;
END $$;

-- ============================================================================
-- PART 5: Supplier identity — index for supplier lookups
-- ============================================================================
-- Note: is_active check only on tables that have it (pncp_raw_bids)
CREATE INDEX IF NOT EXISTS idx_contracts_fornecedor_cnpj_lookup
    ON public.pncp_supplier_contracts (fornecedor_cnpj)
    WHERE fornecedor_cnpj IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_bids_orgao_cnpj_lookup
    ON public.pncp_raw_bids (orgao_cnpj, data_publicacao DESC)
    WHERE orgao_cnpj IS NOT NULL;

-- ============================================================================
-- Rollback SQL
-- ============================================================================
-- ALTER TABLE public.pncp_raw_bids DROP CONSTRAINT IF EXISTS fk_bids_orgao_entity;
-- ALTER TABLE public.pncp_supplier_contracts DROP CONSTRAINT IF EXISTS fk_contracts_supplier_entity;
-- ALTER TABLE public.pncp_supplier_contracts DROP CONSTRAINT IF EXISTS fk_contracts_orgao_entity;
-- ALTER TABLE public.sc_public_entities DROP CONSTRAINT IF EXISTS uq_spe_cnpj_8;

COMMIT;


-- ============================================================
-- Migration: 035_value_observations.sql
-- ============================================================
-- ============================================================================
-- Migration 035: Value Observations + Retention Policies
-- ============================================================================
-- Story 1.2 (Unify Schema) — Task 10 (Retention Policies DT-22)
--
-- 1. Enhanced purge_old_bids with configurable retention
-- 2. Value observation materialization for bid_simulator
-- 3. Retention metadata columns
--
-- DESIGN:
--   - Politica de retencao configurada via parametros (nao hardcoded)
--   - Purging seguro com dry-run mode e batch processing
--   - LOCK_TIMEOUT=5s para operacoes em tabelas grandes
--
-- Depende de: 008 (purge_rpc), 030 (canonical views)
-- Idempotente: Sim
-- ============================================================================

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

-- ============================================================================
-- PART 1: Enhanced purge function with configurable retention
-- ============================================================================
-- Substitui a purge_rpc basica (008) por uma versao com:
--   - Parametros de configuracao (dias, dry_run, batch_size)
--   - Suporte a soft-delete (is_active = FALSE)
--   - Logging de resultados
--   ============================================================================

CREATE OR REPLACE FUNCTION public.fn_purge_old_data(
    p_table     TEXT DEFAULT 'pncp_raw_bids',
    p_field     TEXT DEFAULT 'data_publicacao',
    p_retention_days INTEGER DEFAULT 730,  -- 2 anos
    p_dry_run   BOOLEAN DEFAULT TRUE,
    p_batch_size INTEGER DEFAULT 10000
)
RETURNS TABLE (
    action      TEXT,
    table_name  TEXT,
    rows_affected BIGINT,
    duration_ms DOUBLE PRECISION
) LANGUAGE plpgsql AS $$
DECLARE
    cutoff_date DATE;
    v_count     BIGINT;
    start_ts    TIMESTAMPTZ;
    end_ts      TIMESTAMPTZ;
BEGIN
    cutoff_date := CURRENT_DATE - p_retention_days;
    start_ts := clock_timestamp();

    -- Validate table/field to prevent SQL injection (whitelist)
    IF p_table NOT IN ('pncp_raw_bids', 'pncp_supplier_contracts') THEN
        RETURN QUERY SELECT 'error'::TEXT, p_table, 0::BIGINT, 0::DOUBLE PRECISION;
        RETURN;
    END IF;
    IF p_field NOT IN ('data_publicacao', 'data_encerramento', 'ingested_at') THEN
        RETURN QUERY SELECT 'error'::TEXT, p_field, 0::BIGINT, 0::DOUBLE PRECISION;
        RETURN;
    END IF;

    IF p_table = 'pncp_raw_bids' THEN
        EXECUTE format(
            'SELECT COUNT(*) FROM %I WHERE %I < $1 AND is_active = TRUE',
            p_table, p_field
        ) INTO v_count USING cutoff_date;

        IF p_dry_run THEN
            end_ts := clock_timestamp();
            RETURN QUERY SELECT 'dry-run'::TEXT, p_table, v_count,
                EXTRACT(EPOCH FROM (end_ts - start_ts)) * 1000;
        ELSE
            -- Batch delete (soft-delete: is_active = FALSE preserves FK integrity)
            LOOP
                EXECUTE format(
                    'UPDATE %I SET is_active = FALSE WHERE %I < $1 AND is_active = TRUE LIMIT $2',
                    p_table, p_field
                ) USING cutoff_date, p_batch_size;

                EXIT WHEN NOT FOUND;
            END LOOP;

            end_ts := clock_timestamp();
            RETURN QUERY SELECT 'purged'::TEXT, p_table, v_count,
                EXTRACT(EPOCH FROM (end_ts - start_ts)) * 1000;
        END IF;
    ELSE
        -- pncp_supplier_contracts (mesma logica)
        EXECUTE format(
            'SELECT COUNT(*) FROM %I WHERE %I < $1 AND is_active = TRUE',
            p_table, p_field
        ) INTO v_count USING cutoff_date;

        IF p_dry_run THEN
            end_ts := clock_timestamp();
            RETURN QUERY SELECT 'dry-run'::TEXT, p_table, v_count,
                EXTRACT(EPOCH FROM (end_ts - start_ts)) * 1000;
        ELSE
            LOOP
                EXECUTE format(
                    'UPDATE %I SET is_active = FALSE WHERE %I < $1 AND is_active = TRUE LIMIT $2',
                    p_table, p_field
                ) USING cutoff_date, p_batch_size;
                EXIT WHEN NOT FOUND;
            END LOOP;

            end_ts := clock_timestamp();
            RETURN QUERY SELECT 'purged'::TEXT, p_table, v_count,
                EXTRACT(EPOCH FROM (end_ts - start_ts)) * 1000;
        END IF;
    END IF;
END;
$$;

COMMENT ON FUNCTION public.fn_purge_old_data IS
    'Configurable data retention purge. Default: 730 days. Use dry_run=TRUE to preview. Story 1.2 (DT-22)';

-- ============================================================================
-- PART 2: Retention tracking table
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.retention_policy (
    id              BIGSERIAL PRIMARY KEY,
    table_name      TEXT NOT NULL,
    field_name      TEXT NOT NULL,
    retention_days  INTEGER NOT NULL DEFAULT 730,
    strategy        TEXT NOT NULL DEFAULT 'soft_delete',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_retention_policy UNIQUE (table_name, field_name),
    CONSTRAINT ck_retention_strategy CHECK (strategy IN ('soft_delete', 'hard_delete', 'archive'))
);

COMMENT ON TABLE public.retention_policy IS
    'Retention policy configuration. Story 1.2 (DT-22)';

-- Default policies
INSERT INTO public.retention_policy (table_name, field_name, retention_days, strategy)
VALUES
    ('pncp_raw_bids', 'data_publicacao', 730, 'soft_delete'),
    ('pncp_supplier_contracts', 'data_publicacao', 1095, 'soft_delete')  -- 3 anos para contratos
ON CONFLICT (table_name, field_name) DO NOTHING;

-- ============================================================================
-- PART 3: Value observation statistics function
-- ============================================================================
CREATE OR REPLACE FUNCTION public.fn_value_statistics(
    p_uf           TEXT DEFAULT NULL,
    p_modalidade_id INTEGER DEFAULT NULL,
    p_days         INTEGER DEFAULT 365
)
RETURNS TABLE (
    observation_type TEXT,
    total_observations BIGINT,
    avg_valor       NUMERIC(18,2),
    median_valor    NUMERIC(18,2),
    min_valor       NUMERIC(18,2),
    max_valor       NUMERIC(18,2),
    p25_valor       NUMERIC(18,2),
    p75_valor       NUMERIC(18,2),
    stddev_valor    NUMERIC(18,2)
) LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        v.observation_type,
        COUNT(*)::BIGINT,
        ROUND(AVG(v.valor), 2),
        ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY v.valor)::NUMERIC, 2),
        ROUND(MIN(v.valor), 2),
        ROUND(MAX(v.valor), 2),
        ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY v.valor)::NUMERIC, 2),
        ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY v.valor)::NUMERIC, 2),
        ROUND(STDDEV(v.valor)::NUMERIC, 2)
    FROM public.v_value_observations_canonical v
    WHERE (p_uf IS NULL OR v.uf = p_uf)
      AND (p_modalidade_id IS NULL OR v.modalidade_id = p_modalidade_id)
      AND v.data_publicacao >= CURRENT_DATE - p_days
      AND v.valor IS NOT NULL
    GROUP BY v.observation_type
    ORDER BY v.observation_type;
END;
$$;

COMMENT ON FUNCTION public.fn_value_statistics IS
    'Statistical summary of value observations. Used by bid_simulator. Story 1.2';

-- ============================================================================
-- Rollback SQL
-- ============================================================================
-- DROP FUNCTION IF EXISTS public.fn_value_statistics;
-- DROP TABLE IF EXISTS public.retention_policy;
-- DROP FUNCTION IF EXISTS public.fn_purge_old_data;

COMMIT;


-- ============================================================
-- Migration: 036_reporting_views.sql
-- ============================================================
-- ============================================================================
-- Migration 036: Reporting Views
-- ============================================================================
-- Story 1.2 (Unify Schema) — Final reporting views
--
-- Views de reporting que dependem de todas as migrations anteriores (030-035).
-- Inclui views para:
--   1. Coverage health dashboard
--   2. Schema integrity check
--   3. Migration status
--   4. Canonical entity match summary
--
-- Depende de: 030-035 (todas as views e tabelas anteriores)
-- Idempotente: Sim (OR REPLACE)
-- ============================================================================

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

-- ============================================================================
-- 1. Coverage health dashboard view
-- ============================================================================
CREATE OR REPLACE VIEW public.v_coverage_health AS
SELECT
    ec.source,
    COUNT(*)::INTEGER AS total_entities,
    COUNT(*) FILTER (WHERE ec.is_covered)::INTEGER AS covered,
    ROUND(100.0 * COUNT(*) FILTER (WHERE ec.is_covered) / GREATEST(COUNT(*), 1), 1) AS pct_covered,
    COUNT(*) FILTER (WHERE ec.within_200km AND ec.is_covered)::INTEGER AS covered_200km,
    COUNT(*) FILTER (WHERE ec.within_200km)::INTEGER AS total_200km,
    ROUND(100.0 * COUNT(*) FILTER (WHERE ec.within_200km AND ec.is_covered) / GREATEST(COUNT(*) FILTER (WHERE ec.within_200km), 1), 1) AS pct_200km,
    MAX(ec.last_seen_at)::DATE AS last_coverage_date,
    NOW()::DATE - MAX(ec.last_seen_at)::DATE AS days_since_last_coverage
FROM public.entity_coverage ec
GROUP BY ec.source
ORDER BY ec.source;

COMMENT ON VIEW public.v_coverage_health IS
    'Coverage health per source. Story 1.2';

-- ============================================================================
-- 2. Schema integrity check view
-- ============================================================================
CREATE OR REPLACE VIEW public.v_schema_integrity AS
SELECT
    'tables'::TEXT AS check_type,
    COUNT(*)::INTEGER AS total_expected,
    COUNT(*) FILTER (WHERE EXISTS (
        SELECT 1 FROM information_schema.tables t
        WHERE t.table_schema = 'public'
        AND t.table_name = o.object_name
    ))::INTEGER AS present,
    COUNT(*) FILTER (WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.tables t
        WHERE t.table_schema = 'public'
        AND t.table_name = o.object_name
    ))::INTEGER AS missing
FROM (VALUES
    ('pncp_raw_bids'), ('pncp_supplier_contracts'), ('sc_public_entities'),
    ('enriched_entities'), ('entity_coverage'), ('entity_hierarchy'),
    ('coverage_snapshots'), ('coverage_evidence'), ('opportunity_intel'),
    ('ingestion_runs'), ('ingestion_checkpoints')
) AS o(object_name)

UNION ALL

SELECT
    'views'::TEXT AS check_type,
    COUNT(*)::INTEGER,
    COUNT(*) FILTER (WHERE EXISTS (
        SELECT 1 FROM information_schema.views v
        WHERE v.table_schema = 'public'
        AND v.table_name = o.object_name
    ))::INTEGER,
    COUNT(*) FILTER (WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.views v
        WHERE v.table_schema = 'public'
        AND v.table_name = o.object_name
    ))::INTEGER
FROM (VALUES
    ('v_entities_canonical'), ('v_open_opportunities_canonical'),
    ('v_contracts_canonical'), ('v_suppliers_canonical'),
    ('v_value_observations_canonical'), ('v_latest_evidence'),
    ('v_source_health'), ('v_coverage_health'),
    ('v_schema_integrity'), ('v_capability_coverage_summary')
) AS o(object_name)

UNION ALL

SELECT
    'fk_constraints'::TEXT,
    COUNT(*)::INTEGER,
    COUNT(*) FILTER (WHERE EXISTS (
        SELECT 1 FROM pg_constraint c
        JOIN pg_class cl ON c.conrelid = cl.oid
        WHERE c.conname = o.object_name
    ))::INTEGER,
    COUNT(*) FILTER (WHERE NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        JOIN pg_class cl ON c.conrelid = cl.oid
        WHERE c.conname = o.object_name
    ))::INTEGER
FROM (VALUES
    ('fk_bids_orgao_entity'), ('fk_contracts_supplier_entity'),
    ('fk_contracts_orgao_entity'), ('uq_spe_cnpj_8'),
    ('uq_oi_content_hash')
) AS o(object_name);

COMMENT ON VIEW public.v_schema_integrity IS
    'Schema integrity check — tables, views, constraints expected vs actual. Story 1.2';

-- ============================================================================
-- 3. Migration status view
-- ============================================================================
CREATE OR REPLACE VIEW public.v_migration_status AS
SELECT
    version,
    name,
    applied_at,
    checksum,
    CASE
        WHEN rollback_sql IS NOT NULL THEN 'reversible'
        ELSE 'irreversible'
    END AS reversibility,
    CASE
        WHEN checksum IS NOT NULL THEN 'verified'
        ELSE 'unverified'
    END AS integrity_status
FROM public._migrations
ORDER BY version::INTEGER;

COMMENT ON VIEW public.v_migration_status IS
    'Migration tracking status. Story 1.2';

-- ============================================================================
-- 4. Entity match summary view
-- ============================================================================
CREATE OR REPLACE VIEW public.v_entity_match_summary AS
SELECT
    b.match_method,
    COUNT(*)::INTEGER AS total_bids,
    COUNT(*) FILTER (WHERE b.matched_entity_id IS NOT NULL)::INTEGER AS matched,
    ROUND(100.0 * COUNT(*) FILTER (WHERE b.matched_entity_id IS NOT NULL) / GREATEST(COUNT(*), 1), 1) AS pct_matched,
    MIN(b.match_score) AS min_score,
    MAX(b.match_score) AS max_score,
    ROUND(AVG(b.match_score)::NUMERIC, 3) AS avg_score,
    COUNT(DISTINCT b.matched_entity_id)::INTEGER AS distinct_entities
FROM public.pncp_raw_bids b
WHERE b.match_method IS NOT NULL
GROUP BY b.match_method
ORDER BY b.match_method;

COMMENT ON VIEW public.v_entity_match_summary IS
    'Entity match performance by method. Story 1.2';

-- ============================================================================
-- Rollback SQL
-- ============================================================================
-- DROP VIEW IF EXISTS public.v_entity_match_summary;
-- DROP VIEW IF EXISTS public.v_migration_status;
-- DROP VIEW IF EXISTS public.v_schema_integrity;
-- DROP VIEW IF EXISTS public.v_coverage_health;

COMMIT;


-- ============================================================
-- Migration: 037_target_universe_snapshot.sql
-- ============================================================
-- Migration 037: Target Universe Snapshot Tables
--
-- Creates the authoritative snapshot tables for the canonical target universe.
-- target_universe_runs tracks each seed snapshot (immutable after creation).
-- target_universe_entities stores per-entity snapshot data linked to a run.
--
-- Design:
--   - Idempotent (IF NOT EXISTS) for safe re-execution
--   - Universe run_id is used by all analytic queries to filter by snapshot
--   - Indexes on (universe_run_id, canonical_entity_key) for join performance
--   - Append-only: no UPDATE or DELETE on snapshot rows
--   - seed_sha256 enables seed-change detection at startup
--
-- References:
--   Story 1.3: Universe Authority
--   Constitution Article IV (No Invention): schema derived from seed structure
--   Plano mestre Secao 7 (P0-03)

BEGIN;

-- -----------------------------------------------------------------------
-- target_universe_runs
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS target_universe_runs (
    id              BIGSERIAL    PRIMARY KEY,
    seed_sha256     TEXT         NOT NULL,
    seed_filename   TEXT         NOT NULL,
    radius_km       NUMERIC(6,1) NOT NULL DEFAULT 200.0,
    total_rows      INTEGER      NOT NULL DEFAULT 0,
    included_rows   INTEGER      NOT NULL DEFAULT 0,
    excluded_rows   INTEGER      NOT NULL DEFAULT 0,
    unresolved_rows INTEGER      NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    git_sha         TEXT
);

-- Immutable: no UPDATE allowed after creation
COMMENT ON TABLE target_universe_runs IS
    'Immutable snapshot of a seed-based target universe run. '
    'Append-only — rows are never updated or deleted.';

COMMENT ON COLUMN target_universe_runs.seed_sha256 IS
    'SHA-256 hex digest of the seed spreadsheet at snapshot time.';
COMMENT ON COLUMN target_universe_runs.seed_filename IS
    'Original filename of the seed spreadsheet.';
COMMENT ON COLUMN target_universe_runs.radius_km IS
    'Radius in km from Florianopolis used for the snapshot.';
COMMENT ON COLUMN target_universe_runs.total_rows IS
    'Total number of seed rows (including unresolved).';
COMMENT ON COLUMN target_universe_runs.included_rows IS
    'Number of entities within the radius (included).';
COMMENT ON COLUMN target_universe_runs.excluded_rows IS
    'Number of entities outside the radius (excluded).';
COMMENT ON COLUMN target_universe_runs.unresolved_rows IS
    'Number of entities with no radius decision (unresolved).';
COMMENT ON COLUMN target_universe_runs.created_at IS
    'Timestamp when this snapshot was generated.';
COMMENT ON COLUMN target_universe_runs.git_sha IS
    'Git commit SHA at snapshot time for full reproducibility.';

CREATE INDEX IF NOT EXISTS idx_target_universe_runs_seed_sha256
    ON target_universe_runs (seed_sha256);

-- -----------------------------------------------------------------------
-- target_universe_entities
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS target_universe_entities (
    universe_run_id     BIGINT       NOT NULL,
    canonical_entity_key TEXT        NOT NULL,
    seed_row            INTEGER      NOT NULL,
    cnpj8               VARCHAR(8)   NOT NULL,
    legal_name          TEXT         NOT NULL,
    municipality        TEXT         NOT NULL,
    ibge_code           VARCHAR(7),
    legal_nature        TEXT,
    latitude            NUMERIC(10,7),
    longitude           NUMERIC(10,7),
    distance_km         NUMERIC(8,1),
    radius_decision     VARCHAR(20)  NOT NULL DEFAULT 'unresolved',
    duplicate_root      BOOLEAN      NOT NULL DEFAULT FALSE,
    db_entity_id        INTEGER,
    match_method        VARCHAR(30),

    PRIMARY KEY (universe_run_id, canonical_entity_key),

    CONSTRAINT fk_universe_run
        FOREIGN KEY (universe_run_id)
        REFERENCES target_universe_runs (id)
        ON DELETE CASCADE
);

COMMENT ON TABLE target_universe_entities IS
    'Per-entity snapshot data linked to a target_universe_runs entry. '
    'PK (universe_run_id, canonical_entity_key) enforces no-duplicate entities per run.';

COMMENT ON COLUMN target_universe_entities.universe_run_id IS
    'Foreign key to target_universe_runs.id.';
COMMENT ON COLUMN target_universe_entities.canonical_entity_key IS
    'Stable entity identity key: hex digest of (cnpj8|municipio|razao_social).';
COMMENT ON COLUMN target_universe_entities.seed_row IS
    'Row number in the original seed spreadsheet.';
COMMENT ON COLUMN target_universe_entities.cnpj8 IS
    'First 8 digits of CNPJ (root).';
COMMENT ON COLUMN target_universe_entities.radius_decision IS
    'included | excluded | unresolved';
COMMENT ON COLUMN target_universe_entities.duplicate_root IS
    'TRUE when this CNPJ-8 root appears more than once in the seed.';
COMMENT ON COLUMN target_universe_entities.db_entity_id IS
    'sc_public_entities.id matched at snapshot time (NULL if unmatched).';
COMMENT ON COLUMN target_universe_entities.match_method IS
    'Method used to match this entity to the DB (e.g. cnpj8, name).';

-- Performance indexes for analytic queries filtering by universe_run_id
CREATE INDEX IF NOT EXISTS idx_target_universe_entities_run_id
    ON target_universe_entities (universe_run_id);

CREATE INDEX IF NOT EXISTS idx_target_universe_entities_run_canonical
    ON target_universe_entities (universe_run_id, canonical_entity_key);

CREATE INDEX IF NOT EXISTS idx_target_universe_entities_run_included
    ON target_universe_entities (universe_run_id)
    WHERE radius_decision = 'included';

CREATE INDEX IF NOT EXISTS idx_target_universe_entities_cnpj8
    ON target_universe_entities (cnpj8);

COMMIT;


-- ============================================================
-- Migration: 038_target_universe_active_view.sql
-- ============================================================
-- Migration 038: Target Universe Active View
--
-- Creates the v_target_universe_active view that resolves "current entity set"
-- through the latest snapshot instead of the raio_200km column.
--
-- All analytic queries should JOIN with this view instead of filtering
-- by sc_public_entities.raio_200km directly.
--
-- Design:
--   - Idempotent (CREATE OR REPLACE VIEW)
--   - Latest snapshot is determined by MAX(target_universe_runs.id)
--   - LEFT JOIN preserves entities even if snapshot is missing (graceful deg.)
--   - Supercedes the within_200km column for universe membership decisions
--
-- References:
--   Story 1.3: Universe Authority — Task 4 (migration) + Task 7/8 (queries)

BEGIN;

-- ============================================================================
-- v_target_universe_active — Entities in the latest snapshot
-- ============================================================================
CREATE OR REPLACE VIEW public.v_target_universe_active AS
WITH latest_run AS (
    SELECT id, seed_sha256, radius_km, created_at
    FROM target_universe_runs
    ORDER BY id DESC
    LIMIT 1
)
SELECT
    tue.universe_run_id,
    tue.canonical_entity_key,
    tue.seed_row,
    tue.cnpj8,
    tue.legal_name,
    tue.municipality,
    tue.ibge_code,
    tue.legal_nature,
    tue.latitude,
    tue.longitude,
    tue.distance_km,
    tue.radius_decision,
    tue.duplicate_root,
    tue.db_entity_id,
    tue.match_method,
    lr.seed_sha256,
    lr.radius_km           AS snapshot_radius_km,
    lr.created_at           AS snapshot_created_at,
    spe.id                  AS db_entity_id_original,
    spe.razao_social        AS db_razao_social,
    spe.municipio           AS db_municipio,
    spe.raio_200km          AS db_within_200km,
    spe.is_active           AS db_is_active
FROM target_universe_entities tue
CROSS JOIN latest_run lr
LEFT JOIN sc_public_entities spe ON spe.id = tue.db_entity_id
WHERE tue.universe_run_id = lr.id
  AND tue.radius_decision = 'included';

COMMENT ON VIEW public.v_target_universe_active IS
    'Active target universe entities from the latest snapshot. '
    'Replaces WHERE raio_200km filtering for analytic queries. Story 1.3';

COMMENT ON COLUMN public.v_target_universe_active.universe_run_id IS
    'Snapshot run ID — connect query results to a specific seed version';
COMMENT ON COLUMN public.v_target_universe_active.radius_decision IS
    'included | excluded | unresolved — from seed resolution';
COMMENT ON COLUMN public.v_target_universe_active.db_within_200km IS
    'Diagnostic: what the DB raio_200km column says (may diverge from seed)';
COMMENT ON COLUMN public.v_target_universe_active.db_entity_id_original IS
    'sc_public_entities.id for legacy joins (NULL if entity not in DB)';

-- ============================================================================
-- v_target_universe_all — All entities in the latest snapshot (incl. excluded)
-- ============================================================================
CREATE OR REPLACE VIEW public.v_target_universe_all AS
WITH latest_run AS (
    SELECT id, seed_sha256, radius_km, created_at
    FROM target_universe_runs
    ORDER BY id DESC
    LIMIT 1
)
SELECT
    tue.universe_run_id,
    tue.canonical_entity_key,
    tue.seed_row,
    tue.cnpj8,
    tue.legal_name,
    tue.municipality,
    tue.ibge_code,
    tue.legal_nature,
    tue.latitude,
    tue.longitude,
    tue.distance_km,
    tue.radius_decision,
    tue.duplicate_root,
    tue.db_entity_id,
    tue.match_method,
    lr.seed_sha256,
    lr.radius_km           AS snapshot_radius_km,
    lr.created_at           AS snapshot_created_at
FROM target_universe_entities tue
CROSS JOIN latest_run lr
WHERE tue.universe_run_id = lr.id;

COMMENT ON VIEW public.v_target_universe_all IS
    'All target universe entities (included + excluded + unresolved) from latest snapshot. '
    'Use for diagnostic reports and divergence analysis. Story 1.3';

COMMIT;


-- ============================================================
-- Migration: 039_source_snapshot_tracking.sql
-- ============================================================
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


-- ============================================================
-- Migration: 040_coverage_model_expansion.sql
-- ============================================================
-- ============================================================================
-- Migration 040: Coverage Model Expansion (Story 1.5)
-- ============================================================================
-- Expande a tabela coverage_evidence com campos da Secao 9 do plano mestre:
--   - canonical_entity_key, capability, applicability, scope_key
--   - pages_expected, pages_processed, records_expected
--   - freshness_status, checked_at, next_due_at
--   - period_start, period_end (alias funcional para queried_start/queried_end)
--
-- Expande o enum evidence_state com 11 estados de coverage (Secao 9):
--   - pending (novo), running (novo), blocked (novo), stale (novo)
--   - error (mapeado para os estados de erro especificos existentes)
--
-- Cria tabela materializada de aplicabilidade (Task 5)
--
-- Depende de: 024, 025 (coverage_evidence existe), 037 (target_universe_entities existe)
-- Idempotente: Sim (IF NOT EXISTS, DO $$ blocks)
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. Expandir o enum evidence_state com 4 novos estados
-- ============================================================================
-- Estados atuais: success_with_data, success_zero, partial, connection_failed,
--                  auth_failed, parse_failed, transform_failed, persist_failed,
--                  not_applicable, not_investigated
-- Novos estados:  pending, running, blocked, stale
-- Mapeamento:     "error" e o nome generico; os estados especificos existentes
--                 (connection_failed, auth_failed, etc.) continuam valendo.

-- PostgreSQL nao permite ALTER ENUM ADD VALUE dentro de uma transacao que
-- tambem faz outras operacoes. Usamos DO $$ blocks para cada ADD VALUE.
-- Cada um e uma transacao implicita separada (via DO).

DO $$ BEGIN
    ALTER TYPE evidence_state ADD VALUE IF NOT EXISTS 'pending' BEFORE 'running';
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TYPE evidence_state ADD VALUE IF NOT EXISTS 'running' BEFORE 'success_with_data';
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TYPE evidence_state ADD VALUE IF NOT EXISTS 'blocked' AFTER 'persist_failed';
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TYPE evidence_state ADD VALUE IF NOT EXISTS 'stale' AFTER 'blocked';
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================================================
-- 2. Adicionar novas colunas a coverage_evidence (Secao 9)
-- ============================================================================

-- canonical_entity_key: ligacao com o universo canonico (target_universe_entities)
ALTER TABLE coverage_evidence
    ADD COLUMN IF NOT EXISTS canonical_entity_key TEXT;

COMMENT ON COLUMN coverage_evidence.canonical_entity_key IS
    'Stable entity identity key linking to target_universe_entities.canonical_entity_key. Story 1.5';

-- capability: qual capacidade de negocio esta sendo medida
ALTER TABLE coverage_evidence
    ADD COLUMN IF NOT EXISTS capability TEXT;

COMMENT ON COLUMN coverage_evidence.capability IS
    'Capacidade: open_tenders|historical_contracts|competitors|prices|entity_matching|coverage_truth|source_health. Story 1.5';

-- applicability: se o par (ente x fonte x capacidade) e aplicavel
ALTER TABLE coverage_evidence
    ADD COLUMN IF NOT EXISTS applicability TEXT;

COMMENT ON COLUMN coverage_evidence.applicability IS
    'Decisao de aplicabilidade: applicable|not_applicable|unknown. Story 1.5';

-- applicability_reason: justificativa para a decisao de aplicabilidade
ALTER TABLE coverage_evidence
    ADD COLUMN IF NOT EXISTS applicability_reason TEXT;

COMMENT ON COLUMN coverage_evidence.applicability_reason IS
    'Justificativa para a decisao de aplicabilidade (ex: fonte federal so para entes PNCP). Story 1.5';

-- scope_key: escopo da execucao (ex: "SC_90d", "BR_2024")
ALTER TABLE coverage_evidence
    ADD COLUMN IF NOT EXISTS scope_key TEXT;

COMMENT ON COLUMN coverage_evidence.scope_key IS
    'Chave do escopo de execucao (ex: SC_90d, BR_2024_full). Story 1.5';

-- pages_expected: numero de paginas esperadas para paginacao completa
ALTER TABLE coverage_evidence
    ADD COLUMN IF NOT EXISTS pages_expected INT;

COMMENT ON COLUMN coverage_evidence.pages_expected IS
    'Numero de paginas esperadas para paginacao completa. Story 1.5';

-- pages_processed: numero de paginas efetivamente processadas
ALTER TABLE coverage_evidence
    ADD COLUMN IF NOT EXISTS pages_processed INT;

COMMENT ON COLUMN coverage_evidence.pages_processed IS
    'Numero de paginas efetivamente processadas. Story 1.5';

-- records_expected: numero de registros esperados (total estimado)
ALTER TABLE coverage_evidence
    ADD COLUMN IF NOT EXISTS records_expected INT;

COMMENT ON COLUMN coverage_evidence.records_expected IS
    'Numero de registros esperados (total estimado antes da execucao). Story 1.5';

-- freshness_status: estado de atualizacao dos dados
ALTER TABLE coverage_evidence
    ADD COLUMN IF NOT EXISTS freshness_status TEXT;

COMMENT ON COLUMN coverage_evidence.freshness_status IS
    'Estado de atualizacao: fresh|stale|unknown|overdue. Story 1.5';

-- checked_at: quando a verificacao foi feita
ALTER TABLE coverage_evidence
    ADD COLUMN IF NOT EXISTS checked_at TIMESTAMPTZ;

COMMENT ON COLUMN coverage_evidence.checked_at IS
    'Momento exato da verificacao de cobertura. Story 1.5';

-- next_due_at: quando a proxima verificacao deve ocorrer
ALTER TABLE coverage_evidence
    ADD COLUMN IF NOT EXISTS next_due_at TIMESTAMPTZ;

COMMENT ON COLUMN coverage_evidence.next_due_at IS
    'Prazo para a proxima verificacao. Story 1.5';

-- period_start / period_end: alias funcional para queried_start / queried_end
-- (as colunas ja existem como queried_start e queried_end)
-- Criamos uma view de compatibilidade em vez de renomear colunas existentes.

-- ============================================================================
-- 3. Indices para as novas colunas
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_ce_capability
    ON coverage_evidence (capability)
    WHERE capability IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_ce_applicability
    ON coverage_evidence (applicability, source, entity_id)
    WHERE applicability IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_ce_freshness
    ON coverage_evidence (freshness_status, next_due_at)
    WHERE freshness_status IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_ce_canonical_key
    ON coverage_evidence (canonical_entity_key)
    WHERE canonical_entity_key IS NOT NULL;

-- ============================================================================
-- 4. View de compatibilidade: coverage_evidence com nomenclatura Secao 9
-- ============================================================================

CREATE OR REPLACE VIEW v_coverage_evidence_expanded AS
SELECT
    id,
    entity_id,
    canonical_entity_key,
    capability,
    source,
    data_type,
    applicability,
    applicability_reason,
    scope_key,
    -- Compatibilidade: period_start = queried_start, period_end = queried_end
    queried_start       AS period_start,
    queried_end         AS period_end,
    run_id              AS source_run_id,
    state,
    -- Mapeamento de contagens
    count_obtained      AS records_fetched,
    count_transformed   AS records_transformed,
    count_persisted     AS records_persisted,
    records_expected,
    pages_expected,
    pages_processed,
    -- Freshness
    freshness_status,
    checked_at,
    next_due_at,
    -- Erros
    error_code,
    error_message,
    -- Metadata
    metadata            AS evidence_metadata,
    started_at,
    completed_at
FROM coverage_evidence;

COMMENT ON VIEW v_coverage_evidence_expanded IS
    'Coverage evidence com nomenclatura expandida da Secao 9. Story 1.5. '
    'Compativel com o schema antigo: todas as colunas originais continuam existindo na tabela base.';

-- ============================================================================
-- 5. Tabela materializada de aplicabilidade (Task 5)
-- ============================================================================
-- Regras de decisao:
--   - Fontes federais (PNCP, ComprasGov): aplicaveis a entes com esfera federal OU
--     entes municipais que aderem voluntariamente ao PNCP
--   - Fontes estaduais (TCE-SC, DOE-SC, SC Compras): aplicaveis a entes de SC
--   - Fontes municipais (DOM-SC, CIGA CKAN): aplicaveis a entes municipais de SC
--   - PCP: multiplataforma, aplicavel amplamente
--   - Transparencia: aplicavel a entes com portal de transparencia
-- ============================================================================

-- Tabela base para regras de aplicabilidade
CREATE TABLE IF NOT EXISTS source_applicability_rules (
    id                  BIGSERIAL PRIMARY KEY,
    source              TEXT NOT NULL,
    -- Filtros de decisao
    esfera_filter       TEXT,       -- federal|estadual|municipal|* (todos)
    natureza_filter     TEXT,       -- pref|cam|gov|aut|* (todos)
    plataforma_filter   TEXT,       -- pncp_aderente|* (todos)
    municipio_filter    TEXT,       -- regex ou * (todos)
    -- Resultado
    is_applicable       BOOLEAN NOT NULL DEFAULT TRUE,
    reason              TEXT NOT NULL DEFAULT '',
    priority            INT NOT NULL DEFAULT 0, -- maior = maior prioridade
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_applicability_rule UNIQUE (source, esfera_filter, natureza_filter, plataforma_filter)
);

COMMENT ON TABLE source_applicability_rules IS
    'Regras de decisao de aplicabilidade por fonte. Story 1.5';
COMMENT ON COLUMN source_applicability_rules.esfera_filter IS
    'Filtro por esfera: federal|estadual|municipal|*';
COMMENT ON COLUMN source_applicability_rules.natureza_filter IS
    'Filtro por natureza juridica: pref|cam|gov|aut|*';
COMMENT ON COLUMN source_applicability_rules.plataforma_filter IS
    'Filtro por plataforma: pncp_aderente|*';

-- Seed rules (valores iniciais, serao refinados em P0-06 a P0-09)
INSERT INTO source_applicability_rules (source, esfera_filter, natureza_filter, is_applicable, reason, priority) VALUES
    -- PNCP: todas as esferas, todas as naturezas (adesao voluntaria)
    ('pncp',           '*', '*', TRUE,  'Fonte federal com adesao voluntaria de todas as esferas', 0),
    -- ComprasGov: todas as esferas, todas as naturezas
    ('compras_gov',    '*', '*', TRUE,  'Compras federais com adesao multiesfera', 0),
    -- DOM-SC: apenas municipios de SC
    ('dom_sc',         'municipal', '*', TRUE,  'Diario oficial dos municipios de SC', 10),
    ('dom_sc',         'estadual',  '*', FALSE, 'DOM-SC nao cobre entes estaduais', 10),
    ('dom_sc',         'federal',   '*', FALSE, 'DOM-SC nao cobre entes federais', 10),
    -- PCP: multiplataforma
    ('pcp',            '*', '*', TRUE,  'Portal de Compras Publicas — multiplataforma', 0),
    -- SC Compras: apenas entes de SC
    ('sc_compras',     '*', '*', TRUE,  'Plataforma estadual SC', 0),
    -- TCE-SC: apenas entes de SC
    ('tce_sc',         '*', '*', TRUE,  'Tribunal de Contas de SC', 0),
    -- DOE-SC: apenas entes estaduais de SC
    ('doe_sc',         'estadual', '*', TRUE,  'Diario oficial estadual de SC', 10),
    ('doe_sc',         'municipal', '*', FALSE, 'DOE-SC nao cobre entes municipais diretamente', 10),
    ('doe_sc',         'federal',   '*', FALSE, 'DOE-SC nao cobre entes federais', 10),
    -- Transparencia: entes com portal verificavel
    ('transparencia',  '*', '*', TRUE,  'Portal da transparencia — aplicavel quando portal existe', 0),
    -- CIGA CKAN: municipios de SC
    ('ciga_ckan',      'municipal', '*', TRUE,  'CIGA CKAN — dados municipais de SC', 10),
    ('ciga_ckan',      'estadual',  '*', FALSE, 'CIGA CKAN nao cobre entes estaduais', 10),
    ('ciga_ckan',      'federal',   '*', FALSE, 'CIGA CKAN nao cobre entes federais', 10),
    -- MIDES BigQuery: entes estaduais de SC
    ('mides_bigquery', 'estadual',  '*', TRUE,  'MIDES BigQuery — dados estaduais', 10),
    ('mides_bigquery', 'municipal', '*', FALSE, 'MIDES BigQuery nao cobre entes municipais', 10),
    ('mides_bigquery', 'federal',   '*', FALSE, 'MIDES BigQuery nao cobre entes federais', 10)
ON CONFLICT (source, esfera_filter, natureza_filter, plataforma_filter) DO NOTHING;

-- Trigger de updated_at
CREATE OR REPLACE FUNCTION fn_applicability_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_applicability_updated_at') THEN
        CREATE TRIGGER trg_applicability_updated_at
            BEFORE UPDATE ON source_applicability_rules
            FOR EACH ROW
            EXECUTE FUNCTION fn_applicability_updated_at();
    END IF;
END $$;

-- ============================================================================
-- 6. View materializada: aplicabilidade por (ente, source)
-- ============================================================================
-- Para cada ente ativo x fonte, decide se e aplicavel com base nas regras.
-- Usa a visao canonica v_entities_canonical (migration 030).
-- ============================================================================

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_entity_source_applicability AS
WITH
-- Fontes ativas do registry (expanded list)
sources(source) AS (
    VALUES
        ('pncp'),
        ('dom_sc'),
        ('pcp'),
        ('compras_gov'),
        ('sc_compras'),
        ('transparencia'),
        ('tce_sc'),
        ('doe_sc'),
        ('ciga_ckan'),
        ('mides_bigquery')
),
-- Decisao por regra: para cada (ente, source), pega a regra de maior prioridade
entity_rules AS (
    SELECT
        e.entity_id,
        s.source,
        -- Determina esfera
        CASE
            WHEN e.natureza_juridica LIKE '%FEDERAL%' OR e.cod_natureza LIKE '1%' THEN 'federal'
            WHEN e.natureza_juridica LIKE '%ESTADUAL%' OR e.cod_natureza LIKE '2%' THEN 'estadual'
            ELSE 'municipal'
        END AS esfera,
        -- Determina natureza simplificada
        CASE
            WHEN e.natureza_juridica LIKE '%PREFEITURA%' OR e.cod_natureza LIKE '1%' THEN 'pref'
            WHEN e.natureza_juridica LIKE '%CAMARA%' OR e.cod_natureza LIKE '12%' THEN 'cam'
            WHEN e.natureza_juridica LIKE '%GOVERNO%' OR e.cod_natureza LIKE '10%' THEN 'gov'
            WHEN e.natureza_juridica LIKE '%AUTARQUIA%' OR e.cod_natureza LIKE '2%' THEN 'aut'
            ELSE 'outro'
        END AS natureza_simplificada
    FROM v_entities_canonical e
    CROSS JOIN sources s
    WHERE e.is_active = TRUE
)
SELECT
    er.entity_id,
    er.source,
    er.esfera,
    er.natureza_simplificada AS natureza,
    COALESCE(MAX(r.priority), 0) AS rule_priority,
    BOOL_OR(r.is_applicable) AS is_applicable,
    -- Pega a razao da regra de maior prioridade que se aplica
    (
        SELECT r2.reason
        FROM source_applicability_rules r2
        WHERE r2.source = er.source
          AND (r2.esfera_filter = '*' OR r2.esfera_filter = er.esfera)
          AND (r2.natureza_filter = '*' OR r2.natureza_filter = er.natureza_simplificada)
          AND r2.is_active = TRUE
        ORDER BY r2.priority DESC
        LIMIT 1
    ) AS reason,
    NOW() AS calculated_at
FROM entity_rules er
LEFT JOIN source_applicability_rules r
    ON r.source = er.source
    AND r.is_active = TRUE
    AND (r.esfera_filter = '*' OR r.esfera_filter = er.esfera)
    AND (r.natureza_filter = '*' OR r.natureza_filter = er.natureza_simplificada)
GROUP BY er.entity_id, er.source, er.esfera, er.natureza_simplificada
ORDER BY er.entity_id, er.source;

COMMENT ON MATERIALIZED VIEW mv_entity_source_applicability IS
    'Aplicabilidade materializada por (ente, source). Atualizar via REFRESH MATERIALIZED VIEW. Story 1.5';

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_applicability_entity_source
    ON mv_entity_source_applicability (entity_id, source);

CREATE INDEX IF NOT EXISTS idx_mv_applicability_source
    ON mv_entity_source_applicability (source, is_applicable);

-- ============================================================================
-- 7. View de cobertura por capacidade (coverage manifest)
-- ============================================================================

CREATE OR REPLACE VIEW v_coverage_manifest AS
SELECT
    COALESCE(ce.capability, 'open_tenders') AS capability,
    ce.source,
    COUNT(*) FILTER (WHERE ce.entity_id IS NOT NULL) AS total_entity_pairs,
    COUNT(*) FILTER (WHERE ce.entity_id IS NOT NULL AND ce.state IN ('success_with_data', 'success_zero')) AS covered_pairs,
    COUNT(*) FILTER (WHERE ce.entity_id IS NOT NULL AND ce.state = 'success_with_data') AS with_data,
    COUNT(*) FILTER (WHERE ce.entity_id IS NOT NULL AND ce.state = 'success_zero') AS zero_data,
    COUNT(*) FILTER (WHERE ce.entity_id IS NOT NULL AND ce.state = 'partial') AS partial,
    COUNT(*) FILTER (WHERE ce.entity_id IS NOT NULL AND ce.state IN ('pending', 'running')) AS in_progress,
    COUNT(*) FILTER (WHERE ce.entity_id IS NOT NULL AND ce.state = 'blocked') AS blocked,
    COUNT(*) FILTER (WHERE ce.entity_id IS NOT NULL AND ce.state = 'stale') AS stale,
    COUNT(*) FILTER (WHERE ce.entity_id IS NOT NULL AND ce.state LIKE '%failed') AS errored,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE ce.entity_id IS NOT NULL AND ce.state IN ('success_with_data', 'success_zero'))
        / GREATEST(COUNT(*) FILTER (WHERE ce.entity_id IS NOT NULL), 1), 1
    ) AS pct_covered,
    MAX(ce.completed_at) AS last_check_at
FROM coverage_evidence ce
WHERE ce.entity_id IS NOT NULL
GROUP BY ce.capability, ce.source
ORDER BY ce.capability, ce.source;

COMMENT ON VIEW v_coverage_manifest IS
    'Coverage manifest por capacidade e fonte. Story 1.5. '
    'Metricas independentes: data presence nao altera coverage (success_zero conta como covered).';

-- ============================================================================
-- Rollback
-- ============================================================================
-- DROP VIEW IF EXISTS v_coverage_manifest;
-- DROP MATERIALIZED VIEW IF EXISTS mv_entity_source_applicability;
-- DROP TRIGGER IF EXISTS trg_applicability_updated_at ON source_applicability_rules;
-- DROP FUNCTION IF EXISTS fn_applicability_updated_at;
-- DROP TABLE IF EXISTS source_applicability_rules;
-- DROP VIEW IF EXISTS v_coverage_evidence_expanded;
-- ALTER TABLE coverage_evidence DROP COLUMN IF EXISTS canonical_entity_key;
-- ALTER TABLE coverage_evidence DROP COLUMN IF EXISTS capability;
-- ALTER TABLE coverage_evidence DROP COLUMN IF EXISTS applicability;
-- ALTER TABLE coverage_evidence DROP COLUMN IF EXISTS applicability_reason;
-- ALTER TABLE coverage_evidence DROP COLUMN IF EXISTS scope_key;
-- ALTER TABLE coverage_evidence DROP COLUMN IF EXISTS pages_expected;
-- ALTER TABLE coverage_evidence DROP COLUMN IF EXISTS pages_processed;
-- ALTER TABLE coverage_evidence DROP COLUMN IF EXISTS records_expected;
-- ALTER TABLE coverage_evidence DROP COLUMN IF EXISTS freshness_status;
-- ALTER TABLE coverage_evidence DROP COLUMN IF EXISTS checked_at;
-- ALTER TABLE coverage_evidence DROP COLUMN IF EXISTS next_due_at;

COMMIT;


-- ============================================================
-- Migration: 041_fix_fk_constraints.sql
-- ============================================================
-- ============================================================================
-- Migration 041: Fix FK Constraints — 14-digit CNPJ vs 8-digit cnpj_8 mismatch
-- ============================================================================
-- Story 1.2 (Unify Schema) — CRITICAL bugfix
--
-- PROBLEM:
-- Migration 034 created 3 FKs that reference sc_public_entities(cnpj_8) which
-- stores 8-digit CNPJ base, but the source columns contain full 14-digit CNPJ:
--
--   fk_bids_orgao_entity:
--     pncp_raw_bids.orgao_cnpj (14-digit) → sc_public_entities.cnpj_8 (8-digit)
--   fk_contracts_orgao_entity:
--     pncp_supplier_contracts.orgao_cnpj (14-digit) → sc_public_entities.cnpj_8 (8-digit)
--   fk_contracts_supplier_entity:
--     pncp_supplier_contracts.fornecedor_cnpj (14-digit) → sc_public_entities.cnpj_8 (8-digit)
--
-- A FK constraint compares values literally: "12345678901234" != "12345678",
-- so the FKs can never be validated and will reject all INSERT/UPDATE.
--
-- FIX:
-- 1. Drop the 3 broken FKs
-- 2. Add GENERATED ALWAYS AS (LEFT(col, 8)) STORED columns to child tables
-- 3. Create new FKs on the generated 8-digit columns
-- 4. All new FKs use NOT VALID to avoid locking -- VALIDATE separately
--
-- Depende de: 034_supplier_identity.sql (criou as FKs quebradas)
-- Idempotente: Sim (DROP IF EXISTS / IF NOT EXISTS)
-- ============================================================================

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

-- ============================================================================
-- PART 1: Drop broken FKs
-- ============================================================================
-- As FKs originais comparam CNPJ de 14 digitos com cnpj_8 de 8 digitos.
-- Mesmo com NOT VALID, elas blockeriam qualquer INSERT/UPDATE que nao
-- encontrasse um valor de 14 digitos em sc_public_entities.cnpj_8.

ALTER TABLE IF EXISTS public.pncp_raw_bids
    DROP CONSTRAINT IF EXISTS fk_bids_orgao_entity;

ALTER TABLE IF EXISTS public.pncp_supplier_contracts
    DROP CONSTRAINT IF EXISTS fk_contracts_orgao_entity;

ALTER TABLE IF EXISTS public.pncp_supplier_contracts
    DROP CONSTRAINT IF EXISTS fk_contracts_supplier_entity;

RAISE NOTICE 'Part 1: Dropped 3 broken FKs (fk_bids_orgao_entity, fk_contracts_orgao_entity, fk_contracts_supplier_entity).';

-- ============================================================================
-- PART 2: Add generated cnpj_8 columns to child tables
-- ============================================================================
-- Colunas GENERATED ALWAYS AS STORED mantem-se sincronizadas automaticamente
-- com o valor original. Nao podem ser escritas diretamente (somente leitura).
-- Usamos LEFT(col, 8) para extrair os primeiros 8 digitos do CNPJ,
-- que e exatamente o que as views existentes ja fazem via LEFT() nas JOINs.

-- pncp_raw_bids: orgao_cnpj -> orgao_cnpj_8
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'pncp_raw_bids'
          AND column_name = 'orgao_cnpj_8'
    ) THEN
        ALTER TABLE public.pncp_raw_bids
            ADD COLUMN orgao_cnpj_8 TEXT
            GENERATED ALWAYS AS (LEFT(orgao_cnpj, 8)) STORED;
        RAISE NOTICE 'Added orgao_cnpj_8 to pncp_raw_bids.';
    ELSE
        RAISE NOTICE 'orgao_cnpj_8 already exists on pncp_raw_bids.';
    END IF;
END $$;

-- pncp_supplier_contracts: orgao_cnpj -> orgao_cnpj_8
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'pncp_supplier_contracts'
          AND column_name = 'orgao_cnpj_8'
    ) THEN
        ALTER TABLE public.pncp_supplier_contracts
            ADD COLUMN orgao_cnpj_8 TEXT
            GENERATED ALWAYS AS (LEFT(orgao_cnpj, 8)) STORED;
        RAISE NOTICE 'Added orgao_cnpj_8 to pncp_supplier_contracts.';
    ELSE
        RAISE NOTICE 'orgao_cnpj_8 already exists on pncp_supplier_contracts.';
    END IF;
END $$;

-- pncp_supplier_contracts: fornecedor_cnpj -> fornecedor_cnpj_8
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'pncp_supplier_contracts'
          AND column_name = 'fornecedor_cnpj_8'
    ) THEN
        ALTER TABLE public.pncp_supplier_contracts
            ADD COLUMN fornecedor_cnpj_8 TEXT
            GENERATED ALWAYS AS (LEFT(fornecedor_cnpj, 8)) STORED;
        RAISE NOTICE 'Added fornecedor_cnpj_8 to pncp_supplier_contracts.';
    ELSE
        RAISE NOTICE 'fornecedor_cnpj_8 already exists on pncp_supplier_contracts.';
    END IF;
END $$;

-- ============================================================================
-- PART 3: Create valid FKs on generated columns
-- ============================================================================
-- As novas FKs usam as colunas geradas de 8 digitos, que tem o mesmo tipo
-- (TEXT) e mesmo comprimento que sc_public_entities.cnpj_8.
--
-- NOT VALID: evita lock full nas tabelas durante a criacao.
-- A validacao deve ser executada separadamente em horario de baixo trafego:
--   ALTER TABLE pncp_raw_bids VALIDATE CONSTRAINT fk_bids_orgao_entity_v2;
--   ALTER TABLE pncp_supplier_contracts VALIDATE CONSTRAINT fk_contracts_orgao_entity_v2;
--   ALTER TABLE pncp_supplier_contracts VALIDATE CONSTRAINT fk_contracts_supplier_entity_v2;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_bids_orgao_entity_v2') THEN
        ALTER TABLE public.pncp_raw_bids
            ADD CONSTRAINT fk_bids_orgao_entity_v2
            FOREIGN KEY (orgao_cnpj_8) REFERENCES public.sc_public_entities(cnpj_8)
            ON UPDATE CASCADE ON DELETE SET NULL
            NOT VALID;
        RAISE NOTICE 'FK fk_bids_orgao_entity_v2 created (NOT VALID).';
    ELSE
        RAISE NOTICE 'FK fk_bids_orgao_entity_v2 already exists.';
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_contracts_orgao_entity_v2') THEN
        ALTER TABLE public.pncp_supplier_contracts
            ADD CONSTRAINT fk_contracts_orgao_entity_v2
            FOREIGN KEY (orgao_cnpj_8) REFERENCES public.sc_public_entities(cnpj_8)
            ON UPDATE CASCADE ON DELETE SET NULL
            NOT VALID;
        RAISE NOTICE 'FK fk_contracts_orgao_entity_v2 created (NOT VALID).';
    ELSE
        RAISE NOTICE 'FK fk_contracts_orgao_entity_v2 already exists.';
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_contracts_supplier_entity_v2') THEN
        ALTER TABLE public.pncp_supplier_contracts
            ADD CONSTRAINT fk_contracts_supplier_entity_v2
            FOREIGN KEY (fornecedor_cnpj_8) REFERENCES public.sc_public_entities(cnpj_8)
            ON UPDATE CASCADE ON DELETE SET NULL
            NOT VALID;
        RAISE NOTICE 'FK fk_contracts_supplier_entity_v2 created (NOT VALID).';
    ELSE
        RAISE NOTICE 'FK fk_contracts_supplier_entity_v2 already exists.';
    END IF;
END $$;

-- ============================================================================
-- PART 4: Comments documenting the fix
-- ============================================================================

COMMENT ON COLUMN public.pncp_raw_bids.orgao_cnpj_8 IS
    'CNPJ base 8 digitos (generated). FK target for sc_public_entities. Fix 041.';

COMMENT ON COLUMN public.pncp_supplier_contracts.orgao_cnpj_8 IS
    'CNPJ base 8 digitos (generated). FK target for sc_public_entities. Fix 041.';

COMMENT ON COLUMN public.pncp_supplier_contracts.fornecedor_cnpj_8 IS
    'CNPJ base 8 digitos (generated). FK target for sc_public_entities. Fix 041.';

COMMENT ON CONSTRAINT fk_bids_orgao_entity_v2 ON public.pncp_raw_bids IS
    'FK orgao_cnpj_8 -> sc_public_entities.cnpj_8. Fix 041 (substitui fk_bids_orgao_entity que usava 14-digit orgao_cnpj contra cnpj_8 de 8 digitos). Validar: ALTER TABLE pncp_raw_bids VALIDATE CONSTRAINT fk_bids_orgao_entity_v2;';

COMMENT ON CONSTRAINT fk_contracts_orgao_entity_v2 ON public.pncp_supplier_contracts IS
    'FK orgao_cnpj_8 -> sc_public_entities.cnpj_8. Fix 041. Validar: ALTER TABLE pncp_supplier_contracts VALIDATE CONSTRAINT fk_contracts_orgao_entity_v2;';

COMMENT ON CONSTRAINT fk_contracts_supplier_entity_v2 ON public.pncp_supplier_contracts IS
    'FK fornecedor_cnpj_8 -> sc_public_entities.cnpj_8. Fix 041. Validar: ALTER TABLE pncp_supplier_contracts VALIDATE CONSTRAINT fk_contracts_supplier_entity_v2;';

-- ============================================================================
-- PART 5: Indexes on generated columns for FK lookup performance
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_bids_orgao_cnpj_8
    ON public.pncp_raw_bids (orgao_cnpj_8)
    WHERE orgao_cnpj_8 IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_contracts_orgao_cnpj_8
    ON public.pncp_supplier_contracts (orgao_cnpj_8)
    WHERE orgao_cnpj_8 IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_contracts_fornecedor_cnpj_8
    ON public.pncp_supplier_contracts (fornecedor_cnpj_8)
    WHERE fornecedor_cnpj_8 IS NOT NULL;

RAISE NOTICE 'Fix 041 complete. Run VALIDATE CONSTRAINT separately for each FK in low-traffic window.';

-- ============================================================================
-- PART 6: Update schema integrity view to reference new FK names
-- ============================================================================
-- Migration 036 criou v_schema_integrity com os nomes antigos das FKs.
-- Como 041 substitui fk_bids_orgao_entity → fk_bids_orgao_entity_v2 (etc),
-- precisamos atualizar a view para que o check de integridade reflita
-- os nomes corretos.

CREATE OR REPLACE VIEW public.v_schema_integrity AS
SELECT
    'tables'::TEXT AS check_type,
    COUNT(*)::INTEGER AS total_expected,
    COUNT(*) FILTER (WHERE EXISTS (
        SELECT 1 FROM information_schema.tables t
        WHERE t.table_schema = 'public'
        AND t.table_name = o.object_name
    ))::INTEGER AS present,
    COUNT(*) FILTER (WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.tables t
        WHERE t.table_schema = 'public'
        AND t.table_name = o.object_name
    ))::INTEGER AS missing
FROM (VALUES
    ('pncp_raw_bids'), ('pncp_supplier_contracts'), ('sc_public_entities'),
    ('enriched_entities'), ('entity_coverage'), ('entity_hierarchy'),
    ('coverage_snapshots'), ('coverage_evidence'), ('opportunity_intel'),
    ('ingestion_runs'), ('ingestion_checkpoints')
) AS o(object_name)

UNION ALL

SELECT
    'views'::TEXT AS check_type,
    COUNT(*)::INTEGER,
    COUNT(*) FILTER (WHERE EXISTS (
        SELECT 1 FROM information_schema.views v
        WHERE v.table_schema = 'public'
        AND v.table_name = o.object_name
    ))::INTEGER,
    COUNT(*) FILTER (WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.views v
        WHERE v.table_schema = 'public'
        AND v.table_name = o.object_name
    ))::INTEGER
FROM (VALUES
    ('v_entities_canonical'), ('v_open_opportunities_canonical'),
    ('v_contracts_canonical'), ('v_suppliers_canonical'),
    ('v_value_observations_canonical'), ('v_latest_evidence'),
    ('v_source_health'), ('v_coverage_health'),
    ('v_schema_integrity'), ('v_capability_coverage_summary')
) AS o(object_name)

UNION ALL

SELECT
    'fk_constraints'::TEXT,
    COUNT(*)::INTEGER,
    COUNT(*) FILTER (WHERE EXISTS (
        SELECT 1 FROM pg_constraint c
        JOIN pg_class cl ON c.conrelid = cl.oid
        WHERE c.conname = o.object_name
    ))::INTEGER,
    COUNT(*) FILTER (WHERE NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        JOIN pg_class cl ON c.conrelid = cl.oid
        WHERE c.conname = o.object_name
    ))::INTEGER
FROM (VALUES
    ('fk_bids_orgao_entity_v2'), ('fk_contracts_supplier_entity_v2'),
    ('fk_contracts_orgao_entity_v2'), ('uq_spe_cnpj_8'),
    ('uq_oi_content_hash')
) AS o(object_name);

RAISE NOTICE 'Part 6: Updated v_schema_integrity view with new FK constraint names.';

-- ============================================================================
-- Rollback SQL
-- ============================================================================
-- ALTER TABLE public.pncp_raw_bids DROP CONSTRAINT IF EXISTS fk_bids_orgao_entity_v2;
-- ALTER TABLE public.pncp_supplier_contracts DROP CONSTRAINT IF EXISTS fk_contracts_orgao_entity_v2;
-- ALTER TABLE public.pncp_supplier_contracts DROP CONSTRAINT IF EXISTS fk_contracts_supplier_entity_v2;
-- ALTER TABLE public.pncp_raw_bids DROP COLUMN IF EXISTS orgao_cnpj_8;
-- ALTER TABLE public.pncp_supplier_contracts DROP COLUMN IF EXISTS orgao_cnpj_8;
-- ALTER TABLE public.pncp_supplier_contracts DROP COLUMN IF EXISTS fornecedor_cnpj_8;
-- DROP INDEX IF EXISTS idx_bids_orgao_cnpj_8;
-- DROP INDEX IF EXISTS idx_contracts_orgao_cnpj_8;
-- DROP INDEX IF EXISTS idx_contracts_fornecedor_cnpj_8;
-- ============================================================================

COMMIT;


-- ============================================================
-- Migration: 041_fix_snapshot_membership.sql
-- ============================================================
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

