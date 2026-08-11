-- Preserve one observed, valid CNPJ-14 per sector root for contact enrichment.

BEGIN;

ALTER TABLE public.confenge_company_sector_current
    ADD COLUMN IF NOT EXISTS representative_cnpj14 CHAR(14);

ALTER TABLE public.confenge_company_sector_history
    ADD COLUMN IF NOT EXISTS representative_cnpj14 CHAR(14);

COMMENT ON COLUMN public.confenge_company_sector_current.representative_cnpj14 IS
'Valid establishment CNPJ observed in canonical source data; NULL is honest and never synthesized.';

COMMENT ON COLUMN public.confenge_company_sector_history.representative_cnpj14 IS
'Append-only lineage for the establishment identity used by bounded enrichment workers.';

COMMIT;
