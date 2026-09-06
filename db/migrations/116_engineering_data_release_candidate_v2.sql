-- 116_engineering_data_release_candidate_v2.sql
-- Minimal signed/published engineering-data release boundary (#544-#554).
-- Classification remains owned by contract_engineering_class; this consumer
-- never reclassifies objeto text. Pre-signature result events are absent.
--
-- ROLLBACK:
--   psql "$LOCAL_DATALAKE_DSN" -f db/rollback/116_engineering_data_release_candidate_v2_rollback.sql

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

CREATE INDEX IF NOT EXISTS idx_psc_engineering_event_at
    ON public.pncp_supplier_contracts (
        (COALESCE(data_assinatura, data_publicacao_fonte)) DESC,
        contrato_id
    )
    WHERE COALESCE(data_assinatura, data_publicacao_fonte) IS NOT NULL
      AND COALESCE(quality_state, 'VALID') <> 'QUARANTINED';

-- Existing v1 columns stay in the same order. Candidate columns are appended,
-- which is required by PostgreSQL CREATE OR REPLACE VIEW compatibility.
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
    COALESCE(c.data_assinatura, c.data_publicacao_fonte)::timestamp AS event_at,
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
    COALESCE(c.lifecycle_event_last, c.status_normalized, 'UNKNOWN') AS lifecycle_status,
    cls.confidence AS event_confidence,
    (c.first_seen_at::date - c.data_publicacao_fonte) AS data_freshness,
    (CURRENT_DATE - COALESCE(c.data_assinatura, c.data_publicacao_fonte)) AS commercial_age_days,
    CASE
        WHEN c.lifecycle_event_last IN ('REVOGACAO', 'ANULACAO', 'RESCISAO') THEN 'NOT_ACTIONABLE'
        WHEN (CURRENT_DATE - COALESCE(c.data_assinatura, c.data_publicacao_fonte)) BETWEEN 0 AND 14 THEN 'HOT'
        WHEN (CURRENT_DATE - COALESCE(c.data_assinatura, c.data_publicacao_fonte)) BETWEEN 15 AND 45 THEN 'WARM'
        WHEN (CURRENT_DATE - COALESCE(c.data_assinatura, c.data_publicacao_fonte)) BETWEEN 46 AND 90 THEN 'ACTIVE'
        WHEN (CURRENT_DATE - COALESCE(c.data_assinatura, c.data_publicacao_fonte)) BETWEEN 91 AND 120 THEN 'LATE'
        ELSE 'COLD'
    END AS commercial_actionability,
    cls.evidence AS evidence_refs,
    c.tipo_contrato_id,
    c.tipo_contrato_nome,
    c.categoria_processo_id,
    c.categoria_processo_nome,
    c.modalidade_id,
    c.modalidade_nome,
    c.regime_execucao_id,
    c.regime_execucao_nome,
    c.srp,
    CASE
        WHEN c.data_assinatura IS NOT NULL THEN 'CONTRACT_SIGNED'
        ELSE 'CONTRACT_PUBLISHED'
    END AS event_type
FROM public.pncp_supplier_contracts c
JOIN public.contract_engineering_class cls
    ON cls.contrato_id = c.contrato_id
WHERE cls.engineering_class <> 'NAO_ENGENHARIA'
  AND COALESCE(c.quality_state, 'VALID') <> 'QUARANTINED'
  AND COALESCE(c.data_assinatura, c.data_publicacao_fonte) IS NOT NULL;

COMMENT ON VIEW public.v_recent_engineering_wins IS
    'commercial_read_v1 v2 candidate (#550/#554): persisted class, sane dates, terminal lifecycle, official PNCP structural facts, and LIVE_PROVEN contract signed/published events only.';
COMMENT ON COLUMN public.v_recent_engineering_wins.data_freshness IS
    'DATA_FRESHNESS: lake first_seen_at minus source_published_at. Not event recency.';
COMMENT ON COLUMN public.v_recent_engineering_wins.commercial_age_days IS
    'EVENT_RECENCY: today minus official signed/published event_at. Not data freshness.';
COMMENT ON COLUMN public.v_recent_engineering_wins.commercial_actionability IS
    'HOT/WARM/ACTIVE/LATE from event recency; terminal lifecycle is NOT_ACTIONABLE.';
COMMENT ON COLUMN public.v_recent_engineering_wins.event_type IS
    'LIVE_PROVEN release boundary: CONTRACT_SIGNED when assinatura exists, otherwise CONTRACT_PUBLISHED.';

REVOKE ALL ON TABLE public.v_recent_engineering_wins FROM PUBLIC;
GRANT SELECT ON TABLE public.v_recent_engineering_wins TO confenge_commercial_read_v1;
GRANT SELECT ON TABLE public.v_supplier_cadastral_contact TO confenge_commercial_read_v1;
GRANT SELECT ON TABLE public.v_engineering_supplier_universe TO confenge_commercial_read_v1;
GRANT SELECT ON TABLE public.v_orgaos_contratantes_projeto TO confenge_commercial_read_v1;
GRANT SELECT ON TABLE public.v_contract_dates_sane TO confenge_commercial_read_v1;

COMMIT;
