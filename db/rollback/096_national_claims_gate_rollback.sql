-- Rollback 096_national_claims_gate.sql
BEGIN;
DROP TABLE IF EXISTS public.national_claims_lkg;
DROP TABLE IF EXISTS public.national_claims_decision;
DROP TABLE IF EXISTS public.national_claims_identity_evidence;
DROP TABLE IF EXISTS public.national_claims_aggregate_evidence;
DROP TABLE IF EXISTS public.national_claims_partition;
DROP TABLE IF EXISTS public.national_claims_universe;
COMMIT;
