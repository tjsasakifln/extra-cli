BEGIN;

DROP TABLE IF EXISTS public.truth_plane_cost_observations;
DROP TABLE IF EXISTS public.truth_plane_alert_events;
DROP TABLE IF EXISTS public.truth_plane_alert_routes;
DROP TABLE IF EXISTS public.truth_plane_kill_switch_history;
DROP TABLE IF EXISTS public.truth_plane_kill_switch;
DROP TABLE IF EXISTS public.truth_plane_sli_reviews;
DROP TABLE IF EXISTS public.truth_plane_slo_definitions;

ALTER TABLE IF EXISTS public.crawl_jobs DROP COLUMN IF EXISTS dlq_entry_id;
DROP INDEX IF EXISTS public.idx_dlq_selective_replay;
DROP INDEX IF EXISTS public.uq_dlq_job_open_terminal;

ALTER TABLE IF EXISTS public.dlq_entries
    DROP CONSTRAINT IF EXISTS ck_dlq_resolution_complete,
    DROP CONSTRAINT IF EXISTS ck_dlq_replay_count,
    DROP COLUMN IF EXISTS resolution,
    DROP COLUMN IF EXISTS resolved_by,
    DROP COLUMN IF EXISTS resolved_at,
    DROP COLUMN IF EXISTS replay_count,
    DROP COLUMN IF EXISTS terminal_at,
    DROP COLUMN IF EXISTS next_action,
    DROP COLUMN IF EXISTS owner,
    DROP COLUMN IF EXISTS payload_pointer,
    DROP COLUMN IF EXISTS error_class,
    DROP COLUMN IF EXISTS canonical_entity_key,
    DROP COLUMN IF EXISTS attempt_id,
    DROP COLUMN IF EXISTS job_id;

COMMIT;
