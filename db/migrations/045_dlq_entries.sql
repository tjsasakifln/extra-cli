-- 045_dlq_entries.sql
-- Dead Letter Queue — durable storage for failed pipeline records.
-- Created for DF-1B.1 (DATA-FOUNDATION epic).
--
-- Idempotent: IF NOT EXISTS guards applied to all CREATE statements.

BEGIN;

-- ===========================================================================
-- DLQ entries table
-- ===========================================================================

CREATE TABLE IF NOT EXISTS dlq_entries (
    id              BIGSERIAL PRIMARY KEY,
    source          TEXT NOT NULL,
    run_id          TEXT NOT NULL,
    phase           TEXT NOT NULL,        -- 'fetch', 'parse', 'transform', 'upsert'
    payload         JSONB,
    error_code      TEXT,
    error_message   TEXT,
    error_traceback TEXT,
    retry_count     INT NOT NULL DEFAULT 0,
    max_retries     INT NOT NULL DEFAULT 3,
    status          TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'replayed', 'dead', 'archived'
    failed_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    replayed_at     TIMESTAMPTZ,
    replayed_by     TEXT,                 -- run_id that replayed this entry
    purge_after     TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '90 days')
);

-- Index: source + status for efficient queries
CREATE INDEX IF NOT EXISTS idx_dlq_source_status
    ON dlq_entries (source, status);

-- Index: unreplayed entries for worker polling
CREATE INDEX IF NOT EXISTS idx_dlq_pending
    ON dlq_entries (failed_at, id)
    WHERE status = 'pending';

-- Index: purge target for cleanup queries
CREATE INDEX IF NOT EXISTS idx_dlq_purge
    ON dlq_entries (purge_after)
    WHERE status IN ('dead', 'archived');

-- ===========================================================================
-- Audit trigger: record last_checked_at updates
-- ===========================================================================

CREATE OR REPLACE FUNCTION update_dlq_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Only add column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'dlq_entries' AND column_name = 'updated_at'
    ) THEN
        ALTER TABLE dlq_entries ADD COLUMN updated_at TIMESTAMPTZ DEFAULT NOW();
    END IF;
END $$;

DROP TRIGGER IF EXISTS trg_dlq_updated_at ON dlq_entries;
CREATE TRIGGER trg_dlq_updated_at
    BEFORE UPDATE ON dlq_entries
    FOR EACH ROW
    EXECUTE FUNCTION update_dlq_updated_at();

COMMIT;
