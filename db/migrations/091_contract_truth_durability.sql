-- 091_contract_truth_durability.sql
-- Activity proof (#309), quality quarantine (#312), namespaced identity (#306).
-- Additive: raw official columns stay untouched.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

ALTER TABLE public.pncp_supplier_contracts
    ADD COLUMN IF NOT EXISTS status_raw TEXT,
    ADD COLUMN IF NOT EXISTS status_normalized TEXT,
    ADD COLUMN IF NOT EXISTS status_rule_version TEXT,
    ADD COLUMN IF NOT EXISTS status_source TEXT,
    ADD COLUMN IF NOT EXISTS status_observed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS quality_state TEXT,
    ADD COLUMN IF NOT EXISTS quality_reasons JSONB,
    ADD COLUMN IF NOT EXISTS quality_rule_version TEXT,
    ADD COLUMN IF NOT EXISTS canonical_contract_id TEXT,
    ADD COLUMN IF NOT EXISTS source TEXT,
    ADD COLUMN IF NOT EXISTS source_contract_id TEXT,
    ADD COLUMN IF NOT EXISTS parent_procurement_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_pncp_contracts_source_source_id
    ON public.pncp_supplier_contracts (source, source_contract_id)
    WHERE source IS NOT NULL AND source_contract_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.contract_id_aliases (
    alias_id TEXT PRIMARY KEY,
    canonical_contract_id TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE VIEW public.v_contracts_all AS
SELECT *
FROM public.pncp_supplier_contracts;

CREATE OR REPLACE VIEW public.v_contracts_active_proven AS
SELECT *
FROM public.pncp_supplier_contracts
WHERE status_normalized = 'ACTIVE_PROVEN';

CREATE OR REPLACE VIEW public.v_contracts_report_ready AS
SELECT *
FROM public.pncp_supplier_contracts
WHERE quality_state IS NOT NULL
  AND quality_state <> 'QUARANTINED'
  AND status_normalized IS NOT NULL
  AND status_normalized <> 'UNKNOWN';

COMMIT;
