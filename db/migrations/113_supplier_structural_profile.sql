-- 113_supplier_structural_profile.sql
-- #547: daily F1–F8 supplier structural profile. Consumes persisted class (#544).

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '180s';

CREATE MATERIALIZED VIEW IF NOT EXISTS public.mv_supplier_structural_profile AS
SELECT
    regexp_replace(COALESCE(c.fornecedor_cnpj, ''), '\D', '', 'g') AS fornecedor_cnpj,
    count(*) AS n_contracts,
    coalesce(sum(c.valor_total), 0) AS v_total,
    min(coalesce(c.data_assinatura, c.data_publicacao_fonte, c.data_publicacao)) AS first_sig,
    max(coalesce(c.data_assinatura, c.data_publicacao_fonte, c.data_publicacao)) AS last_sig,
    count(DISTINCT c.orgao_cnpj) AS n_orgaos,
    array_agg(DISTINCT c.uf) FILTER (WHERE c.uf IS NOT NULL) AS ufs,
    count(*) FILTER (
        WHERE c.status_normalized = 'ACTIVE_PROVEN'
           OR (c.data_fim IS NOT NULL AND c.data_fim >= CURRENT_DATE)
    ) AS n_active,
    coalesce(sum(c.valor_total) FILTER (
        WHERE c.status_normalized = 'ACTIVE_PROVEN'
           OR (c.data_fim IS NOT NULL AND c.data_fim >= CURRENT_DATE)
    ), 0) AS v_active,
    max(c.valor_total) AS v_max,
    count(*) FILTER (
        WHERE cls.engineering_class = 'PROJETO_ENGENHARIA'
          AND coalesce(c.data_assinatura, c.data_publicacao) >= CURRENT_DATE - INTERVAL '24 months'
    ) AS n_proj_24m,
    count(*) FILTER (
        WHERE cls.engineering_class = 'PROJETO_ENGENHARIA'
          AND coalesce(c.data_assinatura, c.data_publicacao) >= CURRENT_DATE - INTERVAL '12 months'
    ) AS n_proj_12m,
    count(*) FILTER (
        WHERE cls.engineering_class IN ('OBRA_EXECUCAO', 'OBRA_COM_PROJETO')
          AND coalesce(c.data_assinatura, c.data_publicacao) >= CURRENT_DATE - INTERVAL '90 days'
    ) AS n_obra_90d,
    count(*) FILTER (
        WHERE cls.engineering_class IN ('OBRA_EXECUCAO', 'OBRA_COM_PROJETO')
          AND coalesce(c.data_fim, CURRENT_DATE) >= CURRENT_DATE
          AND coalesce(c.data_assinatura, c.data_publicacao) >= CURRENT_DATE - INTERVAL '12 months'
    ) AS n_obra_active_12m,
    count(*) FILTER (
        WHERE cls.engineering_class = 'OBRA_COM_PROJETO'
          AND coalesce(c.data_assinatura, c.data_publicacao) >= CURRENT_DATE - INTERVAL '12 months'
    ) AS n_integ_12m,
    count(*) FILTER (
        WHERE coalesce(c.data_assinatura, c.data_publicacao) < CURRENT_DATE - INTERVAL '90 days'
    ) AS n_before_90d,
    max(c.valor_total) FILTER (
        WHERE coalesce(c.data_assinatura, c.data_publicacao) < CURRENT_DATE - INTERVAL '90 days'
    ) AS v_max_before_90d,
    array_agg(DISTINCT c.uf) FILTER (
        WHERE c.uf IS NOT NULL
          AND coalesce(c.data_assinatura, c.data_publicacao) < CURRENT_DATE - INTERVAL '90 days'
    ) AS ufs_before_90d,
    count(*) FILTER (
        WHERE c.data_fim IS NOT NULL
          AND c.data_fim BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '60 days'
    ) AS n_ending_60d,
    (array_agg(c.objeto_contrato ORDER BY coalesce(c.data_assinatura, c.data_publicacao) DESC NULLS LAST))[1:5] AS recent_objects,
    now() AS refreshed_at
FROM public.pncp_supplier_contracts c
JOIN public.contract_engineering_class cls
    ON cls.contrato_id = c.contrato_id
WHERE regexp_replace(COALESCE(c.fornecedor_cnpj, ''), '\D', '', 'g') ~ '^\d{14}$'
  AND cls.engineering_class <> 'NAO_ENGENHARIA'
  AND coalesce(c.quality_state, 'VALID') <> 'QUARANTINED'
GROUP BY 1;

CREATE UNIQUE INDEX IF NOT EXISTS mv_supplier_structural_profile_pk
    ON public.mv_supplier_structural_profile (fornecedor_cnpj);

COMMENT ON MATERIALIZED VIEW public.mv_supplier_structural_profile IS
    'Daily F1–F8 supplier structural profile (#547). Reads contract_engineering_class; no objeto regex.';

CREATE OR REPLACE FUNCTION public.refresh_supplier_structural_profile()
RETURNS TIMESTAMPTZ
LANGUAGE plpgsql
AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY public.mv_supplier_structural_profile;
    RETURN NOW();
END;
$$;

COMMIT;
