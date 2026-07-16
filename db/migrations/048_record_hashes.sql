-- 048_record_hashes.sql
-- Content-hash based dedup across all sources.
-- Created for DF-1B.3 (DATA-FOUNDATION epic).
--
-- Idempotent: IF NOT EXISTS guards.

BEGIN;

CREATE TABLE IF NOT EXISTS record_hashes (
    content_hash    TEXT PRIMARY KEY,
    source          TEXT NOT NULL,
    run_id          TEXT NOT NULL,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    seen_count      INT NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_record_hashes_source
    ON record_hashes (source, last_seen_at DESC);

COMMIT;
