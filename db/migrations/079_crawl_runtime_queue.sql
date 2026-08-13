-- 079_crawl_runtime_queue.sql
-- #246/#268/#269: durable entity x source queue, recurring schedule and attempts.

BEGIN;

CREATE TABLE IF NOT EXISTS crawl_entity_source_schedule (
    canonical_entity_key   TEXT NOT NULL,
    entity_id              INTEGER NOT NULL REFERENCES sc_public_entities(id) ON DELETE CASCADE,
    source                 TEXT NOT NULL,
    capability             TEXT NOT NULL,
    applicability          TEXT NOT NULL CHECK (applicability IN (
        'APPLICABLE', 'NOT_APPLICABLE', 'BLOCKED', 'FAILED'
    )),
    applicability_reason   TEXT NOT NULL,
    policy_version         TEXT NOT NULL,
    binding_version        TEXT NOT NULL,
    canonical_url          TEXT,
    domain_key             TEXT NOT NULL,
    last_run_at            TIMESTAMPTZ,
    last_success_at        TIMESTAMPTZ,
    last_outcome           TEXT,
    next_run_at            TIMESTAMPTZ NOT NULL,
    freshness_deadline     TIMESTAMPTZ NOT NULL,
    consecutive_failures   INTEGER NOT NULL DEFAULT 0 CHECK (consecutive_failures >= 0),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (canonical_entity_key, source, capability)
);

CREATE TABLE IF NOT EXISTS crawl_jobs (
    id                       BIGSERIAL PRIMARY KEY,
    canonical_entity_key     TEXT NOT NULL,
    entity_id                INTEGER NOT NULL REFERENCES sc_public_entities(id) ON DELETE CASCADE,
    source                   TEXT NOT NULL,
    capability               TEXT NOT NULL,
    domain_key               TEXT NOT NULL,
    binding_version          TEXT NOT NULL,
    window_start             TIMESTAMPTZ NOT NULL,
    window_end               TIMESTAMPTZ NOT NULL,
    status                   TEXT NOT NULL DEFAULT 'queued' CHECK (status IN (
        'queued', 'running', 'succeeded', 'failed', 'blocked', 'cancelled'
    )),
    priority                 INTEGER NOT NULL DEFAULT 0,
    cursor                   JSONB NOT NULL DEFAULT '{}'::jsonb,
    freshness_deadline       TIMESTAMPTZ NOT NULL,
    next_run_at              TIMESTAMPTZ NOT NULL,
    lease_owner              TEXT,
    lease_expires_at         TIMESTAMPTZ,
    heartbeat_at             TIMESTAMPTZ,
    attempt_count            INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    max_attempts             INTEGER NOT NULL DEFAULT 5 CHECK (max_attempts >= 1),
    domain_concurrency_limit INTEGER NOT NULL DEFAULT 1 CHECK (domain_concurrency_limit BETWEEN 1 AND 32),
    idempotency_key          TEXT NOT NULL UNIQUE,
    last_outcome             TEXT,
    last_error_class         TEXT,
    last_error               TEXT,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (window_end >= window_start),
    CHECK (
        (status = 'running' AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)
        OR status <> 'running'
    ),
    UNIQUE (canonical_entity_key, source, capability, window_start, window_end, idempotency_key)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_crawl_jobs_active_pair
    ON crawl_jobs (canonical_entity_key, source, capability)
    WHERE status IN ('queued', 'running');

CREATE INDEX IF NOT EXISTS idx_crawl_jobs_admission
    ON crawl_jobs (priority DESC, next_run_at, id)
    WHERE status = 'queued';

CREATE INDEX IF NOT EXISTS idx_crawl_jobs_expired_lease
    ON crawl_jobs (lease_expires_at)
    WHERE status = 'running';

CREATE TABLE IF NOT EXISTS crawl_job_attempts (
    id                 BIGSERIAL PRIMARY KEY,
    job_id             BIGINT NOT NULL REFERENCES crawl_jobs(id) ON DELETE CASCADE,
    run_id             TEXT NOT NULL UNIQUE,
    worker_id          TEXT NOT NULL,
    status             TEXT NOT NULL CHECK (status IN (
        'running', 'succeeded', 'failed', 'blocked', 'interrupted', 'lease_expired'
    )),
    started_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    heartbeat_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at        TIMESTAMPTZ,
    lease_expires_at   TIMESTAMPTZ NOT NULL,
    cursor             JSONB NOT NULL DEFAULT '{}'::jsonb,
    metrics            JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_class        TEXT,
    error_message      TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK ((status = 'running' AND finished_at IS NULL) OR status <> 'running')
);

CREATE INDEX IF NOT EXISTS idx_crawl_attempts_job_started
    ON crawl_job_attempts (job_id, started_at DESC);

COMMIT;
