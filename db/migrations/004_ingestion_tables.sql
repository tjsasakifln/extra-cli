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
