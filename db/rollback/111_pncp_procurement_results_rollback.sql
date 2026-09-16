BEGIN;
DROP FUNCTION IF EXISTS public.backfill_procurement_results_engineering_object();
DROP FUNCTION IF EXISTS public.link_procurement_results_to_contracts();
DROP FUNCTION IF EXISTS public.apply_pncp_procurement_results(JSONB);
DROP TABLE IF EXISTS public.pncp_procurement_results;
COMMIT;
