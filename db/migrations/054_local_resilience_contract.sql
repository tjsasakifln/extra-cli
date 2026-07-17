-- 054_local_resilience_contract.sql
-- Additive projection support for ADR-021 local resilience. Filesystem
-- checkpoints remain the pre-VPS source of truth; these columns let a future
-- VPS project the same contract into PostgreSQL without semantic loss.

BEGIN;

ALTER TABLE IF EXISTS dlq_entries
    ADD COLUMN IF NOT EXISTS payload_hash TEXT,
    ADD COLUMN IF NOT EXISTS error_kind TEXT NOT NULL DEFAULT 'record';

CREATE UNIQUE INDEX IF NOT EXISTS uq_dlq_pending_payload
    ON dlq_entries (source, payload_hash, COALESCE(error_code, ''))
    WHERE status = 'pending' AND payload_hash IS NOT NULL;

ALTER TABLE IF EXISTS coverage_evidence
    ADD COLUMN IF NOT EXISTS request_scope TEXT,
    ADD COLUMN IF NOT EXISTS pages_fetched INT,
    ADD COLUMN IF NOT EXISTS pages_expected INT,
    ADD COLUMN IF NOT EXISTS provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS satisfactory BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE IF EXISTS coverage_evidence
    DROP CONSTRAINT IF EXISTS ck_coverage_evidence_satisfactory;

ALTER TABLE IF EXISTS coverage_evidence
    ADD CONSTRAINT ck_coverage_evidence_satisfactory CHECK (
        satisfactory = FALSE OR (
            state IN ('success_with_data', 'success_zero')
            AND request_scope IS NOT NULL
            AND provenance <> '{}'::jsonb
            AND (pages_expected IS NULL OR pages_fetched >= pages_expected)
            AND error_code IS NULL
        )
    );

COMMIT;
