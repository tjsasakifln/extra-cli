BEGIN;
DROP TABLE IF EXISTS crawl_failure_events;
DROP FUNCTION IF EXISTS crawl_metadata_has_secret_key(JSONB);
COMMIT;
