-- Migration 037: Target Universe Snapshot Tables
--
-- Creates the authoritative snapshot tables for the canonical target universe.
-- target_universe_runs tracks each seed snapshot (immutable after creation).
-- target_universe_entities stores per-entity snapshot data linked to a run.
--
-- Design:
--   - Idempotent (IF NOT EXISTS) for safe re-execution
--   - Universe run_id is used by all analytic queries to filter by snapshot
--   - Indexes on (universe_run_id, canonical_entity_key) for join performance
--   - Append-only: no UPDATE or DELETE on snapshot rows
--   - seed_sha256 enables seed-change detection at startup
--
-- References:
--   Story 1.3: Universe Authority
--   Constitution Article IV (No Invention): schema derived from seed structure
--   Plano mestre Secao 7 (P0-03)

BEGIN;

-- -----------------------------------------------------------------------
-- target_universe_runs
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS target_universe_runs (
    id              BIGSERIAL    PRIMARY KEY,
    seed_sha256     TEXT         NOT NULL,
    seed_filename   TEXT         NOT NULL,
    radius_km       NUMERIC(6,1) NOT NULL DEFAULT 200.0,
    total_rows      INTEGER      NOT NULL DEFAULT 0,
    included_rows   INTEGER      NOT NULL DEFAULT 0,
    excluded_rows   INTEGER      NOT NULL DEFAULT 0,
    unresolved_rows INTEGER      NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    git_sha         TEXT
);

-- Immutable: no UPDATE allowed after creation
COMMENT ON TABLE target_universe_runs IS
    'Immutable snapshot of a seed-based target universe run. '
    'Append-only — rows are never updated or deleted.';

COMMENT ON COLUMN target_universe_runs.seed_sha256 IS
    'SHA-256 hex digest of the seed spreadsheet at snapshot time.';
COMMENT ON COLUMN target_universe_runs.seed_filename IS
    'Original filename of the seed spreadsheet.';
COMMENT ON COLUMN target_universe_runs.radius_km IS
    'Radius in km from Florianopolis used for the snapshot.';
COMMENT ON COLUMN target_universe_runs.total_rows IS
    'Total number of seed rows (including unresolved).';
COMMENT ON COLUMN target_universe_runs.included_rows IS
    'Number of entities within the radius (included).';
COMMENT ON COLUMN target_universe_runs.excluded_rows IS
    'Number of entities outside the radius (excluded).';
COMMENT ON COLUMN target_universe_runs.unresolved_rows IS
    'Number of entities with no radius decision (unresolved).';
COMMENT ON COLUMN target_universe_runs.created_at IS
    'Timestamp when this snapshot was generated.';
COMMENT ON COLUMN target_universe_runs.git_sha IS
    'Git commit SHA at snapshot time for full reproducibility.';

CREATE INDEX IF NOT EXISTS idx_target_universe_runs_seed_sha256
    ON target_universe_runs (seed_sha256);

-- -----------------------------------------------------------------------
-- target_universe_entities
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS target_universe_entities (
    universe_run_id     BIGINT       NOT NULL,
    canonical_entity_key TEXT        NOT NULL,
    seed_row            INTEGER      NOT NULL,
    cnpj8               VARCHAR(8)   NOT NULL,
    legal_name          TEXT         NOT NULL,
    municipality        TEXT         NOT NULL,
    ibge_code           VARCHAR(7),
    legal_nature        TEXT,
    latitude            NUMERIC(10,7),
    longitude           NUMERIC(10,7),
    distance_km         NUMERIC(8,1),
    radius_decision     VARCHAR(20)  NOT NULL DEFAULT 'unresolved',
    duplicate_root      BOOLEAN      NOT NULL DEFAULT FALSE,
    db_entity_id        INTEGER,
    match_method        VARCHAR(30),

    PRIMARY KEY (universe_run_id, canonical_entity_key),

    CONSTRAINT fk_universe_run
        FOREIGN KEY (universe_run_id)
        REFERENCES target_universe_runs (id)
        ON DELETE CASCADE
);

COMMENT ON TABLE target_universe_entities IS
    'Per-entity snapshot data linked to a target_universe_runs entry. '
    'PK (universe_run_id, canonical_entity_key) enforces no-duplicate entities per run.';

COMMENT ON COLUMN target_universe_entities.universe_run_id IS
    'Foreign key to target_universe_runs.id.';
COMMENT ON COLUMN target_universe_entities.canonical_entity_key IS
    'Stable entity identity key: hex digest of (cnpj8|municipio|razao_social).';
COMMENT ON COLUMN target_universe_entities.seed_row IS
    'Row number in the original seed spreadsheet.';
COMMENT ON COLUMN target_universe_entities.cnpj8 IS
    'First 8 digits of CNPJ (root).';
COMMENT ON COLUMN target_universe_entities.radius_decision IS
    'included | excluded | unresolved';
COMMENT ON COLUMN target_universe_entities.duplicate_root IS
    'TRUE when this CNPJ-8 root appears more than once in the seed.';
COMMENT ON COLUMN target_universe_entities.db_entity_id IS
    'sc_public_entities.id matched at snapshot time (NULL if unmatched).';
COMMENT ON COLUMN target_universe_entities.match_method IS
    'Method used to match this entity to the DB (e.g. cnpj8, name).';

-- Performance indexes for analytic queries filtering by universe_run_id
CREATE INDEX IF NOT EXISTS idx_target_universe_entities_run_id
    ON target_universe_entities (universe_run_id);

CREATE INDEX IF NOT EXISTS idx_target_universe_entities_run_canonical
    ON target_universe_entities (universe_run_id, canonical_entity_key);

CREATE INDEX IF NOT EXISTS idx_target_universe_entities_run_included
    ON target_universe_entities (universe_run_id)
    WHERE radius_decision = 'included';

CREATE INDEX IF NOT EXISTS idx_target_universe_entities_cnpj8
    ON target_universe_entities (cnpj8);

COMMIT;
