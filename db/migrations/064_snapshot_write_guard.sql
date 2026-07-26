-- 064_snapshot_write_guard.sql
-- Campaign: CONFENGE-COMMERCIAL-READY-01
-- Prevent mutation of restored snapshot tables unless explicitly allowed.
-- Used for RESTORED_SNAPSHOT_SINGLE_DB honesty (source data immutable).
-- Override only for controlled restore: SET LOCAL app.allow_snapshot_mutation = 'on';

BEGIN;

CREATE OR REPLACE FUNCTION public.prevent_pncp_snapshot_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    allow_flag text;
BEGIN
    allow_flag := current_setting('app.allow_snapshot_mutation', true);
    IF allow_flag IS DISTINCT FROM 'on' THEN
        RAISE EXCEPTION
            'CONFENGE snapshot table public.pncp_supplier_contracts is write-protected (RESTORED_SNAPSHOT_SINGLE_DB). SET LOCAL app.allow_snapshot_mutation = ''on'' only for controlled restore.'
            USING ERRCODE = '42501';  -- insufficient_privilege
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
    'Blocks campaign/state roles from mutating restored PNCP snapshot rows.';

COMMIT;
