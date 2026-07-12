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
