-- 094_public_intelligence_research_models.sql
-- Additive public_read_v1 families for extra-cli#400 / web-cfg#65+#73.
-- 094 was free on origin/main@42166330 after fetch. Reserved for this issue only.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

CREATE TABLE IF NOT EXISTS public.public_read_research_flagship_internal (
    series_key            TEXT PRIMARY KEY,
    competence            TEXT NOT NULL,
    geography_kind        TEXT NOT NULL CHECK (geography_kind IN ('UF', 'BR')),
    geography_code        TEXT NOT NULL,
    archetype_id          TEXT NOT NULL,
    contract_count        INTEGER NOT NULL CHECK (contract_count >= 0),
    total_value_brl       NUMERIC,
    ticket_p25_brl        NUMERIC,
    ticket_median_brl     NUMERIC,
    ticket_p75_brl        NUMERIC,
    value_status          TEXT NOT NULL CHECK (value_status IN ('KNOWN', 'UNKNOWN')),
    as_of                 TIMESTAMPTZ NOT NULL,
    source_updated_at     TIMESTAMPTZ,
    completeness          TEXT NOT NULL,
    reason_codes          TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    provenance            JSONB NOT NULL,
    UNIQUE (competence, geography_kind, geography_code, archetype_id)
);

CREATE TABLE IF NOT EXISTS public.public_read_research_claim_internal (
    singleton                          BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    consumer_id                        TEXT NOT NULL,
    contract_version                   TEXT NOT NULL,
    nacional_completo                  BOOLEAN NOT NULL,
    national_claim_allowed             BOOLEAN NOT NULL,
    reason_codes                       TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    as_of                              TIMESTAMPTZ NOT NULL,
    freshness_status                   TEXT NOT NULL,
    coverage_status                    TEXT NOT NULL,
    coverage_ratio                     TEXT,
    completeness                       TEXT NOT NULL,
    catalog_hash                       TEXT,
    reconciliation_hash                TEXT,
    extra_1093_used_as_denominator     BOOLEAN NOT NULL DEFAULT FALSE,
    provenance                         JSONB NOT NULL,
    query_budget                       JSONB NOT NULL,
    consumer_error_count               BIGINT NOT NULL DEFAULT 0 CHECK (consumer_error_count >= 0),
    updated_at                         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO public.public_read_surface_health_internal (view_name, last_refresh_status)
VALUES ('research_flagship', 'NEVER')
ON CONFLICT (view_name) DO NOTHING;

CREATE OR REPLACE VIEW public_read_v1.research_flagship_series AS
SELECT
    series.series_key,
    series.competence,
    series.geography_kind,
    series.geography_code,
    series.archetype_id,
    series.contract_count,
    series.total_value_brl,
    series.ticket_p25_brl,
    series.ticket_median_brl,
    series.ticket_p75_brl,
    series.value_status,
    series.as_of,
    series.source_updated_at,
    series.completeness,
    series.reason_codes,
    series.provenance
FROM public.public_read_research_flagship_internal series
CROSS JOIN public_read_v1.access_gate gate
WHERE gate.enabled
ORDER BY series.competence, series.geography_kind, series.geography_code, series.archetype_id;

CREATE OR REPLACE VIEW public_read_v1.research_claim_gate AS
SELECT
    claim.consumer_id,
    claim.contract_version,
    claim.nacional_completo,
    claim.national_claim_allowed,
    claim.reason_codes,
    claim.as_of,
    claim.freshness_status,
    claim.completeness,
    claim.catalog_hash,
    claim.reconciliation_hash,
    claim.extra_1093_used_as_denominator,
    claim.provenance,
    claim.query_budget,
    claim.consumer_error_count
FROM public.public_read_research_claim_internal claim
CROSS JOIN public_read_v1.access_gate gate
WHERE claim.singleton AND gate.enabled;

CREATE OR REPLACE VIEW public_read_v1.research_health AS
SELECT
    health.view_name AS family,
    health.enabled,
    health.refreshed_at,
    health.query_count,
    health.error_count AS consumer_error_count,
    health.query_p95_ms,
    health.last_refresh_status,
    health.last_error,
    claim.as_of,
    claim.freshness_status,
    claim.coverage_status,
    claim.coverage_ratio,
    claim.nacional_completo,
    claim.national_claim_allowed,
    claim.reason_codes,
    snapshot.snapshot_id,
    CASE
        WHEN claim.singleton IS NULL THEN 'UNKNOWN'
        WHEN claim.national_claim_allowed THEN 'COMPLETE'
        ELSE 'INCOMPLETE'
    END AS completeness,
    jsonb_build_object(
        'snapshot_id', snapshot.snapshot_id,
        'catalog_hash', claim.catalog_hash,
        'consumer_error_count', health.error_count
    ) AS provenance
FROM public.public_read_surface_health_internal health
LEFT JOIN public.public_read_research_claim_internal claim ON claim.singleton
LEFT JOIN public_read_v1.current_snapshot snapshot ON TRUE
CROSS JOIN public_read_v1.access_gate gate
WHERE health.view_name = 'research_flagship' AND gate.enabled;

INSERT INTO public_read_v1.query_budgets VALUES
    (
        'research_flagship_series',
        2000,
        250,
        64,
        2,
        'SELECT * FROM public_read_v1.research_flagship_series WHERE competence = $1 ORDER BY geography_kind, geography_code, archetype_id LIMIT 64'
    ),
    (
        'research_claim_gate',
        1000,
        100,
        1,
        4,
        'SELECT * FROM public_read_v1.research_claim_gate LIMIT 1'
    ),
    (
        'research_health',
        1000,
        100,
        20,
        2,
        'SELECT * FROM public_read_v1.research_health LIMIT 20'
    )
ON CONFLICT (query_family) DO UPDATE SET
    statement_timeout_ms = EXCLUDED.statement_timeout_ms,
    p95_budget_ms = EXCLUDED.p95_budget_ms,
    max_rows = EXCLUDED.max_rows,
    max_concurrent = EXCLUDED.max_concurrent,
    representative_query = EXCLUDED.representative_query;

DO $$
DECLARE release_hash TEXT;
BEGIN
    SELECT encode(digest(string_agg(table_name || ':' || ordinal_position || ':' || column_name || ':' || data_type || ':' || is_nullable, '|' ORDER BY table_name, ordinal_position), 'sha256'), 'hex')
    INTO release_hash
    FROM information_schema.columns
    WHERE table_schema = 'public_read_v1'
      AND table_name IN (
          'current_snapshot', 'tenders', 'contracts', 'entities', 'suppliers',
          'organs', 'municipalities', 'surface_health',
          'research_flagship_series', 'research_claim_gate', 'research_health'
      );
    INSERT INTO public_read_v1.contract_releases VALUES (
        'v1.1.0',
        NOW(),
        release_hash,
        'Additive nullable columns and new families only within v1; removal/type/nullability changes require public_read_v2.',
        180,
        'Additive research-flagship series, claim gate and health families for extra-cli#400. 094 used because it was free on origin/main@42166330.'
    ) ON CONFLICT (version) DO UPDATE SET
        schema_hash = EXCLUDED.schema_hash,
        changelog = EXCLUDED.changelog;
END $$;

GRANT SELECT ON public_read_v1.research_flagship_series TO smartlic_public_reader;
GRANT SELECT ON public_read_v1.research_claim_gate TO smartlic_public_reader;
GRANT SELECT ON public_read_v1.research_health TO smartlic_public_reader;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON public_read_v1.research_flagship_series,
       public_read_v1.research_claim_gate,
       public_read_v1.research_health
    FROM smartlic_public_reader;
REVOKE ALL ON public.public_read_research_flagship_internal FROM smartlic_public_reader;
REVOKE ALL ON public.public_read_research_claim_internal FROM smartlic_public_reader;

COMMIT;
