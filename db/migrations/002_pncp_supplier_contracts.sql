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
