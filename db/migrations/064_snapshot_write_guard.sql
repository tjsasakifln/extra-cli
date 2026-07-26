-- 064_snapshot_write_guard.sql
-- Campaign: CONFENGE-COMMERCIAL-READY-01
-- Opt-in write guard for restored snapshot tables.
-- Active only when session sets: SET app.confenge_snapshot_guard = 'on'
-- Then mutations require: SET LOCAL app.allow_snapshot_mutation = 'on' (controlled restore only).
-- CI seeds / normal test DBs do not set the guard → inserts continue to work.

BEGIN;

CREATE OR REPLACE FUNCTION public.prevent_pncp_snapshot_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    guard_flag text;
    allow_flag text;
BEGIN
    guard_flag := current_setting('app.confenge_snapshot_guard', true);
    -- Guard inactive by default (CI seeds / normal migrations)
    IF guard_flag IS DISTINCT FROM 'on' THEN
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        END IF;
        RETURN NEW;
    END IF;

    allow_flag := current_setting('app.allow_snapshot_mutation', true);
    IF allow_flag IS DISTINCT FROM 'on' THEN
        RAISE EXCEPTION
            'CONFENGE snapshot table public.pncp_supplier_contracts is write-protected (RESTORED_SNAPSHOT_SINGLE_DB). SET LOCAL app.allow_snapshot_mutation = ''on'' only for controlled restore.'
            USING ERRCODE = '42501';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_prevent_pncp_snapshot_mutation ON public.pncp_supplier_contracts;
CREATE TRIGGER trg_prevent_pncp_snapshot_mutation
    BEFORE INSERT OR UPDATE OR DELETE ON public.pncp_supplier_contracts
    FOR EACH ROW
    EXECUTE PROCEDURE public.prevent_pncp_snapshot_mutation();

COMMENT ON FUNCTION public.prevent_pncp_snapshot_mutation() IS
    'Opt-in guard: blocks snapshot mutations when app.confenge_snapshot_guard=on.';

COMMIT;
