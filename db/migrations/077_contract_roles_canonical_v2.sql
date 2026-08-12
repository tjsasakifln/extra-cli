-- 077_contract_roles_canonical_v2.sql
-- Correct buyer/supplier roles in canonical contracts (#313).
-- Depends on 061 (canonical linkage) and 076 (typed supplier identity).

BEGIN;

CREATE TABLE IF NOT EXISTS public.contract_role_links (
    contract_id                 TEXT PRIMARY KEY
                                    REFERENCES public.pncp_supplier_contracts(contrato_id)
                                    ON DELETE CASCADE,
    buyer_entity_id             BIGINT REFERENCES public.sc_public_entities(id),
    supplier_identity_id        TEXT,
    buyer_match_method          TEXT NOT NULL,
    buyer_match_confidence      NUMERIC(6,5) NOT NULL
                                    CHECK (buyer_match_confidence BETWEEN 0 AND 1),
    buyer_reason_codes          TEXT[] NOT NULL DEFAULT '{}',
    supplier_match_method       TEXT NOT NULL,
    supplier_match_confidence   NUMERIC(6,5) NOT NULL
                                    CHECK (supplier_match_confidence BETWEEN 0 AND 1),
    supplier_reason_codes       TEXT[] NOT NULL DEFAULT '{}',
    match_run_id                TEXT NOT NULL,
    snapshot_id                 TEXT NOT NULL,
    matched_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_contract_roles_buyer
    ON public.contract_role_links (buyer_entity_id, contract_id);
CREATE INDEX IF NOT EXISTS idx_contract_roles_supplier
    ON public.contract_role_links (supplier_identity_id, contract_id)
    WHERE supplier_identity_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_contract_roles_snapshot
    ON public.contract_role_links (snapshot_id, contract_id);
CREATE INDEX IF NOT EXISTS idx_contract_roles_run
    ON public.contract_role_links (match_run_id, contract_id);

CREATE INDEX IF NOT EXISTS idx_psc_orgao_root_contract
    ON public.pncp_supplier_contracts (
        (left(regexp_replace(COALESCE(orgao_cnpj, ''), '\D', '', 'g'), 8)),
        contrato_id
    );

CREATE OR REPLACE FUNCTION public.fn_refresh_contract_role_link(
    p_contract_id TEXT,
    p_match_run_id TEXT,
    p_snapshot_id TEXT DEFAULT NULL
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO public.contract_role_links (
        contract_id, buyer_entity_id, supplier_identity_id,
        buyer_match_method, buyer_match_confidence, buyer_reason_codes,
        supplier_match_method, supplier_match_confidence, supplier_reason_codes,
        match_run_id, snapshot_id, matched_at
    )
    SELECT
        contract.contrato_id,
        buyer.id,
        CASE
            WHEN contract.supplier_identifier_hash IS NOT NULL
            THEN 'supplier:' || lower(contract.supplier_id_type) || ':' ||
                 contract.supplier_identifier_hash
            ELSE NULL
        END,
        CASE WHEN buyer.id IS NOT NULL THEN 'orgao_cnpj8_exact' ELSE 'unresolved' END,
        CASE WHEN buyer.id IS NOT NULL THEN 1.0 ELSE 0.0 END,
        CASE
            WHEN buyer.id IS NOT NULL THEN ARRAY['BUYER_ORGAO_CNPJ8_EXACT']::TEXT[]
            WHEN COALESCE(contract.orgao_cnpj, '') = ''
                THEN ARRAY['BUYER_ORGAO_CNPJ_MISSING']::TEXT[]
            ELSE ARRAY['BUYER_ORGAO_NOT_IN_ENTITY_UNIVERSE']::TEXT[]
        END,
        CASE
            WHEN contract.supplier_identifier_hash IS NOT NULL
                 AND contract.supplier_id_type IN ('CNPJ', 'CPF', 'FOREIGN')
                THEN 'typed_identifier_sha256'
            WHEN contract.supplier_identifier_hash IS NOT NULL
                THEN 'typed_identifier_sha256_unknown_type'
            ELSE 'unresolved'
        END,
        CASE
            WHEN contract.supplier_identifier_hash IS NOT NULL
                 AND contract.supplier_id_type IN ('CNPJ', 'CPF', 'FOREIGN') THEN 1.0
            WHEN contract.supplier_identifier_hash IS NOT NULL THEN 0.5
            ELSE 0.0
        END,
        CASE
            WHEN contract.supplier_identifier_hash IS NOT NULL
                 AND contract.supplier_id_type IN ('CNPJ', 'CPF', 'FOREIGN')
                THEN ARRAY['SUPPLIER_TYPED_IDENTITY_VALIDATED']::TEXT[]
            WHEN contract.supplier_identifier_hash IS NOT NULL
                THEN ARRAY['SUPPLIER_IDENTITY_UNTYPED']::TEXT[]
            ELSE ARRAY['SUPPLIER_IDENTITY_UNRESOLVED']::TEXT[]
        END,
        p_match_run_id,
        COALESCE(
            NULLIF(p_snapshot_id, ''),
            contract.query_window_end::TEXT,
            contract.data_publicacao_fonte::TEXT,
            contract.data_publicacao::TEXT,
            contract.last_seen_at::TEXT,
            'unknown'
        ),
        now()
    FROM public.pncp_supplier_contracts contract
    LEFT JOIN LATERAL (
        SELECT entity.id
        FROM public.sc_public_entities entity
        WHERE entity.cnpj_8 = left(
            regexp_replace(COALESCE(contract.orgao_cnpj, ''), '\D', '', 'g'), 8
        )
        ORDER BY entity.id
        LIMIT 1
    ) buyer ON TRUE
    WHERE contract.contrato_id = p_contract_id
    ON CONFLICT (contract_id) DO UPDATE SET
        buyer_entity_id = EXCLUDED.buyer_entity_id,
        supplier_identity_id = EXCLUDED.supplier_identity_id,
        buyer_match_method = EXCLUDED.buyer_match_method,
        buyer_match_confidence = EXCLUDED.buyer_match_confidence,
        buyer_reason_codes = EXCLUDED.buyer_reason_codes,
        supplier_match_method = EXCLUDED.supplier_match_method,
        supplier_match_confidence = EXCLUDED.supplier_match_confidence,
        supplier_reason_codes = EXCLUDED.supplier_reason_codes,
        match_run_id = EXCLUDED.match_run_id,
        snapshot_id = EXCLUDED.snapshot_id,
        matched_at = now();
END;
$$;

CREATE OR REPLACE FUNCTION public.trg_refresh_contract_role_link()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    configured_run_id TEXT;
BEGIN
    configured_run_id := NULLIF(current_setting('extra.contract_role_run_id', TRUE), '');
    PERFORM public.fn_refresh_contract_role_link(
        NEW.contrato_id,
        COALESCE(
            configured_run_id,
            'ingest:' || COALESCE(NULLIF(NEW.source, ''), 'unknown') || ':' ||
            COALESCE(NULLIF(NEW.source_id, ''), NEW.contrato_id)
        ),
        NULL
    );
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_contract_role_link
    ON public.pncp_supplier_contracts;
CREATE TRIGGER trg_contract_role_link
    AFTER INSERT OR UPDATE OF orgao_cnpj, supplier_id_type,
        supplier_identifier_hash, source_id, query_window_end
    ON public.pncp_supplier_contracts
    FOR EACH ROW EXECUTE FUNCTION public.trg_refresh_contract_role_link();

SELECT public.fn_refresh_contract_role_link(
    contract.contrato_id,
    'migration-077-contract-role-backfill',
    NULL
)
FROM public.pncp_supplier_contracts contract
WHERE contract.contrato_id IS NOT NULL;

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

COMMENT ON VIEW public.v_contracts_canonical_v2 IS
    'Canonical contracts v2: buyer from orgao_cnpj only; supplier is a distinct typed identity. Use for #291/#292 and all new consumers.';
COMMENT ON VIEW public.v_contracts_canonical IS
    'DEPRECATED v1: role-ambiguous historical compatibility only. New consumers must use v_contracts_canonical_v2.';
COMMENT ON VIEW public.v_value_observations_canonical_v2 IS
    'Value observations v2: contract entity fields always represent the buyer resolved from orgao_cnpj.';
COMMENT ON VIEW public.v_value_observations_canonical IS
    'DEPRECATED v1: contract entity role may be supplier-derived. Use v_value_observations_canonical_v2.';
COMMENT ON TABLE public.contract_role_links IS
    'One auditable buyer/supplier role match per contract, including method, confidence, reason codes, run and snapshot.';

COMMIT;
