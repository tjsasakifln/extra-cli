-- Rollback 094: drop only the additive research families. v1.0.0 views stay.

BEGIN;

DROP VIEW IF EXISTS public_read_v1.research_health;
DROP VIEW IF EXISTS public_read_v1.research_claim_gate;
DROP VIEW IF EXISTS public_read_v1.research_flagship_series;
DELETE FROM public_read_v1.query_budgets
 WHERE query_family IN ('research_flagship_series', 'research_claim_gate', 'research_health');
DELETE FROM public_read_v1.contract_releases WHERE version = 'v1.1.0';
DELETE FROM public.public_read_surface_health_internal WHERE view_name = 'research_flagship';
DROP TABLE IF EXISTS public.public_read_research_claim_internal;
DROP TABLE IF EXISTS public.public_read_research_flagship_internal;

COMMIT;
