-- #458: align crawl_failure_events with the shipped diagnostics classifier.
-- Persistence failures are permanent local failures until storage/schema is
-- repaired; they must be recorded instead of failing the diagnostic insert.

BEGIN;

ALTER TABLE crawl_failure_events
    DROP CONSTRAINT IF EXISTS crawl_failure_events_error_class_check;

ALTER TABLE crawl_failure_events
    ADD CONSTRAINT crawl_failure_events_error_class_check CHECK (error_class IN (
        'AUTH_BLOCKED', 'SOURCE_DRIFT', 'RATE_LIMITED',
        'UPSTREAM_TRANSIENT', 'TRANSPORT_TRANSIENT',
        'PARSE_OR_SCHEMA_DRIFT', 'PERSIST_FAILURE',
        'UNCLASSIFIED_FAILURE'
    ));

COMMIT;
