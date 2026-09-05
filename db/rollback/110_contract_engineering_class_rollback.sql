-- Rollback of db/migrations/110_contract_engineering_class.sql

BEGIN;

DROP FUNCTION IF EXISTS public.apply_contract_engineering_class(JSONB);
DROP TABLE IF EXISTS public.contract_engineering_class;

COMMIT;
