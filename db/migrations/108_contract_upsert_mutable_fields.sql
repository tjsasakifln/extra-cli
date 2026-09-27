-- 108_contract_upsert_mutable_fields.sql
-- Refresh mutable PNCP contract fields without allowing partial or stale
-- observations to erase newer, valid values.

BEGIN;

-- apply_migrations executes statements with autocommit, so session-level SET
-- is required; SET LOCAL outside an explicit transaction would be a no-op.
SET lock_timeout = '5s';
SET statement_timeout = '120s';

CREATE OR REPLACE FUNCTION public.fn_contract_observation_not_older(
    current_source_updated_at TIMESTAMPTZ,
    current_update_date DATE,
    incoming_source_updated_at TIMESTAMPTZ,
    incoming_update_date DATE
)
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE
        WHEN COALESCE(
                 incoming_source_updated_at,
                 incoming_update_date::TIMESTAMP AT TIME ZONE 'UTC'
             ) IS NULL
            THEN COALESCE(
                     current_source_updated_at,
                     current_update_date::TIMESTAMP AT TIME ZONE 'UTC'
                 ) IS NULL
        WHEN COALESCE(
                 current_source_updated_at,
                 current_update_date::TIMESTAMP AT TIME ZONE 'UTC'
             ) IS NULL
            THEN TRUE
        ELSE COALESCE(
                 incoming_source_updated_at,
                 incoming_update_date::TIMESTAMP AT TIME ZONE 'UTC'
             ) >= COALESCE(
                 current_source_updated_at,
                 current_update_date::TIMESTAMP AT TIME ZONE 'UTC'
             )
    END;
$$;

COMMENT ON FUNCTION public.fn_contract_observation_not_older(
    TIMESTAMPTZ, DATE, TIMESTAMPTZ, DATE
) IS
    'True when an incoming PNCP contract observation may refresh mutable fields. Missing incoming freshness cannot replace a row that already has a source clock.';

