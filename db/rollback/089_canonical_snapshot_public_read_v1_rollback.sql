BEGIN;

REVOKE ALL ON SCHEMA public_read_v1 FROM smartlic_public_reader;
DROP SCHEMA IF EXISTS public_read_v1 CASCADE;
DROP TRIGGER IF EXISTS trg_canonical_revision_snapshot_fanout ON public.canonical_event_revisions;
DROP FUNCTION IF EXISTS public.fanout_canonical_revision_invalidation_v1();
DROP FUNCTION IF EXISTS public.invalidate_consumer_projection_private_v1(TEXT, TEXT, TEXT);
DROP FUNCTION IF EXISTS public.close_canonical_public_snapshot_v1(TEXT);
DROP FUNCTION IF EXISTS public.put_canonical_snapshot_watermark_v1(TEXT, TEXT, TEXT, TIMESTAMPTZ, TEXT, TEXT, INTEGER, INTEGER, TEXT);
DROP FUNCTION IF EXISTS public.begin_canonical_public_snapshot_v1(TIMESTAMPTZ, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, INTEGER, INTEGER, TEXT);
DROP TABLE IF EXISTS public.public_read_surface_health_internal;
DROP TABLE IF EXISTS public.public_consumer_projections;
DROP TABLE IF EXISTS public.canonical_snapshot_invalidations;
DROP TABLE IF EXISTS public.canonical_snapshot_dossiers;
DROP TABLE IF EXISTS public.canonical_snapshot_documents;
DROP TABLE IF EXISTS public.canonical_snapshot_event_revisions;
DROP TABLE IF EXISTS public.canonical_snapshot_source_watermarks;
DROP TABLE IF EXISTS public.canonical_public_snapshots;
DROP FUNCTION IF EXISTS public.guard_closed_canonical_snapshot_v1();

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_roles role
        WHERE role.rolname = 'smartlic_public_reader'
          AND shobj_description(role.oid, 'pg_authid') = 'managed-by-extra-migration-089'
    ) THEN
        EXECUTE format('REVOKE CONNECT ON DATABASE %I FROM smartlic_public_reader', current_database());
        EXECUTE format('REVOKE smartlic_public_reader FROM %I', current_user);
        ALTER ROLE smartlic_public_reader RESET statement_timeout;
        ALTER ROLE smartlic_public_reader RESET lock_timeout;
        ALTER ROLE smartlic_public_reader RESET idle_in_transaction_session_timeout;
        ALTER ROLE smartlic_public_reader RESET default_transaction_read_only;
        DROP OWNED BY smartlic_public_reader;
        BEGIN
            DROP ROLE smartlic_public_reader;
        EXCEPTION
            WHEN dependent_objects_still_exist THEN
                RAISE NOTICE 'smartlic_public_reader still owns objects outside database %; role retained', current_database();
        END;
    END IF;
END $$;

COMMIT;
