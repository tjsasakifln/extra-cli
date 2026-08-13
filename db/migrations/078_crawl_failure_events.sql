-- 078_crawl_failure_events.sql
-- #279: sanitized, structured request/page diagnostics. No response body or
-- credential-bearing headers are stored in PostgreSQL.

BEGIN;

CREATE OR REPLACE FUNCTION crawl_metadata_has_secret_key(doc JSONB)
RETURNS BOOLEAN
LANGUAGE plpgsql
IMMUTABLE
PARALLEL SAFE
AS $function$
DECLARE
    item_key TEXT;
    item_value JSONB;
BEGIN
    IF jsonb_typeof(doc) = 'object' THEN
        FOR item_key, item_value IN SELECT * FROM jsonb_each(doc)
        LOOP
            IF lower(item_key) = ANY (ARRAY[
                'authorization', 'proxy-authorization', 'cookie', 'set-cookie',
                'x-api-key', 'password', 'passwd', 'token', 'secret', 'dsn'
            ]) OR crawl_metadata_has_secret_key(item_value) THEN
                RETURN TRUE;
            END IF;
        END LOOP;
    ELSIF jsonb_typeof(doc) = 'array' THEN
        FOR item_value IN SELECT value FROM jsonb_array_elements(doc)
        LOOP
            IF crawl_metadata_has_secret_key(item_value) THEN
                RETURN TRUE;
            END IF;
        END LOOP;
    END IF;
    RETURN FALSE;
END
$function$;

CREATE TABLE IF NOT EXISTS crawl_failure_events (
    id                      BIGSERIAL PRIMARY KEY,
    source                  TEXT NOT NULL,
    run_id                  TEXT NOT NULL,
    job_id                  BIGINT,
    crawl_job_attempt_id    BIGINT,
    request_scope           TEXT NOT NULL,
    stage                   TEXT NOT NULL,
    page                    INTEGER CHECK (page IS NULL OR page >= 0),
    cursor                  TEXT,
    error_class             TEXT NOT NULL CHECK (error_class IN (
        'AUTH_BLOCKED', 'SOURCE_DRIFT', 'RATE_LIMITED',
        'UPSTREAM_TRANSIENT', 'TRANSPORT_TRANSIENT',
        'PARSE_OR_SCHEMA_DRIFT', 'UNCLASSIFIED_FAILURE'
    )),
    http_status             INTEGER CHECK (http_status IS NULL OR http_status BETWEEN 100 AND 599),
    attempt_no              INTEGER NOT NULL CHECK (attempt_no >= 1),
    transient               BOOLEAN NOT NULL,
    next_action             TEXT NOT NULL,
    sanitized_url           TEXT,
    message                 TEXT NOT NULL,
    error_fingerprint       TEXT NOT NULL CHECK (error_fingerprint ~ '^[0-9a-f]{64}$'),
    metadata                JSONB NOT NULL DEFAULT '{}'::jsonb,
    observed_at             TIMESTAMPTZ NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_crawl_failure_attempt UNIQUE (
        run_id, source, request_scope, attempt_no, error_fingerprint
    ),
    CONSTRAINT ck_crawl_failure_no_secret_keys CHECK (
        NOT crawl_metadata_has_secret_key(metadata)
    )
);

CREATE INDEX IF NOT EXISTS idx_crawl_failure_source_observed
    ON crawl_failure_events (source, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_crawl_failure_class_observed
    ON crawl_failure_events (error_class, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_crawl_failure_job_attempt
    ON crawl_failure_events (job_id, crawl_job_attempt_id)
    WHERE job_id IS NOT NULL OR crawl_job_attempt_id IS NOT NULL;

COMMIT;
