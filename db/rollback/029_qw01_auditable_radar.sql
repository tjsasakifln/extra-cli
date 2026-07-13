-- QW-01 rollback. Enum values are intentionally retained because PostgreSQL
-- cannot safely remove enum labels without rebuilding the type.

BEGIN;

DROP FUNCTION IF EXISTS upsert_qw01_pncp_opportunities(JSONB);

DROP INDEX IF EXISTS uq_or_external_run_id;
DROP INDEX IF EXISTS idx_ce_canonical_entity_source;
DROP INDEX IF EXISTS uq_ce_canonical_entity_run;
DROP INDEX IF EXISTS uq_ce_legacy_entity_run;

ALTER TABLE opportunity_checkpoints
    DROP COLUMN IF EXISTS completion_reason,
    DROP COLUMN IF EXISTS scope_complete,
    DROP COLUMN IF EXISTS pages_expected,
    DROP COLUMN IF EXISTS external_run_id;

ALTER TABLE opportunity_runs
    DROP COLUMN IF EXISTS error_code,
    DROP COLUMN IF EXISTS completion_reason,
    DROP COLUMN IF EXISTS scope_complete,
    DROP COLUMN IF EXISTS records_expected,
    DROP COLUMN IF EXISTS period_end,
    DROP COLUMN IF EXISTS period_start,
    DROP COLUMN IF EXISTS source_strategy,
    DROP COLUMN IF EXISTS external_run_id;

ALTER TABLE coverage_evidence DROP CONSTRAINT IF EXISTS ck_ce_success_zero_scope;
ALTER TABLE coverage_evidence DROP CONSTRAINT IF EXISTS ck_ce_freshness_status;
ALTER TABLE coverage_evidence DROP CONSTRAINT IF EXISTS ck_ce_applicability;

ALTER TABLE coverage_evidence
    DROP COLUMN IF EXISTS evidence_metadata,
    DROP COLUMN IF EXISTS freshness_status,
    DROP COLUMN IF EXISTS open_records,
    DROP COLUMN IF EXISTS records_fetched,
    DROP COLUMN IF EXISTS pages_processed,
    DROP COLUMN IF EXISTS pages_expected,
    DROP COLUMN IF EXISTS checked_at,
    DROP COLUMN IF EXISTS scope_key,
    DROP COLUMN IF EXISTS applicability,
    DROP COLUMN IF EXISTS canonical_entity_key;

CREATE UNIQUE INDEX IF NOT EXISTS uq_ce_entity_run
    ON coverage_evidence (entity_id, source, data_type, run_id)
    WHERE entity_id IS NOT NULL;

COMMIT;
