-- 102_national_coverage_nullable_expected_units.sql
-- The official PNCP organization catalog enumerates publishing organizations,
-- not their publishing units. Preserve that unknown as NULL instead of
-- inventing one unit per organization or failing persistence.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

ALTER TABLE public.national_coverage_universe
    ALTER COLUMN expected_units DROP NOT NULL;

COMMENT ON COLUMN public.national_coverage_universe.expected_units IS
    'Official publishing-unit denominator. NULL means the source did not enumerate units and blocks national authorization.';

COMMIT;
