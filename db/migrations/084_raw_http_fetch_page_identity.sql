-- 084_raw_http_fetch_page_identity.sql
-- Preserve one immutable envelope per request/page even when bodies are equal.
-- The CAS still deduplicates body bytes by SHA-256.

BEGIN;

ALTER TABLE raw_http_fetches
    DROP CONSTRAINT IF EXISTS raw_http_fetches_run_id_source_request_scope_body_sha256_key;

COMMIT;
