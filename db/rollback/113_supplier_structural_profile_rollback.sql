BEGIN;
DROP FUNCTION IF EXISTS public.refresh_supplier_structural_profile();
DROP MATERIALIZED VIEW IF EXISTS public.mv_supplier_structural_profile;
COMMIT;
