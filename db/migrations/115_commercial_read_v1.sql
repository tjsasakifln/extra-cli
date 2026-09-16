-- 115_commercial_read_v1.sql
-- #550: stable commercial_read_v1 + v_recent_engineering_wins + read-only role.
-- DATA_FRESHNESS, EVENT_RECENCY and COMMERCIAL_ACTIONABILITY are independent.

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
    cls.evidence AS evidence_refs
FROM public.pncp_supplier_contracts c
JOIN public.contract_engineering_class cls
    ON cls.contrato_id = c.contrato_id
WHERE cls.engineering_class <> 'NAO_ENGENHARIA'
  AND coalesce(c.quality_state, 'VALID') <> 'QUARANTINED';

COMMENT ON VIEW public.v_recent_engineering_wins IS
    'commercial_read_v1 wins surface (#550). DATA_FRESHNESS=first_seen-source_published; EVENT_RECENCY=commercial_age_days=today-event_at; COMMERCIAL_ACTIONABILITY from event recency plus terminal lifecycle. Independent fields.';

COMMENT ON COLUMN public.v_recent_engineering_wins.data_freshness IS
    'DATA_FRESHNESS: lake first_seen_at minus source_published_at. Not event recency.';
COMMENT ON COLUMN public.v_recent_engineering_wins.commercial_age_days IS
    'EVENT_RECENCY: today minus official event_at (assinatura/publicacao). Not data freshness.';
COMMENT ON COLUMN public.v_recent_engineering_wins.commercial_actionability IS
    'COMMERCIAL_ACTIONABILITY: HOT/WARM/ACTIVE/LATE from event recency; NOT_ACTIONABLE if revoked/annulled/rescinded. Not derived from data_freshness.';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'confenge_commercial_read_v1') THEN
        CREATE ROLE confenge_commercial_read_v1
            NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION;
        COMMENT ON ROLE confenge_commercial_read_v1 IS 'managed-by-extra-migration-115';
    END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO confenge_commercial_read_v1', current_database());
    EXECUTE format('GRANT confenge_commercial_read_v1 TO %I', current_user);
END $$;

ALTER ROLE confenge_commercial_read_v1 SET default_transaction_read_only = 'on';
GRANT USAGE ON SCHEMA public TO confenge_commercial_read_v1;
REVOKE ALL ON TABLE public.v_recent_engineering_wins FROM PUBLIC;
GRANT SELECT ON TABLE public.v_recent_engineering_wins TO confenge_commercial_read_v1;
GRANT SELECT ON TABLE public.supplier_registry TO confenge_commercial_read_v1;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_matviews WHERE schemaname = 'public' AND matviewname = 'mv_supplier_structural_profile'
    ) THEN
        EXECUTE 'GRANT SELECT ON TABLE public.mv_supplier_structural_profile TO confenge_commercial_read_v1';
    END IF;
END $$;

COMMIT;
