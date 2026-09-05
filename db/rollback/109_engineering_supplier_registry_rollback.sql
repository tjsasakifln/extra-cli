-- Rollback of db/migrations/109_engineering_supplier_registry.sql

BEGIN;

DROP TABLE IF EXISTS public.engineering_supplier_registry_runs;
DROP VIEW IF EXISTS public.v_supplier_cadastral_contact;
DROP VIEW IF EXISTS public.v_engineering_supplier_universe;
DROP FUNCTION IF EXISTS public.fn_is_official_engineering_categoria(TEXT, INTEGER);

COMMIT;
