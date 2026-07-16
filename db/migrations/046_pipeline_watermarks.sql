-- 046_pipeline_watermarks.sql
-- Watermarks with overlap support for resilient crawl resumption.
-- Created for DF-1B.2 (DATA-FOUNDATION epic).
--
-- Idempotent: IF NOT EXISTS guards.

BEGIN;

-- ===========================================================================
-- Watermarks table
-- ===========================================================================

CREATE TABLE IF NOT EXISTS pipeline_watermarks (
    id              BIGSERIAL PRIMARY KEY,
    source          TEXT NOT NULL,
    scope_key       TEXT NOT NULL DEFAULT 'default',
    watermark_type  TEXT NOT NULL,        -- 'page', 'date', 'entity', 'chunk'
    watermark_value TEXT NOT NULL,
    run_id          TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'committed',  -- 'committed', 'in_progress', 'stalled'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    committed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source, scope_key, watermark_type, watermark_value)
);

CREATE INDEX IF NOT EXISTS idx_watermarks_source_status
    ON pipeline_watermarks (source, status);

CREATE INDEX IF NOT EXISTS idx_watermarks_stalled
    ON pipeline_watermarks (status, committed_at)
    WHERE status = 'in_progress';

-- ===========================================================================
-- Function: commit watermark (upsert pattern)
-- ===========================================================================

CREATE OR REPLACE FUNCTION commit_watermark(
    p_source TEXT,
    p_scope_key TEXT,
    p_watermark_type TEXT,
    p_watermark_value TEXT,
    p_run_id TEXT
) RETURNS BIGINT AS $$
DECLARE
    v_id BIGINT;
BEGIN
    INSERT INTO pipeline_watermarks (source, scope_key, watermark_type, watermark_value, run_id, status)
    VALUES (p_source, p_scope_key, p_watermark_type, p_watermark_value, p_run_id, 'committed')
    ON CONFLICT (source, scope_key, watermark_type, watermark_value)
    DO UPDATE SET
        run_id = EXCLUDED.run_id,
        status = 'committed',
        committed_at = NOW()
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$ LANGUAGE plpgsql;

-- ===========================================================================
-- Function: get last committed watermark for a source
-- ===========================================================================

CREATE OR REPLACE FUNCTION get_last_watermark(
    p_source TEXT,
    p_watermark_type TEXT DEFAULT 'page'
) RETURNS TABLE (
    watermark_value TEXT,
    run_id TEXT,
    committed_at TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT w.watermark_value, w.run_id, w.committed_at
    FROM pipeline_watermarks w
    WHERE w.source = p_source
      AND w.watermark_type = p_watermark_type
      AND w.status = 'committed'
    ORDER BY w.committed_at DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

COMMIT;
