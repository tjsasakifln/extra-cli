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
DO $migration$
DECLARE
    pkey_name TEXT;
    pkey_columns TEXT[];
BEGIN
    SELECT constraint_row.conname,
           array_agg(attribute_row.attname ORDER BY key_column.ordinality)
    INTO pkey_name, pkey_columns
    FROM pg_constraint AS constraint_row
    CROSS JOIN LATERAL unnest(constraint_row.conkey)
        WITH ORDINALITY AS key_column(attnum, ordinality)
    JOIN pg_attribute AS attribute_row
      ON attribute_row.attrelid = constraint_row.conrelid
     AND attribute_row.attnum = key_column.attnum
    WHERE constraint_row.conrelid = 'crawl_entity_source_schedule'::regclass
      AND constraint_row.contype = 'p'
    GROUP BY constraint_row.conname;

    IF pkey_name IS NULL THEN
        ALTER TABLE crawl_entity_source_schedule
            ADD PRIMARY KEY (canonical_entity_key, source, capability);
    ELSIF pkey_columns IS DISTINCT FROM ARRAY[
        'canonical_entity_key', 'source', 'capability'
    ]::TEXT[] THEN
        EXECUTE format(
            'ALTER TABLE crawl_entity_source_schedule DROP CONSTRAINT %I',
            pkey_name
        );
        ALTER TABLE crawl_entity_source_schedule
            ADD PRIMARY KEY (canonical_entity_key, source, capability);
    END IF;
END
$migration$;

COMMIT;
