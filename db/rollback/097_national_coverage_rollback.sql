-- Rollback 097_national_coverage.sql
BEGIN;
DROP VIEW IF EXISTS public.national_coverage_consumer_v1;
DROP TABLE IF EXISTS public.national_coverage_answer;
DROP TABLE IF EXISTS public.national_coverage_corpus_snapshot;
DROP TABLE IF EXISTS public.national_coverage_partition;
DROP TABLE IF EXISTS public.national_coverage_universe;
COMMIT;
