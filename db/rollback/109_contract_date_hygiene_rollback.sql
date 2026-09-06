-- Rollback of db/migrations/109_contract_date_hygiene.sql
-- Does NOT restore previously nulled absurd dates (they were invalid).

BEGIN;

DROP VIEW IF EXISTS public.v_contract_dates_sane;
DROP TRIGGER IF EXISTS trg_quarantine_implausible_contract_dates ON public.pncp_supplier_contracts;
DROP FUNCTION IF EXISTS public.fn_quarantine_implausible_contract_dates();
DROP TABLE IF EXISTS public.canonical_surface_operational_status;

COMMIT;
