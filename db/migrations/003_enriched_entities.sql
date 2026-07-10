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
