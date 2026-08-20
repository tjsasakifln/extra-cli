-- 098_national_coverage_consumer_select_only.sql
-- Additive SELECT-only lock on the 097 consumer view. Does not rewrite 097 tables.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

CREATE OR REPLACE VIEW public.national_coverage_consumer_v1 AS
SELECT
    a.requested_geography,
    a.requested_period,
    a.requested_source,
    a.requested_grain,
    a.universe_id,
    a.expected_partitions,
    a.closed_partitions,
    a.coverage_pct,
    a.national_claim_authorized,
    a.verdict,
    a.reason_codes,
    a.limitations,
    a.provenance,
    a.content_hash,
    a.produced_at
FROM public.national_coverage_answer AS a
CROSS JOIN (SELECT true AS select_only) AS consumer_lock;

COMMENT ON VIEW public.national_coverage_consumer_v1 IS
    'SELECT-only consumer facts for the editorial gate. Mutation is denied. No indexation authorization.';

REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON public.national_coverage_consumer_v1 FROM PUBLIC;
GRANT SELECT ON public.national_coverage_consumer_v1 TO PUBLIC;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'smartlic_public_reader') THEN
        GRANT SELECT ON public.national_coverage_consumer_v1 TO smartlic_public_reader;
        REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
            ON public.national_coverage_consumer_v1 FROM smartlic_public_reader;
    END IF;
END $$;

COMMIT;
