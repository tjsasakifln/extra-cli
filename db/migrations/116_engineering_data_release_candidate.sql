-- 116_engineering_data_release_candidate.sql
-- Candidate wiring for EXTRA-ENGINEERING-DATA-RELEASE-CANDIDATE-01.
-- Extends commercial_read_v1 with official PNCP identity columns and
-- fail-closed procurement-result status. Does not invent a second
-- classification authority: class still comes from contract_engineering_class.
--
-- Additive columns are appended (PG CREATE OR REPLACE VIEW rule).
-- RESULT_PUBLISHED / ADJUDICATED / HOMOLOGATED are NEVER trigger_type;
-- procurement_result_status is UNKNOWN unless a persisted #545 event exists.
--
-- ROLLBACK:
--   psql "$LOCAL_DATALAKE_DSN" -f db/rollback/116_engineering_data_release_candidate_rollback.sql

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

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
    COALESCE(result_evt.procurement_result_status, 'UNKNOWN') AS procurement_result_status
FROM public.pncp_supplier_contracts c
JOIN public.contract_engineering_class cls
    ON cls.contrato_id = c.contrato_id
LEFT JOIN LATERAL (
    SELECT CASE
        WHEN bool_or(r.event_type = 'HOMOLOGATED') THEN 'HOMOLOGATED'
        WHEN bool_or(r.event_type = 'RESULT_PUBLISHED') THEN 'RESULT_PUBLISHED'
        ELSE 'UNKNOWN'
    END AS procurement_result_status
    FROM public.pncp_procurement_results r
    WHERE c.parent_procurement_id IS NOT NULL
      AND btrim(c.parent_procurement_id) <> ''
      AND r.parent_procurement_id = c.parent_procurement_id
) result_evt ON TRUE
WHERE cls.engineering_class <> 'NAO_ENGENHARIA'
  AND coalesce(c.quality_state, 'VALID') <> 'QUARANTINED';

COMMENT ON VIEW public.v_recent_engineering_wins IS
    'commercial_read_v1 wins surface (#550/#116). Class from contract_engineering_class; dates exclude QUARANTINED; terminal lifecycle is NOT_ACTIONABLE; official PNCP identity columns; clocks independent. procurement_result_status is UNKNOWN unless a persisted #545 event exists. trigger_type is never RESULT_PUBLISHED/ADJUDICATED/HOMOLOGATED.';

COMMENT ON COLUMN public.v_recent_engineering_wins.data_freshness IS
    'DATA_FRESHNESS: lake first_seen_at minus source_published_at. Not event recency.';
COMMENT ON COLUMN public.v_recent_engineering_wins.commercial_age_days IS
    'EVENT_RECENCY: today minus official event_at (assinatura/publicacao). Not data freshness.';
COMMENT ON COLUMN public.v_recent_engineering_wins.commercial_actionability IS
    'COMMERCIAL_ACTIONABILITY: HOT/WARM/ACTIVE/LATE from event recency; NOT_ACTIONABLE if revoked/annulled/rescinded. Not derived from data_freshness.';
COMMENT ON COLUMN public.v_recent_engineering_wins.tipo_contrato_nome IS
    'Official PNCP tipoContrato nome (#546). Not inferred from objeto.';
COMMENT ON COLUMN public.v_recent_engineering_wins.categoria_processo_nome IS
    'Official PNCP categoriaProcesso nome (#546). Not inferred from objeto.';
COMMENT ON COLUMN public.v_recent_engineering_wins.regime_execucao_nome IS
    'Official PNCP regime de execução (#546). Beats textual heuristic when persisted.';
COMMENT ON COLUMN public.v_recent_engineering_wins.procurement_result_status IS
    'Fail-closed #545: UNKNOWN unless a persisted RESULT_PUBLISHED or HOMOLOGATED row exists for parent_procurement_id. ADJUDICATED is never inferred. Not trigger_type.';

REVOKE ALL ON TABLE public.v_recent_engineering_wins FROM PUBLIC;
GRANT SELECT ON TABLE public.v_recent_engineering_wins TO confenge_commercial_read_v1;

GRANT SELECT ON TABLE public.v_supplier_cadastral_contact TO confenge_commercial_read_v1;
GRANT SELECT ON TABLE public.v_engineering_supplier_universe TO confenge_commercial_read_v1;
GRANT SELECT ON TABLE public.v_orgaos_contratantes_projeto TO confenge_commercial_read_v1;
GRANT SELECT ON TABLE public.v_contract_dates_sane TO confenge_commercial_read_v1;

COMMIT;
