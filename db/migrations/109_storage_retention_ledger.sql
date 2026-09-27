-- Durable idempotency/evidence ledger for per-batch storage retention.
-- Canonical contracts are never deleted by this migration.
BEGIN;

CREATE TABLE IF NOT EXISTS public.storage_retention_ledger (
    batch_key              TEXT PRIMARY KEY,
    unit_key               TEXT NOT NULL,
    claim_token            TEXT NOT NULL,
    state                  TEXT NOT NULL,
    transport_bytes        BIGINT NOT NULL CHECK (transport_bytes >= 0),
    relation_growth_bytes  BIGINT NOT NULL CHECK (relation_growth_bytes >= 0),
    filesystem_freed_bytes BIGINT,
    relation_reusable_bytes BIGINT,
    report                 JSONB NOT NULL DEFAULT '{}'::jsonb,
    claimed_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    lease_expires_at       TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '15 minutes',
    attempts               INTEGER NOT NULL DEFAULT 1 CHECK (attempts > 0),
    completed_at           TIMESTAMPTZ,
    CONSTRAINT storage_retention_state_ck
        CHECK (state IN ('CLAIMED', 'SATISFIED', 'DEGRADED', 'ERROR'))
);

CREATE INDEX IF NOT EXISTS idx_storage_retention_ledger_claimed_at
    ON public.storage_retention_ledger (claimed_at DESC);

CREATE INDEX IF NOT EXISTS idx_storage_retention_ledger_incomplete
    ON public.storage_retention_ledger (lease_expires_at)
    WHERE state = 'CLAIMED';

COMMENT ON TABLE public.storage_retention_ledger IS
    'Exactly-once claim and durable evidence for post-commit PNCP storage retention.';

COMMIT;
