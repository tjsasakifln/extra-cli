-- 112_engineering_supplier_registry.sql
-- #549: expand supplier_registry coverage to engineering-contract suppliers
-- of the last 24 months, and expose a cadastral contact join with provenance.
-- Engineering universe uses official PNCP categoria_processo (#546), never
-- objeto regex. Decision-maker discovery is out of scope.
--
-- Depends on #546 / migration 108 (categoria_processo_* columns).
--
-- ROLLBACK:
--   psql "$LOCAL_DATALAKE_DSN" -f db/rollback/112_engineering_supplier_registry_rollback.sql

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

CREATE OR REPLACE FUNCTION public.fn_is_official_engineering_categoria(
    p_nome TEXT,
    p_id INTEGER
) RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT
        CASE
            WHEN p_nome IS NULL AND p_id IS NULL THEN FALSE
            ELSE
                lower(btrim(translate(
                    COALESCE(p_nome, ''),
                    'ÁÀÂÃÄáàâãäÉÈÊËéèêëÍÌÎÏíìîïÓÒÔÕÖóòôõöÚÙÛÜúùûüÇç',
                    'AAAAAaaaaaEEEEeeeeIIIIiiiiOOOOOoooooUUUUuuuuCc'
                ))) IN (
                    'obras',
                    'servicos de engenharia',
                    'servico de engenharia',
                    'obras e servicos de engenharia'
                )
        END;
$$;

COMMENT ON FUNCTION public.fn_is_official_engineering_categoria(TEXT, INTEGER) IS
    'Official PNCP categoriaProcesso membership for engineering. Does not inspect objeto. #549.';

CREATE OR REPLACE VIEW public.v_engineering_supplier_universe AS
SELECT DISTINCT
    regexp_replace(COALESCE(contract.fornecedor_cnpj, ''), '\D', '', 'g') AS cnpj14,
    max(contract.fornecedor_nome) AS fornecedor_nome,
    count(*) AS n_contracts_24m,
    max(COALESCE(contract.data_assinatura, contract.data_publicacao_fonte, contract.data_publicacao)) AS last_sig
FROM public.pncp_supplier_contracts contract
WHERE regexp_replace(COALESCE(contract.fornecedor_cnpj, ''), '\D', '', 'g') ~ '^\d{14}$'
  AND COALESCE(contract.data_assinatura, contract.data_publicacao_fonte, contract.data_publicacao)
        >= (CURRENT_DATE - INTERVAL '24 months')
  AND public.fn_is_official_engineering_categoria(
        contract.categoria_processo_nome,
        contract.categoria_processo_id
      )
GROUP BY 1;

COMMENT ON VIEW public.v_engineering_supplier_universe IS
    'Engineering suppliers of the last 24 months by official categoria_processo (#546/#549). No objeto regex. Coverage AC is measured after structural-field backfill.';

CREATE OR REPLACE VIEW public.v_supplier_cadastral_contact AS
SELECT
    registry.cnpj14,
    registry.razao_social,
    registry.nome_fantasia,
    registry.cnae_principal,
    registry.situacao_cadastral,
    registry.municipio,
    registry.uf,
    registry.source AS registry_source,
    registry.source_version AS registry_source_version,
    registry.source_date AS registry_source_date,
    registry.ingested_at AS registry_ingested_at,
    enriched.email AS cadastral_email,
    enriched.telefone AS cadastral_telefone,
    enriched.enriched_at,
    enriched.enriched_source,
    (
        (enriched.email IS NOT NULL AND btrim(enriched.email) <> '')
        OR (enriched.telefone IS NOT NULL AND btrim(enriched.telefone) <> '')
    ) AS has_cadastral_contact
FROM public.supplier_registry registry
LEFT JOIN public.enriched_entities enriched
    ON regexp_replace(COALESCE(enriched.cnpj, ''), '\D', '', 'g') = registry.cnpj14;

COMMENT ON VIEW public.v_supplier_cadastral_contact IS
    'Cadastral email/phone from enriched_entities with enriched_at and source. Not decision-maker discovery. #549.';

CREATE TABLE IF NOT EXISTS public.engineering_supplier_registry_runs (
    run_id          TEXT PRIMARY KEY,
    cursor_cnpj14   TEXT,
    planned         BIGINT NOT NULL DEFAULT 0,
    upserted        BIGINT NOT NULL DEFAULT 0,
    skipped         BIGINT NOT NULL DEFAULT 0,
    last_run_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes           TEXT
);

COMMENT ON TABLE public.engineering_supplier_registry_runs IS
    'Monthly refresh cursor for #549 engineering supplier_registry coverage.';

COMMIT;
