-- 093_contact_discovery_batch.sql
-- Additive durable job bus for CONFENGE_CONTACT_DISCOVERY.
-- Does not reuse crawl_jobs (FK to sc_public_entities). Same lease/SKIP LOCKED vocabulary.

BEGIN;

CREATE TABLE IF NOT EXISTS contact_discovery_cohorts (
    cohort_id                 TEXT PRIMARY KEY,
    job_type                  TEXT NOT NULL DEFAULT 'CONFENGE_CONTACT_DISCOVERY',
    service                   TEXT NOT NULL,
    offer_context             TEXT,
    discovery_policy_version  TEXT NOT NULL,
    search_backend            TEXT NOT NULL,
    budget_version            TEXT NOT NULL,
    code_sha                  TEXT NOT NULL,
    input_evidence_version    TEXT NOT NULL,
    status                    TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN (
        'OPEN', 'CLOSED', 'PUBLISHED', 'CANCELLED'
    )),
    denominator               INTEGER NOT NULL DEFAULT 0 CHECK (denominator >= 0),
    snapshot_id               TEXT,
    snapshot_pointer          TEXT,
    snapshot_hash             TEXT,
    published_at              TIMESTAMPTZ,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata                  JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS contact_discovery_jobs (
    id                          BIGSERIAL PRIMARY KEY,
    job_type                    TEXT NOT NULL DEFAULT 'CONFENGE_CONTACT_DISCOVERY',
    cohort_id                   TEXT NOT NULL REFERENCES contact_discovery_cohorts(cohort_id) ON DELETE CASCADE,
    canonical_account_id        TEXT NOT NULL,
    service                     TEXT NOT NULL,
    offer_context               TEXT,
    discovery_policy_version    TEXT NOT NULL,
    search_backend              TEXT NOT NULL,
    budget_version              TEXT NOT NULL,
    code_sha                    TEXT NOT NULL,
    input_evidence_version      TEXT NOT NULL,
    idempotency_key             TEXT NOT NULL UNIQUE,
    revision                    INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    status                      TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN (
        'PENDING', 'RUNNING', 'SUCCEEDED', 'BLOCKED', 'RETRYABLE', 'DLQ', 'CANCELLED'
    )),
    priority                    INTEGER NOT NULL DEFAULT 0,
    domain_key                  TEXT NOT NULL,
    backend_key                 TEXT NOT NULL,
    cursor                      JSONB NOT NULL DEFAULT '{}'::jsonb,
    lease_owner                 TEXT,
    lease_expires_at            TIMESTAMPTZ,
    heartbeat_at                TIMESTAMPTZ,
    attempt_count               INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    max_attempts                INTEGER NOT NULL DEFAULT 5 CHECK (max_attempts >= 1),
    backend_concurrency_limit   INTEGER NOT NULL DEFAULT 2 CHECK (backend_concurrency_limit BETWEEN 1 AND 32),
    domain_concurrency_limit    INTEGER NOT NULL DEFAULT 1 CHECK (domain_concurrency_limit BETWEEN 1 AND 32),
    cancel_requested            BOOLEAN NOT NULL DEFAULT FALSE,
    last_outcome                TEXT,
    last_reason_code            TEXT,
    last_error                  TEXT,
    output_pointer              TEXT,
    output_hash                 TEXT,
    cost_metrics                JSONB NOT NULL DEFAULT '{}'::jsonb,
    next_run_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (
        (status = 'RUNNING' AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)
        OR status <> 'RUNNING'
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_contact_discovery_jobs_active_identity
    ON contact_discovery_jobs (
        canonical_account_id,
        discovery_policy_version,
        input_evidence_version,
        search_backend,
        budget_version,
        service
    )
    WHERE status IN ('PENDING', 'RUNNING', 'RETRYABLE');

CREATE INDEX IF NOT EXISTS idx_contact_discovery_jobs_admission
    ON contact_discovery_jobs (priority DESC, next_run_at, id)
    WHERE status IN ('PENDING', 'RETRYABLE');

CREATE INDEX IF NOT EXISTS idx_contact_discovery_jobs_expired_lease
    ON contact_discovery_jobs (lease_expires_at)
    WHERE status = 'RUNNING';

CREATE INDEX IF NOT EXISTS idx_contact_discovery_jobs_cohort_status
    ON contact_discovery_jobs (cohort_id, status);

CREATE TABLE IF NOT EXISTS contact_discovery_attempts (
    id                  BIGSERIAL PRIMARY KEY,
    job_id              BIGINT NOT NULL REFERENCES contact_discovery_jobs(id) ON DELETE CASCADE,
    run_id              TEXT NOT NULL UNIQUE,
    worker_id           TEXT NOT NULL,
    status              TEXT NOT NULL CHECK (status IN (
        'RUNNING', 'SUCCEEDED', 'BLOCKED', 'RETRYABLE', 'DLQ',
        'INTERRUPTED', 'LEASE_EXPIRED', 'CANCELLED'
    )),
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    heartbeat_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at         TIMESTAMPTZ,
    lease_expires_at    TIMESTAMPTZ NOT NULL,
    cursor              JSONB NOT NULL DEFAULT '{}'::jsonb,
    metrics             JSONB NOT NULL DEFAULT '{}'::jsonb,
    reason_code         TEXT,
    error_message       TEXT,
    output_pointer      TEXT,
    output_hash         TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (
        (status = 'RUNNING' AND finished_at IS NULL)
        OR (status <> 'RUNNING' AND finished_at IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_contact_discovery_attempts_job
    ON contact_discovery_attempts (job_id, started_at DESC);

CREATE TABLE IF NOT EXISTS contact_discovery_snapshots (
    snapshot_id         TEXT PRIMARY KEY,
    cohort_id           TEXT NOT NULL REFERENCES contact_discovery_cohorts(cohort_id) ON DELETE CASCADE,
    approved            BOOLEAN NOT NULL DEFAULT FALSE,
    pointer             TEXT NOT NULL,
    content_hash        TEXT NOT NULL,
    denominator         INTEGER NOT NULL,
    status_counts       JSONB NOT NULL DEFAULT '{}'::jsonb,
    policy_version      TEXT NOT NULL,
    code_sha            TEXT NOT NULL,
    search_backend      TEXT NOT NULL,
    budget_version      TEXT NOT NULL,
    reject_reason       TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_contact_discovery_snapshots_cohort
    ON contact_discovery_snapshots (cohort_id, created_at DESC);

CREATE TABLE IF NOT EXISTS contact_discovery_kill_switch (
    singleton     BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    enabled       BOOLEAN NOT NULL DEFAULT FALSE,
    reason        TEXT NOT NULL DEFAULT '',
    changed_by    TEXT NOT NULL DEFAULT '',
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO contact_discovery_kill_switch (singleton, enabled, reason, changed_by)
VALUES (TRUE, FALSE, '', 'migration-093')
ON CONFLICT (singleton) DO NOTHING;

CREATE TABLE IF NOT EXISTS contact_discovery_backend_circuit (
    backend_key             TEXT PRIMARY KEY,
    state                   TEXT NOT NULL DEFAULT 'closed' CHECK (state IN ('closed', 'open', 'half_open')),
    consecutive_failures    INTEGER NOT NULL DEFAULT 0 CHECK (consecutive_failures >= 0),
    opened_at               TIMESTAMPTZ,
    cooldown_until          TIMESTAMPTZ,
    last_error_class        TEXT,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;
