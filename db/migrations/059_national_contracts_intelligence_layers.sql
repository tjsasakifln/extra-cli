-- 059_national_contracts_intelligence_layers.sql
-- Additive analytical views for national contracts intelligence.
-- Does NOT alter dual coverage, crawlers, or fact-table write path.
-- Layer semantics: raw_national | geo_sc | intel_product (see specs/003).

-- L1 stamp view: all active national contracts
CREATE OR REPLACE VIEW public.v_intel_contracts_raw_national AS
SELECT
    c.*,
    'raw_national'::text AS scope_label
FROM public.pncp_supplier_contracts c
WHERE c.is_active = TRUE;

COMMENT ON VIEW public.v_intel_contracts_raw_national IS
'L1 national contracts inventory stamp. NOT operational SC coverage.';

-- L2 geographic SC filter (not canonical universe coverage)
CREATE OR REPLACE VIEW public.v_intel_contracts_geo_sc AS
SELECT
    c.*,
    'geo_sc'::text AS scope_label
FROM public.pncp_supplier_contracts c
WHERE c.is_active = TRUE
  AND c.uf IS NOT NULL
  AND upper(btrim(c.uf)) = 'SC';

COMMENT ON VIEW public.v_intel_contracts_geo_sc IS
'L2 geographic UF=SC filter only. MUST NOT be labeled operational coverage.';

-- L3 supplier geographic footprint
CREATE OR REPLACE VIEW public.v_intel_supplier_geo AS
SELECT
    COALESCE(c.fornecedor_cnpj_8, left(COALESCE(c.fornecedor_cnpj, ''), 8)) AS fornecedor_cnpj_8,
    MAX(c.fornecedor_cnpj) AS fornecedor_cnpj,
    MAX(c.fornecedor_nome) AS fornecedor_nome,
    COUNT(*)::bigint AS contract_count,
    COUNT(DISTINCT upper(btrim(c.uf))) FILTER (WHERE c.uf IS NOT NULL AND btrim(c.uf) <> '')::bigint AS uf_count,
    array_agg(DISTINCT upper(btrim(c.uf)) ORDER BY upper(btrim(c.uf)))
        FILTER (WHERE c.uf IS NOT NULL AND btrim(c.uf) <> '') AS ufs,
    BOOL_OR(c.uf IS NOT NULL AND upper(btrim(c.uf)) = 'SC') AS has_sc,
    COALESCE(SUM(c.valor_total), 0)::numeric(18, 2) AS valor_sum,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY c.valor_total)
        FILTER (WHERE c.valor_total IS NOT NULL) AS valor_p50,
    MIN(c.data_publicacao) AS first_publicacao,
    MAX(c.data_publicacao) AS last_publicacao,
    'intel_product'::text AS scope_label
FROM public.pncp_supplier_contracts c
WHERE c.is_active = TRUE
  AND (
        (c.fornecedor_cnpj IS NOT NULL AND btrim(c.fornecedor_cnpj) <> '')
        OR (c.fornecedor_nome IS NOT NULL AND btrim(c.fornecedor_nome) <> '')
      )
GROUP BY COALESCE(c.fornecedor_cnpj_8, left(COALESCE(c.fornecedor_cnpj, ''), 8));

COMMENT ON VIEW public.v_intel_supplier_geo IS
'L3 supplier footprint across UFs. multi-UF is FACT of contracts, not partnership.';

-- L3 agency profile aggregates
CREATE OR REPLACE VIEW public.v_intel_agency_profile AS
SELECT
    COALESCE(c.orgao_cnpj_8, left(COALESCE(c.orgao_cnpj, ''), 8)) AS orgao_cnpj_8,
    MAX(c.orgao_cnpj) AS orgao_cnpj,
    MAX(c.orgao_nome) AS orgao_nome,
    COUNT(*)::bigint AS contract_count,
    COUNT(DISTINCT COALESCE(c.fornecedor_cnpj_8, c.fornecedor_cnpj))::bigint AS supplier_count,
    COALESCE(SUM(c.valor_total), 0)::numeric(18, 2) AS valor_sum,
    AVG(c.valor_total)::numeric(18, 2) AS valor_avg,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY c.valor_total)
        FILTER (WHERE c.valor_total IS NOT NULL) AS valor_p50,
    MODE() WITHIN GROUP (ORDER BY upper(btrim(c.uf)))
        FILTER (WHERE c.uf IS NOT NULL AND btrim(c.uf) <> '') AS uf_mode,
    MIN(c.data_publicacao) AS first_publicacao,
    MAX(c.data_publicacao) AS last_publicacao,
    'intel_product'::text AS scope_label
FROM public.pncp_supplier_contracts c
WHERE c.is_active = TRUE
  AND (
        (c.orgao_cnpj IS NOT NULL AND btrim(c.orgao_cnpj) <> '')
        OR (c.orgao_nome IS NOT NULL AND btrim(c.orgao_nome) <> '')
      )
GROUP BY COALESCE(c.orgao_cnpj_8, left(COALESCE(c.orgao_cnpj, ''), 8));

COMMENT ON VIEW public.v_intel_agency_profile IS
'L3 contracting agency aggregates. Concentration metrics computed in app layer when needed.';
