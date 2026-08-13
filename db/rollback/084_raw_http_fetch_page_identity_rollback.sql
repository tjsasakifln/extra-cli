-- WARNING: destructive rollback. Reintroducing body-based envelope uniqueness
-- can fail when distinct request/pages legitimately share the same body.

BEGIN;

ALTER TABLE raw_http_fetches
    ADD CONSTRAINT raw_http_fetches_run_id_source_request_scope_body_sha256_key
    UNIQUE (run_id, source, request_scope, body_sha256);

COMMIT;
