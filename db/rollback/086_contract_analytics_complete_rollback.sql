BEGIN;

DROP FUNCTION IF EXISTS public.supplier_contracts_grouped_v2(TEXT, TEXT, TEXT[], TEXT[], DATE, DATE, INTEGER, TEXT);
DROP FUNCTION IF EXISTS public.supplier_contracts_page_v2(TEXT, TEXT, TEXT, TEXT[], TEXT[], DATE, DATE, NUMERIC, INTEGER, DATE, BIGINT, TEXT);
DROP FUNCTION IF EXISTS public.supplier_contracts_dataset_v2(TEXT, TEXT, TEXT, TEXT[], TEXT[], DATE, DATE, TEXT);
DROP INDEX IF EXISTS public.idx_psc_supplier_event_keyset;

COMMIT;
