-- Rollback 090 is a no-op for data. Writer EXECUTE grants stay revoked
-- (fail-closed). Views and ingest/close stay at the locked contract.
-- Dropping the ledger row is enough for re-apply.

BEGIN;
COMMIT;
