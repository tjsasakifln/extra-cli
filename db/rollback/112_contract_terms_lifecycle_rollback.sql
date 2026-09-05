BEGIN;
DROP FUNCTION IF EXISTS public.apply_contract_terms(JSONB);
DROP TABLE IF EXISTS public.contract_terms;
ALTER TABLE public.pncp_supplier_contracts
    DROP COLUMN IF EXISTS lifecycle_event_last,
    DROP COLUMN IF EXISTS lifecycle_event_at;
COMMIT;
