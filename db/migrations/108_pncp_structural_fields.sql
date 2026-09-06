-- 108_pncp_structural_fields.sql
-- #546: persist official PNCP structural fields (not inferred from objeto).
-- Additive columns + upsert persist + canonical v2 expose + resumable backfill RPC.
--
-- ROLLBACK:
--   psql "$LOCAL_DATALAKE_DSN" -f db/rollback/108_pncp_structural_fields_rollback.sql
--
-- Authority: scripts/crawl/pncp_structural_fields.py maps the PNCP payload;
-- this migration persists those mapped keys. Do not re-derive from objeto.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

ALTER TABLE public.pncp_supplier_contracts
    ADD COLUMN IF NOT EXISTS tipo_contrato_id INTEGER,
    ADD COLUMN IF NOT EXISTS tipo_contrato_nome TEXT,
    ADD COLUMN IF NOT EXISTS categoria_processo_id INTEGER,
    ADD COLUMN IF NOT EXISTS categoria_processo_nome TEXT,
    ADD COLUMN IF NOT EXISTS modalidade_id INTEGER,
    ADD COLUMN IF NOT EXISTS modalidade_nome TEXT,
    ADD COLUMN IF NOT EXISTS regime_execucao_id INTEGER,
    ADD COLUMN IF NOT EXISTS regime_execucao_nome TEXT,
    ADD COLUMN IF NOT EXISTS srp BOOLEAN,
    ADD COLUMN IF NOT EXISTS numero_retificacao INTEGER;

CREATE INDEX IF NOT EXISTS idx_psc_tipo_contrato
    ON public.pncp_supplier_contracts (tipo_contrato_id)
    WHERE tipo_contrato_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_psc_categoria_processo
    ON public.pncp_supplier_contracts (categoria_processo_id)
    WHERE categoria_processo_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_psc_modalidade
    ON public.pncp_supplier_contracts (modalidade_id)
    WHERE modalidade_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_psc_srp
    ON public.pncp_supplier_contracts (srp)
    WHERE srp IS TRUE;

COMMENT ON COLUMN public.pncp_supplier_contracts.tipo_contrato_id IS
    'Official PNCP tipoContrato id (contrato, empenho, carta contrato). Not inferred from objeto. #546.';
COMMENT ON COLUMN public.pncp_supplier_contracts.tipo_contrato_nome IS
    'Official PNCP tipoContrato nome. Not inferred from objeto. #546.';
COMMENT ON COLUMN public.pncp_supplier_contracts.categoria_processo_id IS
    'Official PNCP categoriaProcesso id (obras, servicos de engenharia, compras). #546.';
COMMENT ON COLUMN public.pncp_supplier_contracts.categoria_processo_nome IS
    'Official PNCP categoriaProcesso nome. #546.';
COMMENT ON COLUMN public.pncp_supplier_contracts.modalidade_id IS
    'Official PNCP modalidade id from the contract or parent compra payload. #546.';
COMMENT ON COLUMN public.pncp_supplier_contracts.modalidade_nome IS
    'Official PNCP modalidade nome. #546.';
COMMENT ON COLUMN public.pncp_supplier_contracts.regime_execucao_id IS
    'Official PNCP codigoRegimeExecucao when present on the payload. #546.';
COMMENT ON COLUMN public.pncp_supplier_contracts.regime_execucao_nome IS
    'Official PNCP regimeExecucao nome (integrada/semi-integrada/etc.). #546.';
COMMENT ON COLUMN public.pncp_supplier_contracts.srp IS
    'Official PNCP SRP / registro de precos flag from the payload, not from objeto text. #546.';
