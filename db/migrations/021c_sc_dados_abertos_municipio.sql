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
