BEGIN;

-- Fail closed: canonical identities may legitimately share one legacy entity_id.
-- An operator must explicitly reconcile the reported rows (and approve which
-- canonical schedule/active job survives) before this lossy rollback is retried.
DO $rollback_guard$
DECLARE
    schedule_collisions JSONB;
    active_job_collisions JSONB;
BEGIN
    SELECT COALESCE(jsonb_agg(to_jsonb(collision)), '[]'::jsonb)
    INTO schedule_collisions
    FROM (
        SELECT entity_id, source, capability, COUNT(*) AS row_count
        FROM crawl_entity_source_schedule
        GROUP BY entity_id, source, capability
        HAVING COUNT(*) > 1
        ORDER BY entity_id, source, capability
        LIMIT 25
    ) AS collision;

    SELECT COALESCE(jsonb_agg(to_jsonb(collision)), '[]'::jsonb)
    INTO active_job_collisions
    FROM (
        SELECT entity_id, source, capability, COUNT(*) AS row_count
        FROM crawl_jobs
        WHERE status IN ('queued', 'running')
        GROUP BY entity_id, source, capability
        HAVING COUNT(*) > 1
        ORDER BY entity_id, source, capability
        LIMIT 25
    ) AS collision;

    IF schedule_collisions <> '[]'::jsonb OR active_job_collisions <> '[]'::jsonb THEN
        RAISE EXCEPTION USING
            MESSAGE = 'rollback 083 blocked: canonical rows collide on legacy identity',
            DETAIL = jsonb_build_object(
                'schedule_collisions', schedule_collisions,
                'active_job_collisions', active_job_collisions
            )::text,
            HINT = 'Explicitly reconcile the reported canonical rows and cancel redundant active jobs, record approval, then retry.';
    END IF;
END
$rollback_guard$;

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