COMMENT ON COLUMN public.pncp_supplier_contracts.numero_retificacao IS
    'Official PNCP numeroRetificacao. #546.';

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
            NULLIF(rec->>'query_window_end', '')::DATE AS query_window_end,
            NULLIF(rec->>'tipo_contrato_id', '')::INTEGER AS tipo_contrato_id,
            NULLIF(btrim(rec->>'tipo_contrato_nome'), '') AS tipo_contrato_nome,
            NULLIF(rec->>'categoria_processo_id', '')::INTEGER AS categoria_processo_id,
            NULLIF(btrim(rec->>'categoria_processo_nome'), '') AS categoria_processo_nome,
            NULLIF(rec->>'modalidade_id', '')::INTEGER AS modalidade_id,
            NULLIF(btrim(rec->>'modalidade_nome'), '') AS modalidade_nome,
            NULLIF(rec->>'regime_execucao_id', '')::INTEGER AS regime_execucao_id,
            NULLIF(btrim(rec->>'regime_execucao_nome'), '') AS regime_execucao_nome,
            CASE
                WHEN rec->>'srp' IS NULL OR btrim(rec->>'srp') = '' THEN NULL
                WHEN lower(rec->>'srp') IN ('true', 't', '1') THEN TRUE
                WHEN lower(rec->>'srp') IN ('false', 'f', '0') THEN FALSE
                ELSE NULL
            END AS srp,
            NULLIF(rec->>'numero_retificacao', '')::INTEGER AS numero_retificacao
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
            query_window_start, query_window_end,
            tipo_contrato_id, tipo_contrato_nome, categoria_processo_id, categoria_processo_nome,
            modalidade_id, modalidade_nome, regime_execucao_id, regime_execucao_nome,
            srp, numero_retificacao
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
            input.source_updated_at, input.query_window_start, input.query_window_end,
            input.tipo_contrato_id, input.tipo_contrato_nome,
            input.categoria_processo_id, input.categoria_processo_nome,
            input.modalidade_id, input.modalidade_nome,
            input.regime_execucao_id, input.regime_execucao_nome,
            input.srp, input.numero_retificacao
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
            query_window_end = COALESCE(target.query_window_end, EXCLUDED.query_window_end),
            tipo_contrato_id = COALESCE(EXCLUDED.tipo_contrato_id, target.tipo_contrato_id),
            tipo_contrato_nome = COALESCE(EXCLUDED.tipo_contrato_nome, target.tipo_contrato_nome),
            categoria_processo_id = COALESCE(EXCLUDED.categoria_processo_id, target.categoria_processo_id),
            categoria_processo_nome = COALESCE(EXCLUDED.categoria_processo_nome, target.categoria_processo_nome),
            modalidade_id = COALESCE(EXCLUDED.modalidade_id, target.modalidade_id),
            modalidade_nome = COALESCE(EXCLUDED.modalidade_nome, target.modalidade_nome),
            regime_execucao_id = COALESCE(EXCLUDED.regime_execucao_id, target.regime_execucao_id),
            regime_execucao_nome = COALESCE(EXCLUDED.regime_execucao_nome, target.regime_execucao_nome),
            srp = COALESCE(EXCLUDED.srp, target.srp),
            numero_retificacao = COALESCE(EXCLUDED.numero_retificacao, target.numero_retificacao)
        RETURNING target.contrato_id, (xmax = 0) AS is_insert
    )
    SELECT CASE WHEN upserted.is_insert THEN 'inserted' ELSE 'updated' END,
           upserted.contrato_id
    FROM upserted;
END;
$$;

COMMENT ON FUNCTION public.upsert_pncp_supplier_contracts(JSONB) IS
    'Typed supplier identity upsert (#311) plus official PNCP structural fields (#546).';

