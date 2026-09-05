-- Rollback of db/migrations/107_pncp_structural_fields.sql
-- Restores v_contracts_canonical_v2 / upsert from 077 / 076 and drops #546 columns.

BEGIN;

DROP FUNCTION IF EXISTS public.apply_pncp_structural_fields(JSONB);
DROP TABLE IF EXISTS public.pncp_structural_fields_backfill_state;

CREATE OR REPLACE VIEW public.v_contracts_canonical_v2 AS
SELECT
    contract.contrato_id,
    contract.orgao_cnpj AS buyer_cnpj,
    contract.orgao_nome AS buyer_nome,
    roles.buyer_entity_id,
    buyer.razao_social AS buyer_entity_nome,
    buyer.cnpj_8 AS buyer_entity_cnpj_8,
    buyer.raio_200km AS buyer_within_200km,
    roles.buyer_match_method,
    roles.buyer_match_confidence,
    roles.buyer_reason_codes,
    roles.supplier_identity_id,
    contract.supplier_id_type,
    contract.supplier_identifier_export,
    contract.supplier_country,
    contract.fornecedor_cnpj AS supplier_cnpj,
    contract.fornecedor_nome AS supplier_nome,
    contract.is_active,
    roles.supplier_match_method,
    roles.supplier_match_confidence,
    roles.supplier_reason_codes,
    contract.objeto_contrato AS objeto,
    contract.valor_total AS valor,
    contract.data_inicio,
    contract.data_fim,
    contract.data_publicacao,
    contract.data_assinatura,
    contract.data_publicacao_fonte,
    contract.uf,
    contract.municipio,
    contract.codigo_municipio_ibge,
    contract.municipio_inferido,
    contract.source,
    contract.source_id,
    roles.match_run_id,
    roles.snapshot_id,
    roles.matched_at
FROM public.pncp_supplier_contracts contract
LEFT JOIN public.contract_role_links roles
    ON roles.contract_id = contract.contrato_id
LEFT JOIN public.sc_public_entities buyer
    ON buyer.id = roles.buyer_entity_id
WHERE contract.data_inicio IS NOT NULL OR contract.data_publicacao IS NOT NULL;

CREATE OR REPLACE VIEW public.v_value_observations_canonical_v2 AS
SELECT
    'bid'::TEXT AS observation_type,
    bid.pncp_id AS source_id,
    bid.orgao_cnpj,
    bid.municipio,
    bid.uf,
    bid.modalidade_id,
    bid.modalidade_nome AS modalidade,
    bid.objeto_compra AS objeto,
    bid.valor_total_estimado AS valor,
    bid.data_publicacao,
    entity.cnpj_8 AS buyer_entity_cnpj_8,
    entity.raio_200km AS buyer_within_200km
FROM public.pncp_raw_bids bid
LEFT JOIN public.sc_public_entities entity ON entity.id = bid.matched_entity_id
WHERE bid.valor_total_estimado IS NOT NULL AND bid.valor_total_estimado > 0

UNION ALL

SELECT
    'contract'::TEXT AS observation_type,
    contract.contrato_id AS source_id,
    contract.buyer_cnpj AS orgao_cnpj,
    contract.municipio,
    contract.uf,
    NULL::INTEGER AS modalidade_id,
    NULL::TEXT AS modalidade,
    contract.objeto,
    contract.valor,
    contract.data_publicacao,
    contract.buyer_entity_cnpj_8,
    contract.buyer_within_200km
FROM public.v_contracts_canonical_v2 contract
WHERE contract.valor IS NOT NULL AND contract.valor > 0;

