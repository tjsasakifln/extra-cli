-- 083_crawl_queue_canonical_entity.sql
-- Upgrade repair: the active denominator has 1,093 canonical IDs but 1,090 DB roots.

BEGIN;

ALTER TABLE crawl_jobs ADD COLUMN IF NOT EXISTS canonical_entity_key TEXT;
UPDATE crawl_jobs
SET canonical_entity_key = 'db:' || entity_id::text
WHERE canonical_entity_key IS NULL;
ALTER TABLE crawl_jobs ALTER COLUMN canonical_entity_key SET NOT NULL;

DROP INDEX IF EXISTS uq_crawl_jobs_active_pair;
CREATE UNIQUE INDEX uq_crawl_jobs_active_pair
    ON crawl_jobs (canonical_entity_key, source, capability)
    WHERE status IN ('queued', 'running');
CREATE UNIQUE INDEX IF NOT EXISTS uq_crawl_jobs_canonical_window_idempotency
    ON crawl_jobs (
        canonical_entity_key, source, capability,
        window_start, window_end, idempotency_key
    );

ALTER TABLE crawl_entity_source_schedule ADD COLUMN IF NOT EXISTS canonical_entity_key TEXT;
UPDATE crawl_entity_source_schedule
SET canonical_entity_key = 'db:' || entity_id::text
WHERE canonical_entity_key IS NULL;
ALTER TABLE crawl_entity_source_schedule ALTER COLUMN canonical_entity_key SET NOT NULL;
ALTER TABLE crawl_entity_source_schedule DROP CONSTRAINT IF EXISTS crawl_entity_source_schedule_pkey;
ALTER TABLE crawl_entity_source_schedule
    ADD PRIMARY KEY (canonical_entity_key, source, capability);

COMMIT;
