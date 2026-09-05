-- 107_contact_discovery_cohort_scoped_identity.sql
-- Keep retry idempotency inside one cohort; never let an old cohort block a new one.
-- Existing rows and cohort ownership remain untouched.

BEGIN;

-- Build the replacement before removing the old constraint. If this create
-- fails, the pre-upgrade active identity constraint stays in force.
SET lock_timeout = '5s';
SET statement_timeout = '60s';

CREATE UNIQUE INDEX IF NOT EXISTS uq_contact_discovery_jobs_active_identity_v2
    ON contact_discovery_jobs (
        cohort_id,
        canonical_account_id,
        discovery_policy_version,
        input_evidence_version,
        search_backend,
        budget_version,
        service
    )
    WHERE status IN ('PENDING', 'RUNNING', 'RETRYABLE');

DROP INDEX IF EXISTS uq_contact_discovery_jobs_active_identity;

RESET lock_timeout;
RESET statement_timeout;

COMMIT;
