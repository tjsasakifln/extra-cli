-- Rollback 098_national_coverage_consumer_select_only.sql
-- Restores the 097 view definition. Tables stay intact.

BEGIN;

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

COMMENT ON VIEW public.national_coverage_consumer_v1 IS
    'SELECT-only consumer facts for the editorial gate. No indexation authorization.';

COMMIT;