CREATE OR REPLACE FUNCTION public.upsert_pncp_supplier_contracts(p_records JSONB)
RETURNS TABLE (action TEXT, contrato_id TEXT)
LANGUAGE plpgsql
AS $$
BEGIN
    IF jsonb_typeof(p_records) IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'p_records must be a JSON array'
            USING ERRCODE = '22023';
    END IF;

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
        SELECT DISTINCT ON ((candidate.rec->>'contrato_id'))
            candidate.rec,
            NULLIF(upper(btrim(candidate.rec->>'supplier_id_type')), '') AS declared_type,
            COALESCE(
                NULLIF(btrim(candidate.rec->>'supplier_identifier'), ''),
                NULLIF(btrim(candidate.rec->>'fornecedor_cnpj'), '')
            ) AS raw_identifier,
            regexp_replace(
                COALESCE(
                    NULLIF(btrim(candidate.rec->>'supplier_identifier'), ''),
                    NULLIF(btrim(candidate.rec->>'fornecedor_cnpj'), ''),
                    ''
                ),
                '\D', '', 'g'
            ) AS identifier_digits
        FROM jsonb_array_elements(p_records) WITH ORDINALITY AS candidate(rec, ordinal)
        WHERE NULLIF(btrim(candidate.rec->>'contrato_id'), '') IS NOT NULL
        ORDER BY
            (candidate.rec->>'contrato_id'),
            NULLIF(candidate.rec->>'source_updated_at', '')::TIMESTAMPTZ DESC NULLS LAST,
            NULLIF(candidate.rec->>'data_atualizacao_fonte', '')::DATE DESC NULLS LAST,
            candidate.ordinal DESC
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
            btrim(rec->>'contrato_id') AS in_contrato_id,
            NULLIF(btrim(rec->>'orgao_cnpj'), '') AS orgao_cnpj,
            NULLIF(btrim(rec->>'orgao_nome'), '') AS orgao_nome,
            CASE
                WHEN canonical_type = 'CNPJ'
                    AND public.fn_contract_valid_cnpj(canonical_identifier)
                    THEN canonical_identifier
                ELSE NULL
            END AS fornecedor_cnpj,
            NULLIF(btrim(rec->>'fornecedor_nome'), '') AS fornecedor_nome,
            canonical_type AS supplier_id_type,
            canonical_identifier AS supplier_identifier,
            COALESCE(
                NULLIF(btrim(rec->>'supplier_country'), ''),
                CASE WHEN canonical_type IN ('CNPJ', 'CPF') THEN 'BR' ELSE NULL END
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
            CASE
                WHEN canonical_identifier IS NULL THEN NULL
                ELSE COALESCE(
                    NULLIF(btrim(rec->>'supplier_identity_reason'), ''),
                    CASE
                        WHEN declared_type IS NULL THEN 'legacy_rpc_classified'
                        ELSE 'rpc_server_normalized'
                    END
                )
            END AS supplier_identity_reason,
            NULLIF(btrim(rec->>'objeto_contrato'), '') AS objeto_contrato,
            NULLIF(rec->>'valor_total', '')::NUMERIC AS valor_total,
            NULLIF(rec->>'data_inicio', '')::DATE AS data_inicio,
            NULLIF(rec->>'data_fim', '')::DATE AS data_fim,
            NULLIF(rec->>'data_publicacao', '')::DATE AS data_publicacao,
            NULLIF(btrim(rec->>'uf'), '') AS uf,
            NULLIF(btrim(rec->>'municipio'), '') AS municipio,
            COALESCE(NULLIF(btrim(rec->>'source'), ''), 'pncp') AS source,
            NULLIF(btrim(rec->>'source_id'), '') AS source_id,
            NULLIF(rec->>'data_assinatura', '')::DATE AS data_assinatura,
            NULLIF(rec->>'data_publicacao_fonte', '')::DATE AS data_publicacao_fonte,
            NULLIF(rec->>'data_atualizacao_fonte', '')::DATE AS data_atualizacao_fonte,
            NULLIF(rec->>'source_event_date', '')::DATE AS source_event_date,
            NULLIF(btrim(rec->>'source_date_semantics'), '') AS source_date_semantics,
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
            COALESCE(input.supplier_identity_reason, 'legacy_unclassified'),
            input.objeto_contrato, input.valor_total, input.data_inicio, input.data_fim,
            input.data_publicacao, input.uf, input.municipio, input.source,
            input.source_id, input.data_assinatura, input.data_publicacao_fonte,
            input.data_atualizacao_fonte, input.source_event_date,
            input.source_date_semantics, NOW(), NOW(), input.source_updated_at,
            input.query_window_start, input.query_window_end
        FROM input
        ON CONFLICT ON CONSTRAINT pncp_supplier_contracts_contrato_id_key DO UPDATE SET
            last_seen_at = CASE
                WHEN target.last_seen_at IS NULL OR NOW() > target.last_seen_at THEN NOW()
                ELSE target.last_seen_at
            END,
            orgao_cnpj = CASE WHEN public.fn_contract_observation_not_older(
                target.source_updated_at, target.data_atualizacao_fonte,
                EXCLUDED.source_updated_at, EXCLUDED.data_atualizacao_fonte
            ) THEN COALESCE(EXCLUDED.orgao_cnpj, target.orgao_cnpj) ELSE target.orgao_cnpj END,
            orgao_nome = CASE WHEN public.fn_contract_observation_not_older(
                target.source_updated_at, target.data_atualizacao_fonte,
                EXCLUDED.source_updated_at, EXCLUDED.data_atualizacao_fonte
            ) THEN COALESCE(EXCLUDED.orgao_nome, target.orgao_nome) ELSE target.orgao_nome END,
            fornecedor_nome = CASE WHEN public.fn_contract_observation_not_older(
                target.source_updated_at, target.data_atualizacao_fonte,
                EXCLUDED.source_updated_at, EXCLUDED.data_atualizacao_fonte
            ) THEN COALESCE(EXCLUDED.fornecedor_nome, target.fornecedor_nome) ELSE target.fornecedor_nome END,
            fornecedor_cnpj = CASE
                WHEN public.fn_contract_observation_not_older(
                    target.source_updated_at, target.data_atualizacao_fonte,
                    EXCLUDED.source_updated_at, EXCLUDED.data_atualizacao_fonte
                ) AND EXCLUDED.supplier_identifier IS NOT NULL
                    THEN EXCLUDED.fornecedor_cnpj
                ELSE target.fornecedor_cnpj
            END,
            supplier_id_type = CASE
                WHEN public.fn_contract_observation_not_older(
                    target.source_updated_at, target.data_atualizacao_fonte,
                    EXCLUDED.source_updated_at, EXCLUDED.data_atualizacao_fonte
                ) AND EXCLUDED.supplier_identifier IS NOT NULL
                    THEN EXCLUDED.supplier_id_type
                ELSE target.supplier_id_type
            END,
            supplier_identifier = CASE
                WHEN public.fn_contract_observation_not_older(
                    target.source_updated_at, target.data_atualizacao_fonte,
                    EXCLUDED.source_updated_at, EXCLUDED.data_atualizacao_fonte
                ) AND EXCLUDED.supplier_identifier IS NOT NULL
                    THEN EXCLUDED.supplier_identifier
                ELSE target.supplier_identifier
            END,
            supplier_country = CASE
                WHEN public.fn_contract_observation_not_older(
                    target.source_updated_at, target.data_atualizacao_fonte,
                    EXCLUDED.source_updated_at, EXCLUDED.data_atualizacao_fonte
                ) AND EXCLUDED.supplier_identifier IS NOT NULL
                    THEN EXCLUDED.supplier_country
                ELSE target.supplier_country
            END,
            supplier_identifier_hash = CASE
                WHEN public.fn_contract_observation_not_older(
                    target.source_updated_at, target.data_atualizacao_fonte,
                    EXCLUDED.source_updated_at, EXCLUDED.data_atualizacao_fonte
                ) AND EXCLUDED.supplier_identifier IS NOT NULL
                    THEN EXCLUDED.supplier_identifier_hash
                ELSE target.supplier_identifier_hash
            END,
            supplier_identifier_export = CASE
                WHEN public.fn_contract_observation_not_older(
                    target.source_updated_at, target.data_atualizacao_fonte,
                    EXCLUDED.source_updated_at, EXCLUDED.data_atualizacao_fonte
                ) AND EXCLUDED.supplier_identifier IS NOT NULL
                    THEN EXCLUDED.supplier_identifier_export
                ELSE target.supplier_identifier_export
            END,
            supplier_identity_reason = CASE
                WHEN public.fn_contract_observation_not_older(
                    target.source_updated_at, target.data_atualizacao_fonte,
                    EXCLUDED.source_updated_at, EXCLUDED.data_atualizacao_fonte
                ) AND EXCLUDED.supplier_identifier IS NOT NULL
                    THEN EXCLUDED.supplier_identity_reason
                ELSE target.supplier_identity_reason
            END,
            objeto_contrato = CASE WHEN public.fn_contract_observation_not_older(
                target.source_updated_at, target.data_atualizacao_fonte,
                EXCLUDED.source_updated_at, EXCLUDED.data_atualizacao_fonte
            ) THEN COALESCE(EXCLUDED.objeto_contrato, target.objeto_contrato) ELSE target.objeto_contrato END,
            valor_total = CASE WHEN public.fn_contract_observation_not_older(
                target.source_updated_at, target.data_atualizacao_fonte,
                EXCLUDED.source_updated_at, EXCLUDED.data_atualizacao_fonte
            ) THEN COALESCE(EXCLUDED.valor_total, target.valor_total) ELSE target.valor_total END,
            data_inicio = CASE WHEN public.fn_contract_observation_not_older(
                target.source_updated_at, target.data_atualizacao_fonte,
                EXCLUDED.source_updated_at, EXCLUDED.data_atualizacao_fonte
            ) THEN COALESCE(EXCLUDED.data_inicio, target.data_inicio) ELSE target.data_inicio END,
            data_fim = CASE WHEN public.fn_contract_observation_not_older(
                target.source_updated_at, target.data_atualizacao_fonte,
                EXCLUDED.source_updated_at, EXCLUDED.data_atualizacao_fonte
            ) THEN COALESCE(EXCLUDED.data_fim, target.data_fim) ELSE target.data_fim END,
            data_publicacao = CASE WHEN public.fn_contract_observation_not_older(
                target.source_updated_at, target.data_atualizacao_fonte,
                EXCLUDED.source_updated_at, EXCLUDED.data_atualizacao_fonte
            ) THEN COALESCE(EXCLUDED.data_publicacao, target.data_publicacao) ELSE target.data_publicacao END,
            uf = CASE WHEN public.fn_contract_observation_not_older(
                target.source_updated_at, target.data_atualizacao_fonte,
                EXCLUDED.source_updated_at, EXCLUDED.data_atualizacao_fonte
            ) THEN COALESCE(EXCLUDED.uf, target.uf) ELSE target.uf END,
            municipio = CASE WHEN public.fn_contract_observation_not_older(
                target.source_updated_at, target.data_atualizacao_fonte,
                EXCLUDED.source_updated_at, EXCLUDED.data_atualizacao_fonte
            ) THEN COALESCE(EXCLUDED.municipio, target.municipio) ELSE target.municipio END,
            source = CASE WHEN public.fn_contract_observation_not_older(
                target.source_updated_at, target.data_atualizacao_fonte,
                EXCLUDED.source_updated_at, EXCLUDED.data_atualizacao_fonte
            ) THEN COALESCE(EXCLUDED.source, target.source) ELSE target.source END,
            source_id = CASE WHEN public.fn_contract_observation_not_older(
                target.source_updated_at, target.data_atualizacao_fonte,
                EXCLUDED.source_updated_at, EXCLUDED.data_atualizacao_fonte
            ) THEN COALESCE(EXCLUDED.source_id, target.source_id) ELSE target.source_id END,
            data_assinatura = CASE WHEN public.fn_contract_observation_not_older(
                target.source_updated_at, target.data_atualizacao_fonte,
                EXCLUDED.source_updated_at, EXCLUDED.data_atualizacao_fonte
            ) THEN COALESCE(EXCLUDED.data_assinatura, target.data_assinatura) ELSE target.data_assinatura END,
            data_publicacao_fonte = CASE WHEN public.fn_contract_observation_not_older(
                target.source_updated_at, target.data_atualizacao_fonte,
                EXCLUDED.source_updated_at, EXCLUDED.data_atualizacao_fonte
            ) THEN COALESCE(EXCLUDED.data_publicacao_fonte, target.data_publicacao_fonte) ELSE target.data_publicacao_fonte END,
            source_event_date = CASE WHEN public.fn_contract_observation_not_older(
                target.source_updated_at, target.data_atualizacao_fonte,
                EXCLUDED.source_updated_at, EXCLUDED.data_atualizacao_fonte
            ) THEN COALESCE(EXCLUDED.source_event_date, target.source_event_date) ELSE target.source_event_date END,
            source_date_semantics = CASE WHEN public.fn_contract_observation_not_older(
                target.source_updated_at, target.data_atualizacao_fonte,
                EXCLUDED.source_updated_at, EXCLUDED.data_atualizacao_fonte
            ) THEN COALESCE(EXCLUDED.source_date_semantics, target.source_date_semantics) ELSE target.source_date_semantics END,
            data_atualizacao_fonte = CASE
                WHEN EXCLUDED.data_atualizacao_fonte IS NULL THEN target.data_atualizacao_fonte
                WHEN target.data_atualizacao_fonte IS NULL
                  OR EXCLUDED.data_atualizacao_fonte > target.data_atualizacao_fonte
                    THEN EXCLUDED.data_atualizacao_fonte
                ELSE target.data_atualizacao_fonte
            END,
            source_updated_at = CASE
                WHEN EXCLUDED.source_updated_at IS NULL THEN target.source_updated_at
                WHEN target.source_updated_at IS NULL
                  OR EXCLUDED.source_updated_at > target.source_updated_at
                    THEN EXCLUDED.source_updated_at
                ELSE target.source_updated_at
            END,
            query_window_start = CASE
                WHEN EXCLUDED.query_window_end IS NOT NULL
                 AND (target.query_window_end IS NULL OR EXCLUDED.query_window_end >= target.query_window_end)
                    THEN COALESCE(EXCLUDED.query_window_start, target.query_window_start)
                ELSE target.query_window_start
            END,
            query_window_end = CASE
                WHEN EXCLUDED.query_window_end IS NULL THEN target.query_window_end
                WHEN target.query_window_end IS NULL OR EXCLUDED.query_window_end > target.query_window_end
                    THEN EXCLUDED.query_window_end
                ELSE target.query_window_end
            END
        RETURNING target.contrato_id, (xmax = 0) AS is_insert
    )
    SELECT CASE WHEN upserted.is_insert THEN 'inserted' ELSE 'updated' END,
           upserted.contrato_id
    FROM upserted;
END;
$$;

COMMENT ON FUNCTION public.upsert_pncp_supplier_contracts(JSONB) IS
    'Batch upsert by contrato_id. 108 refreshes mutable fields from non-older source observations, preserves valid values on partial payloads, derives supplier security fields server-side, and advances observation freshness monotonically.';

RESET lock_timeout;
RESET statement_timeout;

COMMIT;
