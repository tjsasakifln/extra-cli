-- 096_national_claims_gate.sql
-- Additive persistence for the unique national-claims arbiter (#302 / #350).
-- 096 was free on origin/main@820c83b8 after fetch. Reserved for this issue only.
-- Companion feature branches may also have attempted 096; this file is the
-- inbound claims gate and must not be reused for unrelated schemas.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

CREATE TABLE IF NOT EXISTS public.national_claims_universe (
    universe_id            TEXT PRIMARY KEY,
    universe_kind          TEXT NOT NULL CHECK (
        universe_kind IN (
            'national',
            'icp_commercial',
            'extra_1093_monitored',
            'observed_corpus'
        )
    ),
    official_source        TEXT NOT NULL,
    cutoff                 TEXT NOT NULL,
    competence             TEXT NOT NULL,
    catalog_hash           TEXT NOT NULL,
    method_version         TEXT NOT NULL,
    org_count              INTEGER NOT NULL CHECK (org_count >= 0),
    unit_count             INTEGER NOT NULL CHECK (unit_count >= 0),
    expected_partitions    INTEGER NOT NULL CHECK (expected_partitions >= 0),
    inclusion_rules        JSONB NOT NULL,
    exclusion_rules        JSONB NOT NULL,
    change_log             JSONB NOT NULL DEFAULT '[]'::jsonb,
    owner                  TEXT NOT NULL,
    review_cadence         TEXT NOT NULL,
    payload                JSONB NOT NULL,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS national_claims_universe_kind_hash_uidx
    ON public.national_claims_universe (universe_kind, official_source, competence, catalog_hash);

CREATE TABLE IF NOT EXISTS public.national_claims_partition (
    id                     BIGSERIAL PRIMARY KEY,
    national_universe_id   TEXT NOT NULL REFERENCES public.national_claims_universe (universe_id),
    claim_id               TEXT NOT NULL,
    partition_id           TEXT NOT NULL,
    expected               BOOLEAN NOT NULL,
    attempted              BOOLEAN NOT NULL,
    status                 TEXT NOT NULL CHECK (
        status IN (
            'FOUND',
            'ZERO_CONFIRMED',
            'BLOCKED',
            'FAILED',
            'NOT_APPLICABLE',
            'UNKNOWN'
        )
    ),
    pages_fetched          INTEGER,
    pages_expected         INTEGER,
    records                INTEGER,
    pagination_complete    BOOLEAN NOT NULL DEFAULT FALSE,
    request_complete       BOOLEAN NOT NULL DEFAULT FALSE,
    raw_ref                TEXT,
    evidence_ref           TEXT,
    checked_at             TEXT,
    as_of                  TEXT,
    freshness_status       TEXT,
    identity_mapped        BOOLEAN NOT NULL DEFAULT FALSE,
    reason                 TEXT,
    next_action            TEXT,
    recorded_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS national_claims_partition_claim_idx
    ON public.national_claims_partition (claim_id, partition_id, recorded_at DESC);

CREATE TABLE IF NOT EXISTS public.national_claims_aggregate_evidence (
    id                     BIGSERIAL PRIMARY KEY,
    claim_id               TEXT NOT NULL,
    source                 TEXT NOT NULL,
    data_type              TEXT,
    state                  TEXT,
    count_obtained         INTEGER,
    count_persisted        INTEGER,
    metadata               JSONB NOT NULL DEFAULT '{}'::jsonb,
    identity_class         TEXT NOT NULL CHECK (
        identity_class IN ('SOURCE_WIDE_AGGREGATE', 'UNMAPPABLE')
    ),
    reason_code            TEXT NOT NULL,
    raw_ref                TEXT,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS national_claims_aggregate_evidence_claim_idx
    ON public.national_claims_aggregate_evidence (claim_id);

CREATE TABLE IF NOT EXISTS public.national_claims_identity_evidence (
    id                     BIGSERIAL PRIMARY KEY,
    claim_id               TEXT NOT NULL,
    entity_id              TEXT NOT NULL,
    canonical_entity_key   TEXT,
    source                 TEXT NOT NULL,
    identity_class         TEXT NOT NULL CHECK (identity_class = 'IDENTITY_MAPPED'),
    partition_id           TEXT,
    evidence_ref           TEXT,
    metadata               JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS national_claims_identity_evidence_claim_idx
    ON public.national_claims_identity_evidence (claim_id);

CREATE TABLE IF NOT EXISTS public.national_claims_decision (
    claim_id               TEXT PRIMARY KEY,
    scope                  TEXT NOT NULL,
    national_universe_id   TEXT REFERENCES public.national_claims_universe (universe_id),
    catalog_hash           TEXT,
    authorization_state    TEXT NOT NULL CHECK (
        authorization_state IN (
            'AUTHORIZED',
            'AUTHORIZED_WITH_LIMITATIONS',
            'NEEDS_DATA',
            'STALE',
            'BLOCKED',
            'FAILED'
        )
    ),
    nacional_completo      BOOLEAN NOT NULL DEFAULT FALSE,
    consumer_view          TEXT NOT NULL CHECK (consumer_view IN ('current', 'lkg', 'blocked')),
    numerator              INTEGER NOT NULL CHECK (numerator >= 0),
    denominator            INTEGER NOT NULL CHECK (denominator >= 0),
    coverage_pct           NUMERIC,
    missingness_pct        NUMERIC,
    partitions_expected    INTEGER NOT NULL,
    partitions_closed      INTEGER NOT NULL,
    freshness_status       TEXT,
    as_of                  TEXT,
    source_version         TEXT,
    method_version         TEXT,
    policy_version         TEXT NOT NULL,
    limitations            TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    reason_codes           TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    lkg_claim_id           TEXT,
    invalidation_triggers  JSONB NOT NULL DEFAULT '[]'::jsonb,
    producer_sha           TEXT,
    content_hash           TEXT NOT NULL,
    payload                JSONB NOT NULL,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.national_claims_lkg (
    id                     BIGSERIAL PRIMARY KEY,
    national_universe_id   TEXT NOT NULL,
    claim_id               TEXT NOT NULL REFERENCES public.national_claims_decision (claim_id),
    authorized_at          TEXT NOT NULL,
    expires_at             TEXT NOT NULL,
    invalidated_at         TEXT,
    invalidation_reason    TEXT,
    catalog_hash           TEXT NOT NULL,
    method_version         TEXT NOT NULL,
    source_version         TEXT NOT NULL,
    content_hash           TEXT NOT NULL,
    UNIQUE (national_universe_id, claim_id)
);

COMMENT ON TABLE public.national_claims_aggregate_evidence IS
    '#350 source-wide/unmappable evidence. Never a dual-coverage numerator.';
COMMENT ON TABLE public.national_claims_universe IS
    'Four-kind versioned universes. Only kind=national may authorize a national claim.';
COMMENT ON TABLE public.national_claims_lkg IS
    'Last-known-good after AUTHORIZED. Invalidation stamps; rows are never deleted.';

COMMIT;
