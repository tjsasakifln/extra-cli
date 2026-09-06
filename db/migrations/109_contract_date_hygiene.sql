-- 109_contract_date_hygiene.sql
-- #552: quarantine absurd dates before they contaminate MAX/recency;
-- resolve status_observed_at as real observation of an official status
-- (never a fabricated now()); mark empty 088 canonical event/supplier
-- tables NON-OPERATIONAL (successor: dedicated result/term tables in #545/#548).
--
-- ROLLBACK:
--   psql "$LOCAL_DATALAKE_DSN" -f db/rollback/109_contract_date_hygiene_rollback.sql

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

COMMENT ON COLUMN public.pncp_supplier_contracts.data_assinatura IS
    'Official PNCP dataAssinatura (event_at of the signature act). Distinct from data_publicacao_fonte (source_published_at) and first_seen_at. #552.';
COMMENT ON COLUMN public.pncp_supplier_contracts.data_publicacao_fonte IS
    'Official PNCP dataPublicacaoPncp (source_published_at). Distinct from data_assinatura and first_seen_at. #552.';
COMMENT ON COLUMN public.pncp_supplier_contracts.data_publicacao IS
    'Legacy publication date. Prefer data_publicacao_fonte. May equal data_assinatura on old rows; that is NOT an ordem de servico. #552.';
COMMENT ON COLUMN public.pncp_supplier_contracts.data_inicio IS
    'PNCP dataVigenciaInicio. When equal to data_assinatura (~50% of rows) it is still vigencia start, not ordem de servico. #552.';
COMMENT ON COLUMN public.pncp_supplier_contracts.data_fim IS
    'PNCP dataVigenciaFim. #552.';
COMMENT ON COLUMN public.pncp_supplier_contracts.source_event_date IS
    'Best official event date: data_assinatura else data_publicacao_fonte. Distinct from first_seen_at. #552.';
COMMENT ON COLUMN public.pncp_supplier_contracts.first_seen_at IS
    'Lake first observation time. Distinct from source_published_at and event_at. #552.';
COMMENT ON COLUMN public.pncp_supplier_contracts.last_seen_at IS
    'Lake last re-observation time. #552.';
COMMENT ON COLUMN public.pncp_supplier_contracts.status_observed_at IS
    'Timestamp of observing an official status field (situacaoContrato/status_raw). NULL when status is inferred from vigencia or missing. Never a fabricated now(). #552.';
COMMENT ON COLUMN public.pncp_supplier_contracts.quality_state IS
    'VALID | REVIEW | QUARANTINED. Implausible dates (e.g. year 8406) are QUARANTINED and nulled so they cannot win MAX. #552.';

CREATE OR REPLACE FUNCTION public.fn_quarantine_implausible_contract_dates()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    reasons jsonb := COALESCE(NEW.quality_reasons, '[]'::jsonb);
    quarantined boolean := false;
    col text;
    d date;
BEGIN
    FOREACH col IN ARRAY ARRAY[
        'data_assinatura',
        'data_inicio',
        'data_fim',
        'data_publicacao',
        'data_publicacao_fonte',
        'data_atualizacao_fonte',
        'source_event_date'
    ]
    LOOP
        d := CASE col
            WHEN 'data_assinatura' THEN NEW.data_assinatura
            WHEN 'data_inicio' THEN NEW.data_inicio
            WHEN 'data_fim' THEN NEW.data_fim
            WHEN 'data_publicacao' THEN NEW.data_publicacao
            WHEN 'data_publicacao_fonte' THEN NEW.data_publicacao_fonte
            WHEN 'data_atualizacao_fonte' THEN NEW.data_atualizacao_fonte
            WHEN 'source_event_date' THEN NEW.source_event_date
        END;
        IF d IS NULL THEN
            CONTINUE;
        END IF;
        IF EXTRACT(YEAR FROM d) >= 8000
           OR EXTRACT(YEAR FROM d) > 2100
           OR EXTRACT(YEAR FROM d) < 1994 THEN
            reasons := reasons || jsonb_build_array(
                'implausible_date:' || col || ':' || d::text
            );
            quarantined := true;
            IF col = 'data_assinatura' THEN NEW.data_assinatura := NULL; END IF;
            IF col = 'data_inicio' THEN NEW.data_inicio := NULL; END IF;
            IF col = 'data_fim' THEN NEW.data_fim := NULL; END IF;
            IF col = 'data_publicacao' THEN NEW.data_publicacao := NULL; END IF;
            IF col = 'data_publicacao_fonte' THEN NEW.data_publicacao_fonte := NULL; END IF;
            IF col = 'data_atualizacao_fonte' THEN NEW.data_atualizacao_fonte := NULL; END IF;
            IF col = 'source_event_date' THEN NEW.source_event_date := NULL; END IF;
        END IF;
    END LOOP;

    IF quarantined THEN
        NEW.quality_state := 'QUARANTINED';
        NEW.quality_reasons := reasons;
        NEW.quality_rule_version := COALESCE(NEW.quality_rule_version, 'contract-date-quarantine-v1');
    END IF;

    -- Official status observation only. Inferred vigencia status stays NULL.
    IF NEW.status_raw IS NULL OR btrim(NEW.status_raw) = '' THEN
        NEW.status_observed_at := NULL;
    ELSIF NEW.status_observed_at IS NULL THEN
        NEW.status_observed_at := COALESCE(NEW.last_seen_at, NEW.first_seen_at);
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_quarantine_implausible_contract_dates
    ON public.pncp_supplier_contracts;
CREATE TRIGGER trg_quarantine_implausible_contract_dates
    BEFORE INSERT OR UPDATE ON public.pncp_supplier_contracts
    FOR EACH ROW
    EXECUTE FUNCTION public.fn_quarantine_implausible_contract_dates();

-- Existing absurd dates: null them so MAX is clean. Trigger sets quality.
UPDATE public.pncp_supplier_contracts
SET data_assinatura = data_assinatura
WHERE EXTRACT(YEAR FROM data_assinatura) >= 8000
   OR EXTRACT(YEAR FROM data_inicio) >= 8000
   OR EXTRACT(YEAR FROM data_fim) >= 8000
   OR EXTRACT(YEAR FROM data_publicacao) >= 8000
   OR EXTRACT(YEAR FROM data_publicacao_fonte) >= 8000
   OR EXTRACT(YEAR FROM source_event_date) >= 8000;

CREATE OR REPLACE VIEW public.v_contract_dates_sane AS
SELECT
    contrato_id,
    data_assinatura,
    data_publicacao_fonte,
    source_event_date,
    data_inicio,
    data_fim,
    first_seen_at,
    last_seen_at,
    status_observed_at,
    quality_state
FROM public.pncp_supplier_contracts
WHERE COALESCE(quality_state, 'VALID') <> 'QUARANTINED';

COMMENT ON VIEW public.v_contract_dates_sane IS
    'MAX/recency-safe contract dates. QUARANTINED rows (absurd years) are excluded. #552.';

CREATE TABLE IF NOT EXISTS public.canonical_surface_operational_status (
    object_name      TEXT PRIMARY KEY,
    operational      BOOLEAN NOT NULL,
    decision         TEXT NOT NULL CHECK (decision IN ('OPERATIONAL', 'NON_OPERATIONAL')),
    reason           TEXT NOT NULL,
    successor_issue  TEXT,
    successor_object TEXT,
    decided_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    policy_version   TEXT NOT NULL
);

COMMENT ON TABLE public.canonical_surface_operational_status IS
    'Operational vs non-operational declaration for canonical surfaces. Empty 088 tables are NON_OPERATIONAL; do not treat 0 rows as coverage. #552.';

INSERT INTO public.canonical_surface_operational_status (
    object_name, operational, decision, reason, successor_issue, successor_object, policy_version
) VALUES
    (
        'canonical_public_events_v1', false, 'NON_OPERATIONAL',
        'Table exists from 088 but has 0 rows. Event types do not include RESULT_PUBLISHED/HOMOLOGATED and require canonical entity graph that is also empty.',
        '#545', 'pncp_procurement_results (dedicated; not this table)',
        'canonical-surface-status-v1'
    ),
    (
        'canonical_public_observations', false, 'NON_OPERATIONAL',
        '0 rows. Not an operational observation store for commercial feed.',
        '#545', 'pncp_procurement_results',
        'canonical-surface-status-v1'
    ),
    (
        'canonical_event_observation_links', false, 'NON_OPERATIONAL',
        '0 rows. Depends on empty events/observations.',
        '#545', NULL,
        'canonical-surface-status-v1'
    ),
    (
        'canonical_suppliers', false, 'NON_OPERATIONAL',
        '0 rows. Commercial supplier identity is pncp_supplier_contracts + supplier_registry.',
        '#549', 'supplier_registry',
        'canonical-surface-status-v1'
    ),
    (
        'observed_supplier_relations', false, 'NON_OPERATIONAL',
        '0 rows. Not used by the commercial feed.',
        '#549', 'supplier_registry',
        'canonical-surface-status-v1'
    ),
    (
        'official_acts', false, 'NON_OPERATIONAL',
        '2 residual rows; not an operational pre-signature result or term store.',
        '#545,#548', 'pncp_procurement_results / contract_terms',
        'canonical-surface-status-v1'
    )
ON CONFLICT (object_name) DO UPDATE SET
    operational = EXCLUDED.operational,
    decision = EXCLUDED.decision,
    reason = EXCLUDED.reason,
    successor_issue = EXCLUDED.successor_issue,
    successor_object = EXCLUDED.successor_object,
    policy_version = EXCLUDED.policy_version,
    decided_at = NOW();

COMMIT;
