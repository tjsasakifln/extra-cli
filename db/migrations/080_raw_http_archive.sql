-- 080_raw_http_archive.sql
-- #247: metadata-only index for immutable HTTP envelopes and off-database CAS bodies.

BEGIN;

CREATE TABLE IF NOT EXISTS raw_http_fetches (
    id                       BIGSERIAL PRIMARY KEY,
    run_id                   TEXT NOT NULL,
    crawl_job_attempt_id     BIGINT REFERENCES crawl_job_attempts(id) ON DELETE SET NULL,
    source                   TEXT NOT NULL,
    request_scope            TEXT NOT NULL,
    page                     INTEGER CHECK (page IS NULL OR page >= 0),
    sanitized_url            TEXT,
    http_status              INTEGER CHECK (http_status IS NULL OR http_status BETWEEN 100 AND 599),
    request_succeeded        BOOLEAN NOT NULL,
    body_sha256              TEXT NOT NULL CHECK (body_sha256 ~ '^[0-9a-f]{64}$'),
    body_size_bytes          BIGINT NOT NULL CHECK (body_size_bytes >= 0),
    body_uri                 TEXT NOT NULL CHECK (body_uri LIKE 'cas://raw-http/%'),
    envelope_uri             TEXT NOT NULL,
    envelope_sha256          TEXT NOT NULL CHECK (envelope_sha256 ~ '^[0-9a-f]{64}$'),
    observed_at              TIMESTAMPTZ NOT NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (run_id, source, request_scope, body_sha256),
    UNIQUE (envelope_sha256)
);

CREATE INDEX IF NOT EXISTS idx_raw_http_fetches_attempt
    ON raw_http_fetches (crawl_job_attempt_id)
    WHERE crawl_job_attempt_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_raw_http_fetches_body
    ON raw_http_fetches (body_sha256);

COMMIT;
