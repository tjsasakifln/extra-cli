-- Run as the database administrator against pncp_datalake.
-- New, isolated reader only: no schema/data mutation, no existing grants changed.
BEGIN;
DO $body$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'confenge-radar') THEN
    CREATE ROLE "confenge-radar" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
      NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2;
  END IF;
END
$body$;
ALTER ROLE "confenge-radar" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
  NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2 PASSWORD NULL;
ALTER ROLE "confenge-radar" SET default_transaction_read_only = on;
ALTER ROLE "confenge-radar" SET search_path = pg_catalog;
ALTER ROLE "confenge-radar" SET statement_timeout = '10min';
ALTER ROLE "confenge-radar" SET idle_in_transaction_session_timeout = '10min';
ALTER ROLE "confenge-radar" SET lock_timeout = '5s';
ALTER ROLE "confenge-radar" SET work_mem = '32MB';
ALTER ROLE "confenge-radar" SET temp_file_limit = '2GB';
GRANT CONNECT ON DATABASE pncp_datalake TO "confenge-radar";
GRANT USAGE ON SCHEMA public TO "confenge-radar";
GRANT SELECT (
  id, contrato_id, orgao_cnpj, orgao_nome, fornecedor_cnpj, fornecedor_nome,
  objeto_contrato, valor_total, data_inicio, data_fim, data_publicacao_fonte,
  uf, municipio, ingested_at, is_active, data_assinatura, data_publicacao,
  last_seen_at, source_updated_at, supplier_id_type, status_normalized, quality_state
) ON public.pncp_supplier_contracts TO "confenge-radar";
DO $audit$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_auth_members
    WHERE member = (SELECT oid FROM pg_roles WHERE rolname = 'confenge-radar')
  ) OR has_schema_privilege('confenge-radar', 'public', 'CREATE')
    OR has_database_privilege('confenge-radar', 'pncp_datalake', 'CREATE')
    OR has_table_privilege('confenge-radar', 'public.pncp_supplier_contracts', 'SELECT')
    OR has_table_privilege('confenge-radar', 'public.pncp_supplier_contracts',
      'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') THEN
    RAISE EXCEPTION 'confenge-radar privileges exceed the read-only contract';
  END IF;
END
$audit$;
COMMIT;

-- Expected: all role flags false; UPDATE/INSERT/DELETE/TRUNCATE false.
SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls
FROM pg_roles WHERE rolname = 'confenge-radar';
SELECT privilege, has_table_privilege('confenge-radar', 'public.pncp_supplier_contracts', privilege)
FROM unnest(ARRAY['INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER']) privilege;
