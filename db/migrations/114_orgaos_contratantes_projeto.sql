-- 114_orgaos_contratantes_projeto.sql
-- #551 F9: organs that repeatedly buy external engineering design.
-- Built only on persisted PROJETO_ENGENHARIA.

BEGIN;

CREATE OR REPLACE VIEW public.v_orgaos_contratantes_projeto AS
SELECT
    regexp_replace(COALESCE(c.orgao_cnpj, ''), '\D', '', 'g') AS orgao_cnpj,
    max(c.orgao_nome) AS orgao_nome,
    count(*) FILTER (
        WHERE coalesce(c.data_assinatura, c.data_publicacao) >= CURRENT_DATE - INTERVAL '12 months'
    ) AS n_proj_12m,
    count(*) FILTER (
        WHERE coalesce(c.data_assinatura, c.data_publicacao) >= CURRENT_DATE - INTERVAL '24 months'
    ) AS n_proj_24m,
    coalesce(sum(c.valor_total) FILTER (
        WHERE coalesce(c.data_assinatura, c.data_publicacao) >= CURRENT_DATE - INTERVAL '12 months'
    ), 0) AS v_proj_12m,
    max(coalesce(c.data_assinatura, c.data_publicacao_fonte, c.data_publicacao)) AS ultimo_contrato,
    count(DISTINCT c.fornecedor_cnpj) AS fornecedores_distintos,
    max(c.uf) AS uf,
    max(c.municipio) AS municipio,
    bool_or(entity.id IS NOT NULL) AS in_sc_public_entities
FROM public.pncp_supplier_contracts c
JOIN public.contract_engineering_class cls
    ON cls.contrato_id = c.contrato_id
   AND cls.engineering_class = 'PROJETO_ENGENHARIA'
LEFT JOIN public.sc_public_entities entity
    ON entity.cnpj_8 = left(regexp_replace(COALESCE(c.orgao_cnpj, ''), '\D', '', 'g'), 8)
   AND entity.is_active IS TRUE
WHERE regexp_replace(COALESCE(c.orgao_cnpj, ''), '\D', '', 'g') ~ '^\d{14}$'
GROUP BY 1;

COMMENT ON VIEW public.v_orgaos_contratantes_projeto IS
    'F9 organs contracting external engineering design (#551). Class = persisted PROJETO_ENGENHARIA. SC flag via sc_public_entities.';

COMMIT;