CREATE OR REPLACE FUNCTION public.apply_pncp_structural_fields(p_records JSONB)
RETURNS TABLE (action TEXT, contrato_id TEXT)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH input AS (
        SELECT DISTINCT ON (rec->>'contrato_id')
            rec->>'contrato_id' AS in_contrato_id,
            NULLIF(rec->>'tipo_contrato_id', '')::INTEGER AS tipo_contrato_id,
            NULLIF(btrim(rec->>'tipo_contrato_nome'), '') AS tipo_contrato_nome,
            NULLIF(rec->>'categoria_processo_id', '')::INTEGER AS categoria_processo_id,
            NULLIF(btrim(rec->>'categoria_processo_nome'), '') AS categoria_processo_nome,
            NULLIF(rec->>'modalidade_id', '')::INTEGER AS modalidade_id,
            NULLIF(btrim(rec->>'modalidade_nome'), '') AS modalidade_nome,
            NULLIF(rec->>'regime_execucao_id', '')::INTEGER AS regime_execucao_id,
            NULLIF(btrim(rec->>'regime_execucao_nome'), '') AS regime_execucao_nome,
            CASE
                WHEN rec->>'srp' IS NULL OR btrim(rec->>'srp') = '' THEN NULL
                WHEN lower(rec->>'srp') IN ('true', 't', '1') THEN TRUE
                WHEN lower(rec->>'srp') IN ('false', 'f', '0') THEN FALSE
                ELSE NULL
            END AS srp,
            NULLIF(rec->>'numero_retificacao', '')::INTEGER AS numero_retificacao
        FROM jsonb_array_elements(p_records) AS rec
        WHERE COALESCE(rec->>'contrato_id', '') <> ''
        ORDER BY rec->>'contrato_id'
    ), updated AS (
        UPDATE public.pncp_supplier_contracts AS target
        SET tipo_contrato_id = COALESCE(input.tipo_contrato_id, target.tipo_contrato_id),
            tipo_contrato_nome = COALESCE(input.tipo_contrato_nome, target.tipo_contrato_nome),
            categoria_processo_id = COALESCE(input.categoria_processo_id, target.categoria_processo_id),
            categoria_processo_nome = COALESCE(input.categoria_processo_nome, target.categoria_processo_nome),
            modalidade_id = COALESCE(input.modalidade_id, target.modalidade_id),
            modalidade_nome = COALESCE(input.modalidade_nome, target.modalidade_nome),
            regime_execucao_id = COALESCE(input.regime_execucao_id, target.regime_execucao_id),
            regime_execucao_nome = COALESCE(input.regime_execucao_nome, target.regime_execucao_nome),
            srp = COALESCE(input.srp, target.srp),
            numero_retificacao = COALESCE(input.numero_retificacao, target.numero_retificacao)
        FROM input
        WHERE target.contrato_id = input.in_contrato_id
        RETURNING target.contrato_id
    )
    SELECT 'updated'::TEXT, updated.contrato_id
    FROM updated;
END;
$$;

COMMENT ON FUNCTION public.apply_pncp_structural_fields(JSONB) IS
    'Idempotent backfill of official PNCP structural fields onto existing contracts (#546).';

CREATE TABLE IF NOT EXISTS public.pncp_structural_fields_backfill_state (
    run_id          TEXT PRIMARY KEY,
    cursor_contrato_id TEXT,
    processed       BIGINT NOT NULL DEFAULT 0,
    updated         BIGINT NOT NULL DEFAULT 0,
    skipped         BIGINT NOT NULL DEFAULT 0,
    last_run_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes           TEXT
);

COMMENT ON TABLE public.pncp_structural_fields_backfill_state IS
    'Resumable cursor for #546 structural-field backfill. Observability only.';

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
    roles.matched_at,
    contract.tipo_contrato_id,
    contract.tipo_contrato_nome,
    contract.categoria_processo_id,
    contract.categoria_processo_nome,
    contract.modalidade_id,
    contract.modalidade_nome,
    COALESCE(contract.regime_execucao_nome, contract.regime_execucao_id::TEXT) AS regime_execucao,
    contract.srp,
    contract.numero_retificacao
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
    contract.modalidade_id,
    contract.modalidade_nome AS modalidade,
    contract.objeto,
    contract.valor,
    contract.data_publicacao,
    contract.buyer_entity_cnpj_8,
    contract.buyer_within_200km
FROM public.v_contracts_canonical_v2 contract
WHERE contract.valor IS NOT NULL AND contract.valor > 0;

COMMENT ON VIEW public.v_contracts_canonical_v2 IS
    'Canonical contracts v2: buyer from orgao_cnpj only; supplier is a distinct typed identity; official PNCP structural fields from #546.';

COMMIT;