CREATE OR REPLACE FUNCTION public.upsert_pncp_supplier_contracts(p_records JSONB)
RETURNS TABLE (action TEXT, contrato_id TEXT)
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM jsonb_array_elements(p_records) AS candidate(rec)
        WHERE upper(btrim(COALESCE(candidate.rec->>'supplier_id_type', '')))
                  IN ('CNPJ', 'CPF', 'FOREIGN')
          AND COALESCE(
                  NULLIF(btrim(candidate.rec->>'supplier_identifier'), ''),
                  NULLIF(btrim(candidate.rec->>'fornecedor_cnpj'), '')
              ) IS NULL
    ) THEN
        RAISE EXCEPTION 'supplier_identifier is required for declared CNPJ, CPF, or FOREIGN identity'
            USING ERRCODE = '23514';
    END IF;

    RETURN QUERY
    WITH raw_input AS (
        SELECT DISTINCT ON ((rec->>'contrato_id'))
            rec,
            NULLIF(upper(btrim(rec->>'supplier_id_type')), '') AS declared_type,
            COALESCE(
                NULLIF(btrim(rec->>'supplier_identifier'), ''),
                NULLIF(btrim(rec->>'fornecedor_cnpj'), '')
            ) AS raw_identifier,
            regexp_replace(
                COALESCE(
                    NULLIF(btrim(rec->>'supplier_identifier'), ''),
                    NULLIF(btrim(rec->>'fornecedor_cnpj'), ''),
                    ''
                ),
                '\D', '', 'g'
            ) AS identifier_digits
        FROM jsonb_array_elements(p_records) AS rec
        WHERE COALESCE(rec->>'contrato_id', '') <> ''
        ORDER BY (rec->>'contrato_id')
    ), classified AS (
        SELECT raw_input.*,
            CASE
                WHEN declared_type = 'CNPJ'
                    AND public.fn_contract_valid_cnpj(raw_identifier) THEN 'CNPJ'
                WHEN declared_type = 'CPF'
                    AND public.fn_contract_valid_cpf(raw_identifier) THEN 'CPF'
                WHEN declared_type = 'FOREIGN' AND raw_identifier IS NOT NULL THEN 'FOREIGN'
                WHEN declared_type = 'UNKNOWN' THEN 'UNKNOWN'
                WHEN declared_type IS NULL
                    AND public.fn_contract_valid_cnpj(raw_identifier) THEN 'CNPJ'
                WHEN declared_type IS NULL
                    AND public.fn_contract_valid_cpf(raw_identifier) THEN 'CPF'
                ELSE 'UNKNOWN'
            END AS canonical_type
        FROM raw_input
    ), normalized AS (
        SELECT classified.*,
            CASE
                WHEN canonical_type = 'CNPJ'
                    AND public.fn_contract_valid_cnpj(raw_identifier)
                    THEN identifier_digits
                WHEN canonical_type = 'CPF'
                    AND public.fn_contract_valid_cpf(raw_identifier)
                    THEN identifier_digits
                WHEN canonical_type = 'FOREIGN'
                    AND raw_identifier LIKE 'FOREIGN:%'
                    THEN raw_identifier
                WHEN canonical_type = 'FOREIGN' AND raw_identifier IS NOT NULL
                    THEN 'FOREIGN:' || COALESCE(NULLIF(rec->>'supplier_country', ''), 'ZZ')
                         || ':' || raw_identifier
                WHEN canonical_type = 'UNKNOWN'
                    AND raw_identifier LIKE 'UNKNOWN:%'
                    THEN raw_identifier
                WHEN canonical_type = 'UNKNOWN' AND raw_identifier IS NOT NULL
                    THEN 'UNKNOWN:' || COALESCE(NULLIF(rec->>'supplier_country', ''), 'ZZ')
                         || ':' || raw_identifier
                ELSE NULL
            END AS canonical_identifier
        FROM classified
    ), input AS (
        SELECT
            rec->>'contrato_id' AS in_contrato_id,
            rec->>'orgao_cnpj' AS orgao_cnpj,
            rec->>'orgao_nome' AS orgao_nome,
            CASE
                WHEN canonical_type = 'CNPJ'
                    AND public.fn_contract_valid_cnpj(canonical_identifier)
                    THEN canonical_identifier
                ELSE NULL
            END AS fornecedor_cnpj,
            rec->>'fornecedor_nome' AS fornecedor_nome,
            canonical_type AS supplier_id_type,
            canonical_identifier AS supplier_identifier,
            COALESCE(
                NULLIF(rec->>'supplier_country', ''),
                CASE
                    WHEN canonical_type IN ('CNPJ', 'CPF') THEN 'BR'
                    ELSE NULL
                END
            ) AS supplier_country,
            CASE
                WHEN canonical_identifier IS NULL THEN NULL
                ELSE encode(digest(
                    'supplier-identity-v1:' || canonical_type || ':' || canonical_identifier,
                    'sha256'
                ), 'hex')
            END AS supplier_identifier_hash,
            CASE
                WHEN canonical_type = 'CPF' THEN 'CPF:***.***.***-**'
                WHEN length(identifier_digits) = 11 THEN 'UNKNOWN:MASKED'
                WHEN canonical_type = 'CNPJ' THEN canonical_identifier
                WHEN canonical_type IN ('FOREIGN', 'UNKNOWN') THEN canonical_identifier
                ELSE NULL
            END AS supplier_identifier_export,
            COALESCE(
                NULLIF(rec->>'supplier_identity_reason', ''),
                CASE
                    WHEN declared_type IS NULL THEN 'legacy_rpc_classified'
                    ELSE 'rpc_server_normalized'
                END
            ) AS supplier_identity_reason,
            rec->>'objeto_contrato' AS objeto_contrato,
            NULLIF(rec->>'valor_total', '')::NUMERIC AS valor_total,
            NULLIF(rec->>'data_inicio', '')::DATE AS data_inicio,
            NULLIF(rec->>'data_fim', '')::DATE AS data_fim,
            NULLIF(rec->>'data_publicacao', '')::DATE AS data_publicacao,
            rec->>'uf' AS uf,
            rec->>'municipio' AS municipio,
            COALESCE(rec->>'source', 'pncp') AS source,
            rec->>'source_id' AS source_id,
            NULLIF(rec->>'data_assinatura', '')::DATE AS data_assinatura,
            NULLIF(rec->>'data_publicacao_fonte', '')::DATE AS data_publicacao_fonte,
            NULLIF(rec->>'data_atualizacao_fonte', '')::DATE AS data_atualizacao_fonte,
            NULLIF(rec->>'source_event_date', '')::DATE AS source_event_date,
            NULLIF(rec->>'source_date_semantics', '') AS source_date_semantics,
            NULLIF(rec->>'source_updated_at', '')::TIMESTAMPTZ AS source_updated_at,
            NULLIF(rec->>'query_window_start', '')::DATE AS query_window_start,
            NULLIF(rec->>'query_window_end', '')::DATE AS query_window_end
        FROM normalized
    ), upserted AS (
        INSERT INTO public.pncp_supplier_contracts AS target (
            contrato_id, orgao_cnpj, orgao_nome, fornecedor_cnpj, fornecedor_nome,
            supplier_id_type, supplier_identifier, supplier_country,
            supplier_identifier_hash, supplier_identifier_export, supplier_identity_reason,
            objeto_contrato, valor_total, data_inicio, data_fim, data_publicacao,
            uf, municipio, source, source_id, data_assinatura,
            data_publicacao_fonte, data_atualizacao_fonte, source_event_date,
            source_date_semantics, first_seen_at, last_seen_at, source_updated_at,
            query_window_start, query_window_end
        )
        SELECT
            input.in_contrato_id, input.orgao_cnpj, input.orgao_nome,
            input.fornecedor_cnpj, input.fornecedor_nome, input.supplier_id_type,
            input.supplier_identifier, input.supplier_country,
            input.supplier_identifier_hash, input.supplier_identifier_export,
            input.supplier_identity_reason, input.objeto_contrato, input.valor_total,
            input.data_inicio, input.data_fim, input.data_publicacao, input.uf,
            input.municipio, input.source, input.source_id, input.data_assinatura,
            input.data_publicacao_fonte, input.data_atualizacao_fonte,
            input.source_event_date, input.source_date_semantics, NOW(), NOW(),
            input.source_updated_at, input.query_window_start, input.query_window_end
        FROM input
        ON CONFLICT ON CONSTRAINT pncp_supplier_contracts_contrato_id_key DO UPDATE SET
            last_seen_at = NOW(),
            fornecedor_cnpj = EXCLUDED.fornecedor_cnpj,
            fornecedor_nome = COALESCE(EXCLUDED.fornecedor_nome, target.fornecedor_nome),
            supplier_id_type = EXCLUDED.supplier_id_type,
            supplier_identifier = EXCLUDED.supplier_identifier,
            supplier_country = EXCLUDED.supplier_country,
            supplier_identifier_hash = EXCLUDED.supplier_identifier_hash,
            supplier_identifier_export = EXCLUDED.supplier_identifier_export,
            supplier_identity_reason = EXCLUDED.supplier_identity_reason,
            data_assinatura = COALESCE(target.data_assinatura, EXCLUDED.data_assinatura),
            data_publicacao_fonte = COALESCE(target.data_publicacao_fonte, EXCLUDED.data_publicacao_fonte),
            data_atualizacao_fonte = COALESCE(target.data_atualizacao_fonte, EXCLUDED.data_atualizacao_fonte),
            source_event_date = COALESCE(target.source_event_date, EXCLUDED.source_event_date),
            source_date_semantics = COALESCE(target.source_date_semantics, EXCLUDED.source_date_semantics),
            source_updated_at = COALESCE(target.source_updated_at, EXCLUDED.source_updated_at),
            query_window_start = COALESCE(target.query_window_start, EXCLUDED.query_window_start),
            query_window_end = COALESCE(target.query_window_end, EXCLUDED.query_window_end)
        RETURNING target.contrato_id, (xmax = 0) AS is_insert
    )
    SELECT CASE WHEN upserted.is_insert THEN 'inserted' ELSE 'updated' END,
           upserted.contrato_id
    FROM upserted;
END;
$$;

DROP INDEX IF EXISTS public.idx_psc_tipo_contrato;
DROP INDEX IF EXISTS public.idx_psc_categoria_processo;
DROP INDEX IF EXISTS public.idx_psc_modalidade;
DROP INDEX IF EXISTS public.idx_psc_srp;

ALTER TABLE public.pncp_supplier_contracts
    DROP COLUMN IF EXISTS tipo_contrato_id,
    DROP COLUMN IF EXISTS tipo_contrato_nome,
    DROP COLUMN IF EXISTS categoria_processo_id,
    DROP COLUMN IF EXISTS categoria_processo_nome,
    DROP COLUMN IF EXISTS modalidade_id,
    DROP COLUMN IF EXISTS modalidade_nome,
    DROP COLUMN IF EXISTS regime_execucao_id,
    DROP COLUMN IF EXISTS regime_execucao_nome,
    DROP COLUMN IF EXISTS srp,
    DROP COLUMN IF EXISTS numero_retificacao;

-- Restore 076 upsert body (without #546 columns). Re-apply 076 function by
-- running db/migrations/076_contract_supplier_identity.sql if a full identity
-- restore is required. The column drop above is the data-loss step.

COMMIT;
