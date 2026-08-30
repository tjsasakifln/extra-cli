-- Rollback 102_national_coverage_nullable_expected_units.sql
-- Fail closed: never replace an unknown denominator with an invented count.

BEGIN;

DO $rollback$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.national_coverage_universe
        WHERE expected_units IS NULL
    ) THEN
        RAISE EXCEPTION
            'cannot restore expected_units NOT NULL while unknown unit denominators exist';
    END IF;
END
$rollback$;

ALTER TABLE public.national_coverage_universe
    ALTER COLUMN expected_units SET NOT NULL;

COMMENT ON COLUMN public.national_coverage_universe.expected_units IS NULL;

COMMIT;
