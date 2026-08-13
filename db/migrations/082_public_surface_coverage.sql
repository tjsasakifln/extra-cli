-- 082_public_surface_coverage.sql
-- #235/#236: versioned discovery and continuous entity/source coverage authority.

BEGIN;

CREATE TABLE IF NOT EXISTS discovery_runs (
    id                    BIGSERIAL PRIMARY KEY,
    universe_run_id       BIGINT NOT NULL REFERENCES target_universe_runs(id) ON DELETE RESTRICT,
    mode                  TEXT NOT NULL CHECK (mode IN ('stratified_pilot', 'full')),
    expected_entity_count INTEGER NOT NULL CHECK (expected_entity_count > 0),
    observed_entity_count INTEGER NOT NULL DEFAULT 0 CHECK (observed_entity_count >= 0),
    canonical_ids_sha256  TEXT CHECK (canonical_ids_sha256 IS NULL OR canonical_ids_sha256 ~ '^[0-9a-f]{64}$'),
    audited               BOOLEAN NOT NULL DEFAULT FALSE,
    outcome               TEXT CHECK (outcome IN ('complete', 'partial', 'aborted')),
    started_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at          TIMESTAMPTZ,
    CHECK ((completed_at IS NULL) = (outcome IS NULL)),
    CHECK (outcome <> 'complete' OR observed_entity_count = expected_entity_count),
    CHECK (outcome = 'complete' OR NOT audited)
);

