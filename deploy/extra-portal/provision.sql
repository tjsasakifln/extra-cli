-- DBA, pncp_datalake. The web runtime has no connection to the database.
BEGIN;
DO $body$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'confenge-extra-intel') THEN
    CREATE ROLE "confenge-extra-intel" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
      NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2 PASSWORD NULL;
  END IF;
END
$body$;
ALTER ROLE "confenge-extra-intel" SET default_transaction_read_only = on;
ALTER ROLE "confenge-extra-intel" SET search_path = pg_catalog;
ALTER ROLE "confenge-extra-intel" SET statement_timeout = '25s';
ALTER ROLE "confenge-extra-intel" SET idle_in_transaction_session_timeout = '15s';
ALTER ROLE "confenge-extra-intel" SET temp_file_limit = '128MB';
GRANT CONNECT ON DATABASE pncp_datalake TO "confenge-extra-intel";
GRANT USAGE ON SCHEMA public TO "confenge-extra-intel";
GRANT SELECT (id, source, numero_controle_pncp, objeto, orgao_nome, orgao_cnpj, uf,
  municipio, data_publicacao, data_abertura, data_encerramento, last_status_verified_at,
  status_canonico, is_active, source_active, content_hash)
  ON public.opportunity_intel TO "confenge-extra-intel";
GRANT SELECT (id, source, contrato_id, objeto_contrato, orgao_nome, orgao_cnpj, uf,
  municipio, supplier_id_type, fornecedor_nome, data_publicacao, data_publicacao_fonte,
  data_fim, source_updated_at, status_normalized, is_active, quality_state)
  ON public.pncp_supplier_contracts TO "confenge-extra-intel";
DO $audit$
DECLARE
  role_name constant text := 'confenge-extra-intel';
BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = role_name AND
      (rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls))
    OR EXISTS (SELECT FROM pg_auth_members WHERE member = (SELECT oid FROM pg_roles WHERE rolname = role_name))
    OR has_schema_privilege(role_name, 'public', 'CREATE')
    OR has_database_privilege(role_name, 'pncp_datalake', 'CREATE')
    OR EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND
        has_table_privilege(role_name, format('%I.%I', schemaname, tablename), 'INSERT,UPDATE,DELETE,TRUNCATE'))
  THEN
    RAISE EXCEPTION 'unexpected Extra portal privileges';
  END IF;
END
$audit$;
COMMIT;
