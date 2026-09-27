-- 110_disable_contract_versioning_trigger.sql
-- The canonical contracts table stores the latest observation.  Production
-- had the snapshot trigger re-enabled, causing every incremental refresh to
-- append a full JSONB copy and exhaust disk/shared locks.  Keep versioning
-- disabled until history is partitioned with an explicit storage budget.

BEGIN;

-- apply_migrations uses autocommit; session-level timeouts keep this ALTER
-- bounded even though BEGIN/COMMIT markers are intentionally ignored there.
SET lock_timeout = '10s';
SET statement_timeout = '60s';

ALTER TABLE public.pncp_supplier_contracts
    DISABLE TRIGGER trg_contract_versioning;

RESET lock_timeout;
RESET statement_timeout;

COMMIT;
