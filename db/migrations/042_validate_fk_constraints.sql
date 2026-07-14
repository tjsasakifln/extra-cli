-- Migration 042: Validate all pending FK constraints
-- B2G-FIX-04: FKs created as NOT VALID in 041a must be validated
-- to enforce referential integrity at the database level.
--
-- In fresh install (empty tables), validation is instantaneous.
-- In upgrade (populated tables), validation performs a full table scan.
-- SET LOCAL lock_timeout prevents runaway locks.
--
-- Rollback: ALTER TABLE ... DROP CONSTRAINT IF EXISTS ... (each FK).
--   No data loss — only removes constraint enforcement.

BEGIN;

SET LOCAL lock_timeout = '30s';
SET LOCAL statement_timeout = '300s';

-- Validate FKs created by 041a (B2G-FIX-04)
ALTER TABLE pncp_raw_bids
    VALIDATE CONSTRAINT fk_bids_orgao_entity_v2;

ALTER TABLE pncp_supplier_contracts
    VALIDATE CONSTRAINT fk_contracts_orgao_entity_v2;

ALTER TABLE pncp_supplier_contracts
    VALIDATE CONSTRAINT fk_contracts_supplier_entity_v2;

-- Verify all 3 FKs are now validated
DO $$
DECLARE
    v_unvalidated INT;
BEGIN
    SELECT COUNT(*) INTO v_unvalidated
    FROM pg_catalog.pg_constraint
    WHERE conname IN (
        'fk_bids_orgao_entity_v2',
        'fk_contracts_orgao_entity_v2',
        'fk_contracts_supplier_entity_v2'
    )
    AND convalidated = FALSE;

    IF v_unvalidated > 0 THEN
        RAISE EXCEPTION 'Validation failed: % FK(s) still NOT VALID', v_unvalidated;
    END IF;

    RAISE NOTICE 'All 3 FKs validated successfully.';
END;
$$;

COMMENT ON CONSTRAINT fk_bids_orgao_entity_v2 ON pncp_raw_bids IS
    'FK validated by migration 042 (B2G-FIX-04). Links bid orgao to canonical entity.';
COMMENT ON CONSTRAINT fk_contracts_orgao_entity_v2 ON pncp_supplier_contracts IS
    'FK validated by migration 042 (B2G-FIX-04). Links contract orgao to canonical entity.';
COMMENT ON CONSTRAINT fk_contracts_supplier_entity_v2 ON pncp_supplier_contracts IS
    'FK validated by migration 042 (B2G-FIX-04). Links contract supplier to canonical entity.';

COMMIT;
