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
