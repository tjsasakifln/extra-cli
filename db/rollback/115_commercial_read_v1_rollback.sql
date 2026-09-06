BEGIN;
REVOKE ALL ON TABLE public.v_recent_engineering_wins FROM confenge_commercial_read_v1;
DROP VIEW IF EXISTS public.v_recent_engineering_wins;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_roles
        WHERE rolname = 'confenge_commercial_read_v1'
          AND obj_description(oid, 'pg_authid') = 'managed-by-extra-migration-115'
    ) THEN
        DROP OWNED BY confenge_commercial_read_v1;
        DROP ROLE confenge_commercial_read_v1;
    END IF;
END $$;
COMMIT;
