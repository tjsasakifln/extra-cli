-- 087_runtime_truth_dlq_sli.sql
-- Transactional crawl DLQ and fail-closed truth-plane SLI authority (#274/#275).

BEGIN;

ALTER TABLE public.dlq_entries
    ADD COLUMN IF NOT EXISTS job_id BIGINT REFERENCES public.crawl_jobs(id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS attempt_id BIGINT REFERENCES public.crawl_job_attempts(id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS canonical_entity_key TEXT,
    ADD COLUMN IF NOT EXISTS error_class TEXT,
    ADD COLUMN IF NOT EXISTS payload_pointer JSONB NOT NULL DEFAULT '{}'::JSONB,
    ADD COLUMN IF NOT EXISTS owner TEXT,
    ADD COLUMN IF NOT EXISTS next_action TEXT NOT NULL DEFAULT 'inspect_and_replay_or_resolve',
    ADD COLUMN IF NOT EXISTS terminal_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS replay_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS resolved_by TEXT,
    ADD COLUMN IF NOT EXISTS resolution TEXT;

UPDATE public.dlq_entries
SET error_class = COALESCE(error_class, error_code, 'UNCLASSIFIED')
WHERE error_class IS NULL;

-- Preserve original terminal time for rows that predate this column.
-- ADD COLUMN … DEFAULT NOW() otherwise stamps apply-time on the whole table.
UPDATE public.dlq_entries
SET terminal_at = COALESCE(failed_at, terminal_at)
WHERE failed_at IS NOT NULL
  AND (terminal_at IS NULL OR terminal_at > failed_at);

ALTER TABLE public.dlq_entries
    ALTER COLUMN error_class SET NOT NULL,
    DROP CONSTRAINT IF EXISTS ck_dlq_replay_count,
    DROP CONSTRAINT IF EXISTS ck_dlq_resolution_complete;

ALTER TABLE public.dlq_entries
    ADD CONSTRAINT ck_dlq_replay_count CHECK (replay_count >= 0),
    ADD CONSTRAINT ck_dlq_resolution_complete CHECK (
        (resolved_at IS NULL AND resolved_by IS NULL AND resolution IS NULL)
        OR (resolved_at IS NOT NULL AND resolved_by IS NOT NULL AND resolution IS NOT NULL)
    );

CREATE UNIQUE INDEX IF NOT EXISTS uq_dlq_job_open_terminal
    ON public.dlq_entries (job_id)
    WHERE job_id IS NOT NULL AND status IN ('pending', 'dead');

CREATE INDEX IF NOT EXISTS idx_dlq_selective_replay
    ON public.dlq_entries (source, canonical_entity_key, error_class, terminal_at, id)
    WHERE status IN ('pending', 'dead');

ALTER TABLE public.crawl_jobs
    ADD COLUMN IF NOT EXISTS dlq_entry_id BIGINT REFERENCES public.dlq_entries(id) ON DELETE RESTRICT;

CREATE TABLE IF NOT EXISTS public.truth_plane_slo_definitions (
    metric_name          TEXT PRIMARY KEY,
    stage                TEXT NOT NULL,
    window_seconds       INTEGER NOT NULL CHECK (window_seconds > 0),
    denominator_contract TEXT NOT NULL,
    objective_operator   TEXT NOT NULL CHECK (objective_operator IN ('lte', 'gte')),
    objective_value      NUMERIC NOT NULL CHECK (objective_value >= 0),
    unit                 TEXT NOT NULL,
    alert_before_ratio   NUMERIC NOT NULL DEFAULT 0.80,
    enabled              BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (
        (
            objective_operator = 'lte'
            AND (
                (objective_value = 0 AND alert_before_ratio = 1)
                OR (objective_value > 0 AND alert_before_ratio > 0 AND alert_before_ratio < 1)
            )
        )
        OR (
            objective_operator = 'gte'
            AND objective_value > 0
            AND alert_before_ratio > 1
        )
    )
);

INSERT INTO public.truth_plane_slo_definitions (
    metric_name, stage, window_seconds, denominator_contract,
    objective_operator, objective_value, unit, alert_before_ratio
) VALUES
    ('queue_oldest_age_seconds', 'source_to_raw', 3600, 'all queued/running crawl_jobs in the window', 'lte', 900, 'seconds', 0.80),
    ('queue_terminal_failure_ratio', 'source_to_raw', 3600, 'all terminal crawl_job_attempts in the window', 'lte', 0.05, 'ratio', 0.80),
    ('dlq_open_count', 'source_to_raw', 86400, 'all crawl jobs reaching a terminal retry threshold', 'lte', 0, 'records', 1.00),
    ('document_failure_ratio', 'raw_to_document', 3600, 'all terminal document processing runs in the window', 'lte', 0.05, 'ratio', 0.80),
    ('canonical_lag_seconds', 'document_to_canonical', 3600, 'all accepted source observations in the window', 'lte', 3600, 'seconds', 0.80),
    ('public_read_freshness_seconds', 'canonical_to_public_read_v1', 3600, 'all enabled public_read_v1 views with measured queries', 'lte', 3600, 'seconds', 0.80),
    ('public_read_query_p95_ms', 'canonical_to_public_read_v1', 300, 'all public_read_v1 queries in the window', 'lte', 500, 'milliseconds', 0.80),
    ('public_read_error_ratio', 'canonical_to_public_read_v1', 300, 'all public_read_v1 queries in the window', 'lte', 0.01, 'ratio', 0.80),
    ('public_reader_connection_ratio', 'public_reader_isolation', 300, 'all PostgreSQL connections', 'lte', 0.20, 'ratio', 0.80),
    ('public_reader_blocking_locks', 'public_reader_isolation', 300, 'all blocking PostgreSQL lock edges', 'lte', 0, 'locks', 1.00),
    ('public_reader_cpu_io_share', 'public_reader_isolation', 300, 'all statements sampled by pg_stat_statements', 'lte', 0.20, 'ratio', 0.80),
    ('operational_cost_per_public_unit', 'cost', 2592000, 'all published public units with measured cost in the window', 'lte', 1, 'BRL/unit', 0.80)
ON CONFLICT (metric_name) DO NOTHING;

CREATE TABLE IF NOT EXISTS public.truth_plane_sli_reviews (
    id                    BIGSERIAL PRIMARY KEY,
    observed_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    window_start          TIMESTAMPTZ NOT NULL,
    window_end            TIMESTAMPTZ NOT NULL,
    status                TEXT NOT NULL CHECK (status IN ('VALID', 'BLOCKED')),
    metrics               JSONB NOT NULL,
    metric_count          INTEGER NOT NULL CHECK (metric_count >= 0),
    unknown_count         INTEGER NOT NULL CHECK (unknown_count >= 0),
    breach_count          INTEGER NOT NULL CHECK (breach_count >= 0),
    denominator_sum       NUMERIC NOT NULL CHECK (denominator_sum >= 0),
    definition_hash       TEXT NOT NULL,
    actor                 TEXT NOT NULL,
    CHECK (status <> 'VALID' OR (unknown_count = 0 AND breach_count = 0 AND denominator_sum > 0))
);

CREATE INDEX IF NOT EXISTS idx_truth_plane_sli_valid
    ON public.truth_plane_sli_reviews (observed_at DESC, id DESC)
    WHERE status = 'VALID';

CREATE TABLE IF NOT EXISTS public.truth_plane_kill_switch (
    singleton             BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    enabled               BOOLEAN NOT NULL DEFAULT FALSE,
    reason                TEXT,
    changed_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    changed_by            TEXT NOT NULL DEFAULT 'migration'
);

INSERT INTO public.truth_plane_kill_switch (singleton, enabled, reason, changed_by)
VALUES (TRUE, FALSE, 'initial fail-closed control state', 'migration-087')
ON CONFLICT (singleton) DO NOTHING;

CREATE TABLE IF NOT EXISTS public.truth_plane_kill_switch_history (
    id                    BIGSERIAL PRIMARY KEY,
    enabled               BOOLEAN NOT NULL,
    reason                TEXT NOT NULL,
    changed_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    changed_by            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS public.truth_plane_alert_routes (
    route_name            TEXT PRIMARY KEY,
    destination           TEXT NOT NULL,
    enabled               BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.truth_plane_alert_events (
    id                    BIGSERIAL PRIMARY KEY,
    fingerprint           TEXT NOT NULL,
    metric_name           TEXT NOT NULL REFERENCES public.truth_plane_slo_definitions(metric_name),
    state                 TEXT NOT NULL CHECK (state IN ('WARNING', 'BREACH', 'UNKNOWN', 'BLOCKED')),
    route_name            TEXT REFERENCES public.truth_plane_alert_routes(route_name),
    payload               JSONB NOT NULL,
    first_seen_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    occurrence_count      INTEGER NOT NULL DEFAULT 1 CHECK (occurrence_count > 0),
    delivery_status       TEXT NOT NULL DEFAULT 'PENDING' CHECK (delivery_status IN ('PENDING', 'DELIVERED', 'FAILED', 'NO_ROUTE')),
    UNIQUE (fingerprint)
);

CREATE TABLE IF NOT EXISTS public.truth_plane_cost_observations (
    id                    BIGSERIAL PRIMARY KEY,
    observed_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source                TEXT NOT NULL,
    unit_type             TEXT NOT NULL CHECK (unit_type IN ('source', 'document', 'event', 'dossier', 'public_read')),
    unit_count            BIGINT NOT NULL CHECK (unit_count > 0),
    cost_brl              NUMERIC(18,6) NOT NULL CHECK (cost_brl >= 0),
    provenance            JSONB NOT NULL,
    run_id                TEXT
);

CREATE INDEX IF NOT EXISTS idx_truth_plane_cost_window
    ON public.truth_plane_cost_observations (observed_at, unit_type, source);

COMMIT;
