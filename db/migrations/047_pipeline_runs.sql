-- 047_pipeline_runs.sql
-- Provenance tracking for every crawl pipeline run.
-- Created for DF-1B.3 (DATA-FOUNDATION epic).
--
-- Idempotent: IF NOT EXISTS guards.

BEGIN;

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id              TEXT PRIMARY KEY,
    source              TEXT NOT NULL,
    mode                TEXT NOT NULL DEFAULT 'full',  -- 'full', 'incremental', 'backfill'
    params              JSONB,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    status              TEXT NOT NULL DEFAULT 'running',  -- 'running', 'completed', 'failed', 'killed'
    period_start        DATE,
    period_end          DATE,
    pages_planned       INT DEFAULT 0,
    pages_completed     INT DEFAULT 0,
    records_fetched     INT DEFAULT 0,
    records_deduplicated INT DEFAULT 0,
    records_upserted    INT DEFAULT 0,
    records_dlq         INT DEFAULT 0,
    records_failed      INT DEFAULT 0,
    duration_ms         INT DEFAULT 0,
    error_message       TEXT,
    watermarks_committed INT DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_source
    ON pipeline_runs (source, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status
    ON pipeline_runs (status);

COMMIT;
