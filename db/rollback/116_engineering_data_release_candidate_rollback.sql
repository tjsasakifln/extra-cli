-- Restore the #550 view shape (original 24 columns) and drop candidate grants.

BEGIN;

REVOKE SELECT ON TABLE public.v_supplier_cadastral_contact FROM confenge_commercial_read_v1;
REVOKE SELECT ON TABLE public.v_engineering_supplier_universe FROM confenge_commercial_read_v1;
REVOKE SELECT ON TABLE public.v_orgaos_contratantes_projeto FROM confenge_commercial_read_v1;
REVOKE SELECT ON TABLE public.v_contract_dates_sane FROM confenge_commercial_read_v1;

DROP VIEW IF EXISTS public.v_recent_engineering_wins;

CREATE OR REPLACE VIEW public.v_recent_engineering_wins AS
SELECT
    regexp_replace(COALESCE(c.fornecedor_cnpj, ''), '\D', '', 'g') AS company_cnpj,
    c.fornecedor_nome AS company_name,
    c.parent_procurement_id AS procurement_id,
    c.contrato_id AS contract_id,
    CASE
        WHEN cls.engineering_class = 'PROJETO_ENGENHARIA' THEN 'PROJETO'
        WHEN cls.engineering_class = 'OBRA_COM_PROJETO' THEN 'OBRA_INTEGRADA'
        ELSE 'CONTRATO'
    END AS trigger_type,
    coalesce(c.data_assinatura, c.data_publicacao_fonte)::timestamp AS event_at,
    c.data_publicacao_fonte::timestamp AS source_published_at,
    c.first_seen_at,
    (c.first_seen_at::date - c.data_publicacao_fonte) AS detection_lag_days,
    (c.data_publicacao_fonte - c.data_assinatura) AS publication_lag_days,
    c.objeto_contrato AS object,
    c.valor_total AS value,
    c.orgao_nome AS buyer,
    c.orgao_cnpj AS buyer_cnpj,
    c.uf,
    c.municipio,
    cls.engineering_class,
    cls.confidence AS engineering_confidence,
    coalesce(c.lifecycle_event_last, c.status_normalized, 'UNKNOWN') AS lifecycle_status,
    cls.confidence AS event_confidence,
    (c.first_seen_at::date - c.data_publicacao_fonte) AS data_freshness,
    (CURRENT_DATE - coalesce(c.data_assinatura, c.data_publicacao_fonte)) AS commercial_age_days,
    CASE
        WHEN c.lifecycle_event_last IN ('REVOGACAO', 'ANULACAO', 'RESCISAO') THEN 'NOT_ACTIONABLE'
        WHEN (CURRENT_DATE - coalesce(c.data_assinatura, c.data_publicacao_fonte)) BETWEEN 0 AND 14 THEN 'HOT'
        WHEN (CURRENT_DATE - coalesce(c.data_assinatura, c.data_publicacao_fonte)) BETWEEN 15 AND 45 THEN 'WARM'
        WHEN (CURRENT_DATE - coalesce(c.data_assinatura, c.data_publicacao_fonte)) BETWEEN 46 AND 90 THEN 'ACTIVE'
        WHEN (CURRENT_DATE - coalesce(c.data_assinatura, c.data_publicacao_fonte)) BETWEEN 91 AND 120 THEN 'LATE'
        ELSE 'COLD'
    END AS commercial_actionability,
    cls.evidence AS evidence_refs
FROM public.pncp_supplier_contracts c
JOIN public.contract_engineering_class cls
    ON cls.contrato_id = c.contrato_id
WHERE cls.engineering_class <> 'NAO_ENGENHARIA'
  AND coalesce(c.quality_state, 'VALID') <> 'QUARANTINED';

REVOKE ALL ON TABLE public.v_recent_engineering_wins FROM PUBLIC;
GRANT SELECT ON TABLE public.v_recent_engineering_wins TO confenge_commercial_read_v1;

COMMIT;