CREATE TABLE IF NOT EXISTS entity_discovery_results (
    discovery_run_id      BIGINT NOT NULL REFERENCES discovery_runs(id) ON DELETE CASCADE,
    universe_run_id       BIGINT NOT NULL,
    canonical_entity_key  TEXT NOT NULL,
    entity_id             INTEGER NOT NULL REFERENCES sc_public_entities(id) ON DELETE RESTRICT,
    status                TEXT NOT NULL CHECK (status IN (
        'FOUND', 'UNCLASSIFIED', 'BLOCKED',
        'DISCOVERY_EXHAUSTED_NO_SURFACE', 'FAILED'
    )),
    method                TEXT NOT NULL,
    checked_at            TIMESTAMPTZ NOT NULL,
    observed_timezone     TEXT NOT NULL DEFAULT 'America/Sao_Paulo',
    next_check_at         TIMESTAMPTZ NOT NULL,
    notes                 TEXT,
    PRIMARY KEY (discovery_run_id, canonical_entity_key),
    FOREIGN KEY (universe_run_id, canonical_entity_key)
        REFERENCES target_universe_entities(universe_run_id, canonical_entity_key)
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS public_surface_observations (
    id                    BIGSERIAL PRIMARY KEY,
    discovery_run_id      BIGINT NOT NULL REFERENCES discovery_runs(id) ON DELETE RESTRICT,
    universe_run_id       BIGINT NOT NULL,
    canonical_entity_key  TEXT NOT NULL,
    entity_id             INTEGER NOT NULL REFERENCES sc_public_entities(id) ON DELETE RESTRICT,
    surface_kind          TEXT NOT NULL CHECK (surface_kind IN (
        'institutional', 'procurement', 'transparency', 'gazette', 'cited_platform'
    )),
    version_no            INTEGER NOT NULL CHECK (version_no >= 1),
    status                TEXT NOT NULL CHECK (status IN (
        'FOUND', 'UNCLASSIFIED', 'BLOCKED',
        'DISCOVERY_EXHAUSTED_NO_SURFACE', 'FAILED'
    )),
    canonical_url         TEXT,
    domain                TEXT,
    platform              TEXT,
    anchor_url            TEXT,
    discovery_method      TEXT NOT NULL,
    http_status           INTEGER CHECK (http_status IS NULL OR http_status BETWEEN 100 AND 599),
    redirect_chain        JSONB NOT NULL DEFAULT '[]'::jsonb,
    last_checked_at       TIMESTAMPTZ NOT NULL,
    observed_timezone     TEXT NOT NULL DEFAULT 'America/Sao_Paulo',
    next_check_at         TIMESTAMPTZ NOT NULL,
    is_current            BOOLEAN NOT NULL DEFAULT TRUE,
    invalidated_at        TIMESTAMPTZ,
    invalidation_reason   TEXT,
    evidence              JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (universe_run_id, canonical_entity_key)
        REFERENCES target_universe_entities(universe_run_id, canonical_entity_key)
        ON DELETE RESTRICT,
    UNIQUE (universe_run_id, canonical_entity_key, surface_kind, version_no),
    CHECK ((is_current AND invalidated_at IS NULL) OR NOT is_current)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_public_surface_current
    ON public_surface_observations (universe_run_id, canonical_entity_key, surface_kind)
    WHERE is_current;

CREATE TABLE IF NOT EXISTS entity_source_coverage_attempts (
    id                    BIGSERIAL PRIMARY KEY,
    universe_run_id       BIGINT NOT NULL,
    canonical_entity_key  TEXT NOT NULL,
    entity_id             INTEGER NOT NULL REFERENCES sc_public_entities(id) ON DELETE RESTRICT,
    source                TEXT NOT NULL,
    capability            TEXT NOT NULL,
    status                TEXT NOT NULL CHECK (status IN (
        'FOUND', 'ZERO_CONFIRMED', 'NOT_APPLICABLE', 'BLOCKED',
        'FAILED', 'DISCOVERY_EXHAUSTED_NO_SURFACE'
    )),
    applicability         BOOLEAN NOT NULL,
    applicability_reason  TEXT NOT NULL,
    canonical_url         TEXT,
    checked_at            TIMESTAMPTZ NOT NULL,
    http_statuses         INTEGER[] NOT NULL DEFAULT '{}',
    pages_fetched         INTEGER NOT NULL DEFAULT 0 CHECK (pages_fetched >= 0),
    pages_expected        INTEGER CHECK (pages_expected IS NULL OR pages_expected >= 0),
    records_observed      INTEGER NOT NULL DEFAULT 0 CHECK (records_observed >= 0),
    request_completed     BOOLEAN NOT NULL DEFAULT FALSE,
    scope_complete        BOOLEAN NOT NULL DEFAULT FALSE,
    pagination_reconciled BOOLEAN NOT NULL DEFAULT FALSE,
    raw_uri               TEXT,
    raw_sha256            TEXT CHECK (raw_sha256 IS NULL OR raw_sha256 ~ '^[0-9a-f]{64}$'),
    freshness_deadline    TIMESTAMPTZ NOT NULL,
    next_action           TEXT NOT NULL,
    next_check_at         TIMESTAMPTZ NOT NULL,
    run_id                TEXT,
    crawl_job_attempt_id  BIGINT REFERENCES crawl_job_attempts(id) ON DELETE SET NULL,
    evidence              JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (universe_run_id, canonical_entity_key)
        REFERENCES target_universe_entities(universe_run_id, canonical_entity_key)
        ON DELETE RESTRICT,
    CHECK (
        status <> 'ZERO_CONFIRMED'
        OR (
            request_completed AND scope_complete AND pagination_reconciled
            AND records_observed = 0 AND raw_uri IS NOT NULL AND raw_sha256 IS NOT NULL
        )
    )
);

CREATE TABLE IF NOT EXISTS entity_source_coverage_current (
    universe_run_id       BIGINT NOT NULL,
    canonical_entity_key  TEXT NOT NULL,
    entity_id             INTEGER NOT NULL REFERENCES sc_public_entities(id) ON DELETE RESTRICT,
    source                TEXT NOT NULL,
    capability            TEXT NOT NULL,
    latest_attempt_id     BIGINT NOT NULL REFERENCES entity_source_coverage_attempts(id) ON DELETE RESTRICT,
    status                TEXT NOT NULL CHECK (status IN (
        'FOUND', 'ZERO_CONFIRMED', 'NOT_APPLICABLE', 'BLOCKED',
        'FAILED', 'DISCOVERY_EXHAUSTED_NO_SURFACE'
    )),
    applicability         BOOLEAN NOT NULL,
    applicability_reason  TEXT NOT NULL,
    canonical_url         TEXT,
    checked_at            TIMESTAMPTZ NOT NULL,
    freshness_deadline    TIMESTAMPTZ NOT NULL,
    next_action           TEXT NOT NULL,
    next_check_at         TIMESTAMPTZ NOT NULL,
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (universe_run_id, canonical_entity_key, source, capability),
    FOREIGN KEY (universe_run_id, canonical_entity_key)
        REFERENCES target_universe_entities(universe_run_id, canonical_entity_key)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_surface_entity_current
    ON public_surface_observations (entity_id, surface_kind) WHERE is_current;
CREATE INDEX IF NOT EXISTS idx_coverage_current_state
    ON entity_source_coverage_current (status, next_check_at);
CREATE INDEX IF NOT EXISTS idx_coverage_attempt_entity_source
    ON entity_source_coverage_attempts (entity_id, source, capability, checked_at DESC);

COMMIT;
