-- 097_national_coverage.sql
-- Additive persist for the national coverage denominator (campaign
-- CONFENGE-EXTRA-SEO-NATIONAL-COVERAGE-AUTHORITY-01 / extra-cli#302 residual).
-- Dedicated national_coverage_* objects. Does not alter national_claims_* (096)
-- and does not reuse extra-005 official_universe if that branch lands later.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

CREATE TABLE IF NOT EXISTS public.national_coverage_universe (
    universe_id            TEXT PRIMARY KEY,
    universe_kind          TEXT NOT NULL CHECK (universe_kind IN ('OFFICIAL', 'OBSERVED_CORPUS')),
    official_source        TEXT NOT NULL,
    official_source_url    TEXT,
    competence             TEXT NOT NULL,
    cutoff                 TEXT NOT NULL,
    as_of                  TEXT NOT NULL,
    raw_hash               TEXT NOT NULL,
    catalog_hash           TEXT NOT NULL,
    method_version         TEXT NOT NULL,
    schema_version         TEXT NOT NULL,
    grain                  TEXT NOT NULL,
    expected_partitions    INTEGER NOT NULL CHECK (expected_partitions >= 0),
    expected_units         INTEGER NOT NULL CHECK (expected_units >= 0),
    official_status        TEXT NOT NULL CHECK (official_status IN ('AVAILABLE', 'BLOCKED')),
    official_block_cause   TEXT,
    inclusion_rules        JSONB NOT NULL,
    exclusion_rules        JSONB NOT NULL,
    owner                  TEXT NOT NULL,
    next_refresh           TEXT NOT NULL,
    payload                JSONB NOT NULL,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT national_coverage_universe_not_extra_1093 CHECK (
        official_source NOT IN (
            'extra_1093',
            'extra-1093',
            'extra_1093_monitored',
            'extra-canonical-seed',
            'sc_public_entities.raio_200km'
        )
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS national_coverage_universe_kind_hash_uidx
    ON public.national_coverage_universe (universe_kind, official_source, competence, catalog_hash);

CREATE TABLE IF NOT EXISTS public.national_coverage_partition (
    id                 BIGSERIAL PRIMARY KEY,
    universe_id        TEXT NOT NULL REFERENCES public.national_coverage_universe (universe_id),
    partition_id       TEXT NOT NULL,
    status             TEXT NOT NULL CHECK (
        status IN ('FOUND', 'ZERO_CONFIRMED', 'BLOCKED', 'FAILED', 'NOT_APPLICABLE')
    ),
    expected           BOOLEAN NOT NULL,
    queried            BOOLEAN NOT NULL,
    count_in_status    INTEGER,
    recorded_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS national_coverage_partition_universe_idx
    ON public.national_coverage_partition (universe_id, partition_id, recorded_at DESC);

CREATE TABLE IF NOT EXISTS public.national_coverage_corpus_snapshot (
    snapshot_id        TEXT PRIMARY KEY,
    universe_id        TEXT REFERENCES public.national_coverage_universe (universe_id),
    snapshot_hash      TEXT NOT NULL,
    as_of              TEXT NOT NULL,
    source             TEXT NOT NULL,
    publisher_count    INTEGER NOT NULL CHECK (publisher_count >= 0),
    contract_count     INTEGER NOT NULL CHECK (contract_count >= 0),
    relation           TEXT NOT NULL,
    payload            JSONB NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.national_coverage_answer (
    id                         BIGSERIAL PRIMARY KEY,
    universe_id                TEXT NOT NULL REFERENCES public.national_coverage_universe (universe_id),
    requested_geography        TEXT NOT NULL,
    requested_period           TEXT NOT NULL,
    requested_source           TEXT NOT NULL,
    requested_grain            TEXT NOT NULL,
    expected_partitions        INTEGER NOT NULL,
    closed_partitions          INTEGER NOT NULL,
    queried_partitions         INTEGER NOT NULL,
    coverage_pct               NUMERIC,
    national_claim_authorized  BOOLEAN NOT NULL DEFAULT FALSE,
    verdict                    TEXT NOT NULL CHECK (
        verdict IN ('NATIONAL_CLAIM_AUTHORIZED', 'PARTIAL', 'NOT_MEASURED', 'BLOCKED')
    ),
    reason_codes               TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    limitations                TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    provenance                 JSONB NOT NULL,
    content_hash               TEXT NOT NULL,
    payload                    JSONB NOT NULL,
    produced_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS national_coverage_answer_lookup_idx
    ON public.national_coverage_answer (
        universe_id, requested_geography, requested_period, requested_source, requested_grain, produced_at DESC
    );

CREATE OR REPLACE VIEW public.national_coverage_consumer_v1 AS
SELECT
    requested_geography,
    requested_period,
    requested_source,
    requested_grain,
    universe_id,
    expected_partitions,
    closed_partitions,
    coverage_pct,
    national_claim_authorized,
    verdict,
    reason_codes,
    limitations,
    provenance,
    content_hash,
    produced_at
FROM public.national_coverage_answer;

COMMENT ON TABLE public.national_coverage_universe IS
    'Versioned national coverage denominator. Extra 1.093 is never a national source.';
COMMENT ON VIEW public.national_coverage_consumer_v1 IS
    'SELECT-only consumer facts for the editorial gate. No indexation authorization.';

COMMIT;
