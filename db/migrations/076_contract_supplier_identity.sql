-- 076_contract_supplier_identity.sql
-- Typed supplier identifiers for PNCP contracts (#311).
-- fornecedor_cnpj remains a compatibility key and may contain CNPJ only.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE OR REPLACE FUNCTION public.fn_contract_valid_cpf(value TEXT)
RETURNS BOOLEAN
LANGUAGE plpgsql
IMMUTABLE
STRICT
AS $$
DECLARE
    d TEXT := regexp_replace(value, '\D', '', 'g');
    total INTEGER;
    digit INTEGER;
    i INTEGER;
BEGIN
    IF length(d) <> 11 OR d = repeat(substr(d, 1, 1), 11) THEN
        RETURN FALSE;
    END IF;
    total := 0;
    FOR i IN 1..9 LOOP
        total := total + substr(d, i, 1)::INTEGER * (11 - i);
    END LOOP;
    digit := (total * 10) % 11;
    IF digit = 10 THEN digit := 0; END IF;
    IF digit <> substr(d, 10, 1)::INTEGER THEN RETURN FALSE; END IF;
    total := 0;
    FOR i IN 1..10 LOOP
        total := total + substr(d, i, 1)::INTEGER * (12 - i);
    END LOOP;
    digit := (total * 10) % 11;
    IF digit = 10 THEN digit := 0; END IF;
    RETURN digit = substr(d, 11, 1)::INTEGER;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_contract_valid_cnpj(value TEXT)
RETURNS BOOLEAN
LANGUAGE plpgsql
IMMUTABLE
STRICT
AS $$
DECLARE
    d TEXT := regexp_replace(value, '\D', '', 'g');
    weights1 INTEGER[] := ARRAY[5,4,3,2,9,8,7,6,5,4,3,2];
    weights2 INTEGER[] := ARRAY[6,5,4,3,2,9,8,7,6,5,4,3,2];
    total INTEGER := 0;
    remainder INTEGER;
    digit INTEGER;
    i INTEGER;
BEGIN
    IF length(d) <> 14 OR d = repeat(substr(d, 1, 1), 14) THEN
        RETURN FALSE;
    END IF;
    FOR i IN 1..12 LOOP
        total := total + substr(d, i, 1)::INTEGER * weights1[i];
    END LOOP;
    remainder := total % 11;
    digit := CASE WHEN remainder < 2 THEN 0 ELSE 11 - remainder END;
    IF digit <> substr(d, 13, 1)::INTEGER THEN RETURN FALSE; END IF;
    total := 0;
    FOR i IN 1..13 LOOP
        total := total + substr(d, i, 1)::INTEGER * weights2[i];
    END LOOP;
    remainder := total % 11;
    digit := CASE WHEN remainder < 2 THEN 0 ELSE 11 - remainder END;
    RETURN digit = substr(d, 14, 1)::INTEGER;
END;
$$;

ALTER TABLE public.pncp_supplier_contracts
    ADD COLUMN IF NOT EXISTS supplier_id_type TEXT NOT NULL DEFAULT 'UNKNOWN',
    ADD COLUMN IF NOT EXISTS supplier_identifier TEXT,
    ADD COLUMN IF NOT EXISTS supplier_country TEXT,
    ADD COLUMN IF NOT EXISTS supplier_identifier_hash TEXT,
    ADD COLUMN IF NOT EXISTS supplier_identifier_export TEXT,
    ADD COLUMN IF NOT EXISTS supplier_identity_reason TEXT NOT NULL DEFAULT 'legacy_unclassified';

WITH normalized AS (
    SELECT id, fornecedor_cnpj AS raw_identifier,
           regexp_replace(COALESCE(fornecedor_cnpj, ''), '\D', '', 'g') AS digits
    FROM public.pncp_supplier_contracts
)
UPDATE public.pncp_supplier_contracts contract
SET supplier_id_type = CASE
        WHEN public.fn_contract_valid_cnpj(normalized.digits) THEN 'CNPJ'
        WHEN public.fn_contract_valid_cpf(normalized.digits) THEN 'CPF'
        ELSE 'UNKNOWN'
    END,
    supplier_identifier = CASE
        WHEN public.fn_contract_valid_cnpj(normalized.digits) THEN normalized.digits
        WHEN public.fn_contract_valid_cpf(normalized.digits) THEN normalized.digits
        WHEN normalized.raw_identifier IS NOT NULL AND btrim(normalized.raw_identifier) <> ''
            THEN 'UNKNOWN:ZZ:' || btrim(normalized.raw_identifier)
        ELSE NULL
    END,
    supplier_country = CASE
        WHEN public.fn_contract_valid_cnpj(normalized.digits)
          OR public.fn_contract_valid_cpf(normalized.digits) THEN 'BR'
        ELSE NULL
    END,
    supplier_identifier_hash = CASE
        WHEN normalized.raw_identifier IS NULL OR btrim(normalized.raw_identifier) = '' THEN NULL
        ELSE encode(digest(
            'supplier-identity-v1:' ||
            CASE
                WHEN public.fn_contract_valid_cnpj(normalized.digits) THEN 'CNPJ:' || normalized.digits
                WHEN public.fn_contract_valid_cpf(normalized.digits) THEN 'CPF:' || normalized.digits
                ELSE 'UNKNOWN:UNKNOWN:ZZ:' || btrim(normalized.raw_identifier)
            END,
            'sha256'
        ), 'hex')
    END,
    supplier_identifier_export = CASE
        WHEN public.fn_contract_valid_cnpj(normalized.digits) THEN normalized.digits
        WHEN public.fn_contract_valid_cpf(normalized.digits) THEN 'CPF:***.***.***-**'
        WHEN length(normalized.digits) = 11 THEN 'UNKNOWN:MASKED'
        WHEN normalized.raw_identifier IS NOT NULL AND btrim(normalized.raw_identifier) <> ''
            THEN 'UNKNOWN:ZZ:' || btrim(normalized.raw_identifier)
        ELSE NULL
    END,
    supplier_identity_reason = CASE
        WHEN public.fn_contract_valid_cnpj(normalized.digits) THEN 'legacy_cnpj_valid'
        WHEN public.fn_contract_valid_cpf(normalized.digits) THEN 'legacy_cpf_valid'
        WHEN normalized.raw_identifier IS NULL OR btrim(normalized.raw_identifier) = ''
            THEN 'legacy_identifier_missing'
        ELSE 'legacy_identifier_invalid'
    END,
    fornecedor_cnpj = CASE
        WHEN public.fn_contract_valid_cnpj(normalized.digits) THEN normalized.digits
        ELSE NULL
    END
FROM normalized
WHERE normalized.id = contract.id;

ALTER TABLE public.pncp_supplier_contracts
    DROP CONSTRAINT IF EXISTS ck_contract_supplier_id_type,
    DROP CONSTRAINT IF EXISTS ck_contract_supplier_identity_consistent,
    DROP CONSTRAINT IF EXISTS ck_contract_supplier_hash;

ALTER TABLE public.pncp_supplier_contracts
    ADD CONSTRAINT ck_contract_supplier_id_type
        CHECK (supplier_id_type IN ('CNPJ', 'CPF', 'FOREIGN', 'UNKNOWN')),
    ADD CONSTRAINT ck_contract_supplier_identity_consistent CHECK ((
        (supplier_id_type = 'CNPJ'
            AND supplier_identifier IS NOT NULL
            AND public.fn_contract_valid_cnpj(supplier_identifier)
            AND fornecedor_cnpj = supplier_identifier)
        OR (supplier_id_type = 'CPF'
            AND supplier_identifier IS NOT NULL
            AND public.fn_contract_valid_cpf(supplier_identifier)
            AND fornecedor_cnpj IS NULL
            AND supplier_identifier_export = 'CPF:***.***.***-**')
        OR (supplier_id_type = 'FOREIGN'
            AND supplier_identifier IS NOT NULL
            AND supplier_identifier LIKE 'FOREIGN:%'
            AND fornecedor_cnpj IS NULL)
        OR (supplier_id_type = 'UNKNOWN' AND fornecedor_cnpj IS NULL)
    ) IS TRUE),
    ADD CONSTRAINT ck_contract_supplier_hash CHECK (
        supplier_identifier_hash IS NULL
        OR supplier_identifier_hash ~ '^[0-9a-f]{64}$'
    );

CREATE INDEX IF NOT EXISTS idx_psc_supplier_typed_identifier
    ON public.pncp_supplier_contracts (supplier_id_type, supplier_identifier);

CREATE INDEX IF NOT EXISTS idx_psc_supplier_cnpj_only
    ON public.pncp_supplier_contracts (fornecedor_cnpj, data_publicacao DESC)
    WHERE supplier_id_type = 'CNPJ';

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

COMMENT ON COLUMN public.pncp_supplier_contracts.fornecedor_cnpj IS
    'Compatibility CNPJ-only key. CPF, foreign and unknown identities are always NULL.';
COMMENT ON COLUMN public.pncp_supplier_contracts.supplier_identifier IS
    'Normalized internal identity. CPF is restricted internal data and never exported raw.';
COMMENT ON COLUMN public.pncp_supplier_contracts.supplier_identifier_export IS
    'Export-safe identity; CPF is fully masked by policy.';
COMMENT ON FUNCTION public.upsert_pncp_supplier_contracts(JSONB) IS
    'Typed supplier identity upsert (#311); legacy fornecedor_cnpj input is classified fail-closed.';

COMMIT;
