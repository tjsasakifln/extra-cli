BEGIN;
ALTER TABLE crawl_entity_source_schedule DROP CONSTRAINT IF EXISTS crawl_entity_source_schedule_pkey;
ALTER TABLE crawl_entity_source_schedule ADD PRIMARY KEY (entity_id, source, capability);
ALTER TABLE crawl_entity_source_schedule DROP COLUMN IF EXISTS canonical_entity_key;
DROP INDEX IF EXISTS uq_crawl_jobs_canonical_window_idempotency;
DROP INDEX IF EXISTS uq_crawl_jobs_active_pair;
CREATE UNIQUE INDEX uq_crawl_jobs_active_pair
    ON crawl_jobs (entity_id, source, capability)
    WHERE status IN ('queued', 'running');
ALTER TABLE crawl_jobs DROP COLUMN IF EXISTS canonical_entity_key;
COMMIT;
