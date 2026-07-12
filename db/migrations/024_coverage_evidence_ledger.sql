-- Migration 024: Coverage Evidence Ledger
-- Canonical entity/source evidence table for auditable coverage truth.
-- Each row records one observation: an entity checked against a source
-- during a specific run, with exactly one machine-readable state.
--
-- Design constraints:
--   - Idempotent: all CREATE use IF NOT EXISTS.
--   - Never converts an exception into an empty success.
--   - One state per row — no NULL state after insert.

BEGIN;

-- ---------------------------------------------------------------------------
-- Evidence state enum
-- ---------------------------------------------------------------------------

DO $$ BEGIN
    CREATE TYPE evidence_state AS ENUM (
        'success_with_data',   -- Source returned data for this entity
        'success_zero',        -- Source checked, confirmed zero records (legitimate empty)
        'partial',             -- Source returned partial data (incomplete run)
        'connection_failed',   -- Network/DNS/TCP-level failure
        'auth_failed',         -- Credentials rejected or expired
        'parse_failed',        -- Response received but could not be parsed
        'transform_failed',    -- Parsed OK but transform step failed
        'persist_failed',      -- Transformed OK but DB persist failed
        'not_applicable',      -- Source does not apply to this entity type
        'not_investigated'     -- Source exists but has never been checked for this entity
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- ---------------------------------------------------------------------------
-- Evidence ledger table
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS coverage_evidence (
    id              BIGSERIAL PRIMARY KEY,
    entity_id       INT,                          -- NULL = source-level aggregate record
    source          TEXT NOT NULL,
    data_type       TEXT NOT NULL DEFAULT 'bids',
    -- queried_period: when the source was asked about
    queried_start   DATE,
    queried_end     DATE,
    -- Run identity
    run_id          TEXT NOT NULL,
    -- Timestamps
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Counts
    count_obtained     INT NOT NULL DEFAULT 0,
    count_transformed  INT NOT NULL DEFAULT 0,
    count_persisted    INT NOT NULL DEFAULT 0,
    -- State machine
    state           evidence_state NOT NULL DEFAULT 'not_investigated',
    -- Error context (populated when state indicates failure)
    error_message   TEXT,
    error_code      TEXT,
    -- Arbitrary metadata
    metadata        JSONB DEFAULT '{}'::jsonb,

    -- One evidence row per entity+source+data_type+run_id
    UNIQUE (entity_id, source, data_type, run_id)
);

-- ---------------------------------------------------------------------------
-- Indexes for metric queries
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_ce_state
    ON coverage_evidence (state);

CREATE INDEX IF NOT EXISTS idx_ce_entity_source
    ON coverage_evidence (entity_id, source);

CREATE INDEX IF NOT EXISTS idx_ce_run
    ON coverage_evidence (run_id);

CREATE INDEX IF NOT EXISTS idx_ce_completed
    ON coverage_evidence (completed_at);

CREATE INDEX IF NOT EXISTS idx_ce_source_state
    ON coverage_evidence (source, state);

-- ---------------------------------------------------------------------------
-- Helper: get latest evidence state per (entity, source) combination
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_latest_evidence AS
SELECT DISTINCT ON (entity_id, source, data_type)
    id,
    entity_id,
    source,
    data_type,
    queried_start,
    queried_end,
    run_id,
    started_at,
    completed_at,
    count_obtained,
    count_transformed,
    count_persisted,
    state,
    error_message,
    error_code
FROM coverage_evidence
ORDER BY entity_id, source, data_type, completed_at DESC;

-- ---------------------------------------------------------------------------
-- Helper: source health summary
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_source_health AS
SELECT
    source,
    COUNT(*) AS total_evidence_rows,
    COUNT(*) FILTER (WHERE state = 'success_with_data') AS success_with_data,
    COUNT(*) FILTER (WHERE state = 'success_zero') AS success_zero,
    COUNT(*) FILTER (WHERE state = 'partial') AS partial,
    COUNT(*) FILTER (WHERE state = 'connection_failed') AS connection_failed,
    COUNT(*) FILTER (WHERE state = 'auth_failed') AS auth_failed,
    COUNT(*) FILTER (WHERE state = 'parse_failed') AS parse_failed,
    COUNT(*) FILTER (WHERE state = 'transform_failed') AS transform_failed,
    COUNT(*) FILTER (WHERE state = 'persist_failed') AS persist_failed,
    COUNT(*) FILTER (WHERE state = 'not_applicable') AS not_applicable,
    COUNT(*) FILTER (WHERE state = 'not_investigated') AS not_investigated,
    MAX(completed_at) AS last_check_at
FROM v_latest_evidence
GROUP BY source
ORDER BY source;

COMMIT;
