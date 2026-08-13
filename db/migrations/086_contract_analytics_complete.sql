-- 086_contract_analytics_complete.sql
-- Complete, snapshot-bound contract analytics and keyset pagination (#355, #356).

BEGIN;

CREATE INDEX IF NOT EXISTS idx_psc_supplier_event_keyset
    ON public.pncp_supplier_contracts (
        supplier_id_type,
        supplier_identifier,
        (COALESCE(data_assinatura, data_publicacao_fonte, data_publicacao, data_inicio)) DESC,
        id DESC
    )
    WHERE is_active = TRUE;

CREATE OR REPLACE FUNCTION public.supplier_contracts_dataset_v2(
    p_supplier_id_type TEXT DEFAULT NULL,
    p_supplier_identifier TEXT DEFAULT NULL,
    p_orgao_cnpj TEXT DEFAULT NULL,
    p_ufs TEXT[] DEFAULT NULL,
    p_keywords TEXT[] DEFAULT NULL,
    p_date_start DATE DEFAULT NULL,
    p_date_end DATE DEFAULT NULL,
    p_snapshot_at TEXT DEFAULT NULL
)
RETURNS TABLE (
    record_id BIGINT,
    contrato_id TEXT,
    supplier_id_type TEXT,
    supplier_identifier TEXT,
    supplier_identifier_hash TEXT,
    supplier_identifier_export TEXT,
    fornecedor_nome TEXT,
    orgao_cnpj TEXT,
    orgao_nome TEXT,
    uf TEXT,
    municipio TEXT,
    valor_total NUMERIC,
    data_assinatura DATE,
    data_publicacao DATE,
    event_date DATE,
    objeto_contrato TEXT,
    source TEXT,
    ingested_at TIMESTAMPTZ,
    quarantined BOOLEAN
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        contract.id::BIGINT,
        contract.contrato_id,
        contract.supplier_id_type,
        contract.supplier_identifier,
        contract.supplier_identifier_hash,
        contract.supplier_identifier_export,
        contract.fornecedor_nome,
        contract.orgao_cnpj,
        contract.orgao_nome,
        contract.uf,
        contract.municipio,
        contract.valor_total,
        contract.data_assinatura,
        COALESCE(contract.data_publicacao_fonte, contract.data_publicacao),
        event.event_date,
        contract.objeto_contrato,
        contract.source,
        contract.ingested_at,
        event.event_date IS NULL
            OR contract.valor_total IS NULL
            OR contract.valor_total < 0
    FROM public.pncp_supplier_contracts AS contract
    CROSS JOIN LATERAL (
        SELECT COALESCE(
            contract.data_assinatura,
            contract.data_publicacao_fonte,
            contract.data_publicacao,
            contract.data_inicio
        ) AS event_date
    ) AS event
    WHERE contract.is_active = TRUE
      AND contract.ingested_at <= COALESCE(
          NULLIF(p_snapshot_at, '')::TIMESTAMPTZ,
          statement_timestamp()
      )
      AND (p_supplier_id_type IS NULL OR contract.supplier_id_type = upper(p_supplier_id_type))
      AND (p_supplier_identifier IS NULL OR contract.supplier_identifier = p_supplier_identifier)
      AND (p_orgao_cnpj IS NULL OR contract.orgao_cnpj = regexp_replace(p_orgao_cnpj, '\D', '', 'g'))
      AND (p_ufs IS NULL OR contract.uf = ANY(p_ufs))
      AND (
          p_keywords IS NULL
          OR NOT EXISTS (
              SELECT 1
              FROM unnest(p_keywords) AS keyword
              WHERE NULLIF(btrim(keyword), '') IS NOT NULL
                AND position(lower(btrim(keyword)) IN lower(COALESCE(contract.objeto_contrato, ''))) = 0
          )
      )
      AND (p_date_start IS NULL OR event.event_date >= p_date_start)
      AND (p_date_end IS NULL OR event.event_date <= p_date_end);
$$;

CREATE OR REPLACE FUNCTION public.supplier_contracts_page_v2(
    p_supplier_id_type TEXT DEFAULT NULL,
    p_supplier_identifier TEXT DEFAULT NULL,
    p_orgao_cnpj TEXT DEFAULT NULL,
    p_ufs TEXT[] DEFAULT NULL,
    p_keywords TEXT[] DEFAULT NULL,
    p_date_start DATE DEFAULT NULL,
    p_date_end DATE DEFAULT NULL,
    p_value_min NUMERIC DEFAULT NULL,
    p_page_size INTEGER DEFAULT 200,
    p_cursor_date DATE DEFAULT NULL,
    p_cursor_id BIGINT DEFAULT NULL,
    p_snapshot_at TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE sql
STABLE
AS $$
    WITH request AS (
        SELECT
            LEAST(GREATEST(COALESCE(p_page_size, 200), 1), 1000) AS page_size,
            COALESCE(NULLIF(p_snapshot_at, '')::TIMESTAMPTZ, statement_timestamp()) AS snapshot_at
    ), all_rows AS MATERIALIZED (
        SELECT dataset.*
        FROM request
        CROSS JOIN public.supplier_contracts_dataset_v2(
            p_supplier_id_type,
            p_supplier_identifier,
            p_orgao_cnpj,
            p_ufs,
            p_keywords,
            p_date_start,
            p_date_end,
            request.snapshot_at::TEXT
        ) AS dataset
    ), eligible AS MATERIALIZED (
        SELECT *
        FROM all_rows
        WHERE NOT quarantined
          AND (p_value_min IS NULL OR valor_total >= p_value_min)
    ), page_candidates AS MATERIALIZED (
        SELECT eligible.*
        FROM eligible
        WHERE p_cursor_date IS NULL
           OR p_cursor_id IS NULL
           OR (eligible.event_date, eligible.record_id) < (p_cursor_date, p_cursor_id)
        ORDER BY eligible.event_date DESC, eligible.record_id DESC
        LIMIT (SELECT page_size + 1 FROM request)
    ), page_rows AS MATERIALIZED (
        SELECT *
        FROM page_candidates
        ORDER BY event_date DESC, record_id DESC
        LIMIT (SELECT page_size FROM request)
    ), aggregate_stats AS (
        SELECT
            count(*)::BIGINT AS total_count,
            COALESCE(sum(valor_total), 0)::NUMERIC AS sum_value,
            avg(valor_total)::NUMERIC AS average_value,
            stddev_pop(valor_total)::NUMERIC AS stddev_value,
            percentile_cont(0.10) WITHIN GROUP (ORDER BY valor_total)::NUMERIC AS p10,
            percentile_cont(0.25) WITHIN GROUP (ORDER BY valor_total)::NUMERIC AS p25,
            percentile_cont(0.50) WITHIN GROUP (ORDER BY valor_total)::NUMERIC AS p50,
            percentile_cont(0.75) WITHIN GROUP (ORDER BY valor_total)::NUMERIC AS p75,
            percentile_cont(0.90) WITHIN GROUP (ORDER BY valor_total)::NUMERIC AS p90,
            min(data_publicacao) AS min_publication_date,
            max(data_publicacao) AS max_publication_date,
            min(data_assinatura) AS min_signature_date,
            max(data_assinatura) AS max_signature_date,
            max(ingested_at) AS freshness_at
        FROM eligible
    ), quarantine_stats AS (
        SELECT count(*)::BIGINT AS quarantine_count
        FROM all_rows
        WHERE quarantined
    ), source_stats AS (
        SELECT COALESCE(jsonb_agg(source ORDER BY source), '[]'::JSONB) AS sources
        FROM (SELECT DISTINCT source FROM eligible WHERE source IS NOT NULL) AS distinct_sources
    ), annual_stats AS (
        SELECT COALESCE(
            jsonb_agg(
                jsonb_build_object(
                    'year', year,
                    'matched_contracts', matched_contracts,
                    'sum_value', sum_value
                ) ORDER BY year
            ),
            '[]'::JSONB
        ) AS annual_series
        FROM (
            SELECT
                extract(YEAR FROM event_date)::INTEGER AS year,
                count(*)::BIGINT AS matched_contracts,
                COALESCE(sum(valor_total), 0)::NUMERIC AS sum_value
            FROM eligible
            GROUP BY extract(YEAR FROM event_date)::INTEGER
        ) AS yearly
    ), run_info AS (
        SELECT id, status, COALESCE(completed_at, finished_at, started_at) AS run_at
        FROM public.ingestion_runs
        WHERE status = 'completed'
        ORDER BY COALESCE(completed_at, finished_at, started_at) DESC, id DESC
        LIMIT 1
    ), page_info AS (
        SELECT
            count(*) > (SELECT page_size FROM request) AS has_more,
            (SELECT event_date FROM page_rows ORDER BY event_date, record_id LIMIT 1) AS next_date,
            (SELECT record_id FROM page_rows ORDER BY event_date, record_id LIMIT 1) AS next_id
        FROM page_candidates
    )
    SELECT jsonb_build_object(
        'items', COALESCE((
            SELECT jsonb_agg(
                jsonb_build_object(
                    'record_id', record_id,
                    'numero_controle_pncp', contrato_id,
                    'supplier_id_type', supplier_id_type,
                    'supplier_identifier', supplier_identifier_export,
                    'ni_fornecedor', supplier_identifier_export,
                    'nome_fornecedor', fornecedor_nome,
                    'orgao_cnpj', orgao_cnpj,
                    'orgao_nome', orgao_nome,
                    'uf', uf,
                    'municipio', municipio,
                    'valor_global', valor_total,
                    'data_assinatura', data_assinatura,
                    'data_publicacao', data_publicacao,
                    'event_date', event_date,
                    'objeto_contrato', objeto_contrato,
                    'source', source,
                    'ingested_at', ingested_at
                ) ORDER BY event_date DESC, record_id DESC
            ) FROM page_rows
        ), '[]'::JSONB),
        'meta', jsonb_build_object(
            'source', 'datalake_contracts_v2',
            'completeness', CASE
                WHEN run_info.id IS NULL THEN 'INCOMPLETE'
                WHEN quarantine_stats.quarantine_count > 0 THEN 'INCOMPLETE'
                WHEN page_info.has_more THEN 'PRESENTATION_LIMITED'
                ELSE 'COMPLETE'
            END,
            'has_more', page_info.has_more,
            'next_cursor', CASE WHEN page_info.has_more THEN jsonb_build_object(
                'date', page_info.next_date,
                'id', page_info.next_id
            ) ELSE NULL END,
            'total_count', aggregate_stats.total_count,
            'matched_contracts', aggregate_stats.total_count,
            'sum_value', aggregate_stats.sum_value,
            'average_value', aggregate_stats.average_value,
            'stddev_value', aggregate_stats.stddev_value,
            'p10', aggregate_stats.p10,
            'p25', aggregate_stats.p25,
            'p50', aggregate_stats.p50,
            'p75', aggregate_stats.p75,
            'p90', aggregate_stats.p90,
            'quarantine_count', quarantine_stats.quarantine_count,
            'min_publication_date', aggregate_stats.min_publication_date,
            'max_publication_date', aggregate_stats.max_publication_date,
            'min_signature_date', aggregate_stats.min_signature_date,
            'max_signature_date', aggregate_stats.max_signature_date,
            'sources', source_stats.sources,
            'annual_series', annual_stats.annual_series,
            'snapshot_at', request.snapshot_at,
            'snapshot_id', concat(COALESCE(run_info.id::TEXT, 'no-run'), ':', request.snapshot_at::TEXT),
            'ingestion_run_id', run_info.id,
            'ingestion_run_status', run_info.status,
            'freshness_at', aggregate_stats.freshness_at,
            'freshness_seconds', CASE WHEN aggregate_stats.freshness_at IS NULL THEN NULL
                ELSE extract(EPOCH FROM request.snapshot_at - aggregate_stats.freshness_at)::BIGINT END,
            'date_semantics', 'event_date=data_assinatura|data_publicacao_fonte|data_publicacao|data_inicio',
            'window_start', p_date_start,
            'window_end', p_date_end,
            'page_size', request.page_size
        )
    )
    FROM request
    CROSS JOIN aggregate_stats
    CROSS JOIN quarantine_stats
    CROSS JOIN source_stats
    CROSS JOIN annual_stats
    CROSS JOIN page_info
    LEFT JOIN run_info ON TRUE;
$$;

CREATE OR REPLACE FUNCTION public.supplier_contracts_grouped_v2(
    p_group_by TEXT,
    p_orgao_cnpj TEXT DEFAULT NULL,
    p_ufs TEXT[] DEFAULT NULL,
    p_keywords TEXT[] DEFAULT NULL,
    p_date_start DATE DEFAULT NULL,
    p_date_end DATE DEFAULT NULL,
    p_limit INTEGER DEFAULT 20,
    p_snapshot_at TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    result JSONB;
BEGIN
    IF p_group_by NOT IN ('supplier', 'orgao') THEN
        RAISE EXCEPTION 'p_group_by must be supplier or orgao' USING ERRCODE = '22023';
    END IF;

    WITH request AS (
        SELECT
            LEAST(GREATEST(COALESCE(p_limit, 20), 1), 1000) AS result_limit,
            COALESCE(NULLIF(p_snapshot_at, '')::TIMESTAMPTZ, statement_timestamp()) AS snapshot_at
    ), all_rows AS MATERIALIZED (
        SELECT dataset.*
        FROM request
        CROSS JOIN public.supplier_contracts_dataset_v2(
            NULL, NULL, p_orgao_cnpj, p_ufs, p_keywords,
            p_date_start, p_date_end, request.snapshot_at::TEXT
        ) AS dataset
    ), eligible AS MATERIALIZED (
        SELECT * FROM all_rows WHERE NOT quarantined
    ), grouped AS MATERIALIZED (
        SELECT
            CASE WHEN p_group_by = 'supplier'
                THEN COALESCE(supplier_identifier_hash, supplier_identifier)
                ELSE orgao_cnpj END AS group_id,
            max(CASE WHEN p_group_by = 'supplier' THEN supplier_identifier_export ELSE orgao_cnpj END) AS group_identifier,
            max(CASE WHEN p_group_by = 'supplier' THEN fornecedor_nome ELSE orgao_nome END) AS group_name,
            max(CASE WHEN p_group_by = 'supplier' THEN supplier_id_type END) AS group_type,
            count(*)::BIGINT AS matched_contracts,
            COALESCE(sum(valor_total), 0)::NUMERIC AS sum_value,
            avg(valor_total)::NUMERIC AS average_value,
            max(event_date) AS latest_event_date,
            array_agg(DISTINCT uf ORDER BY uf) FILTER (WHERE uf IS NOT NULL) AS ufs
        FROM eligible
        GROUP BY CASE WHEN p_group_by = 'supplier'
            THEN COALESCE(supplier_identifier_hash, supplier_identifier)
            ELSE orgao_cnpj END
        HAVING CASE WHEN p_group_by = 'supplier'
            THEN COALESCE(supplier_identifier_hash, supplier_identifier)
            ELSE orgao_cnpj END IS NOT NULL
    ), ranked AS (
        SELECT *
        FROM grouped
        ORDER BY CASE WHEN p_group_by = 'supplier' THEN matched_contracts END DESC NULLS LAST,
                 sum_value DESC,
                 group_id
        LIMIT (SELECT result_limit FROM request)
    ), totals AS (
        SELECT
            (SELECT count(*) FROM grouped)::BIGINT AS total_groups,
            (SELECT count(*) FROM eligible)::BIGINT AS total_count,
            (SELECT count(*) FROM all_rows WHERE quarantined)::BIGINT AS quarantine_count,
            (SELECT max(ingested_at) FROM eligible) AS freshness_at
    ), run_info AS (
        SELECT id, status, COALESCE(completed_at, finished_at, started_at) AS run_at
        FROM public.ingestion_runs
        WHERE status = 'completed'
        ORDER BY COALESCE(completed_at, finished_at, started_at) DESC, id DESC
        LIMIT 1
    )
    SELECT jsonb_build_object(
        'items', COALESCE((SELECT jsonb_agg(
            jsonb_build_object(
                'group_id', group_id,
                'group_identifier', group_identifier,
                'group_name', group_name,
                'group_type', group_type,
                'matched_contracts', matched_contracts,
                'sum_value', sum_value,
                'average_value', average_value,
                'latest_event_date', latest_event_date,
                'ufs', COALESCE(to_jsonb(ufs), '[]'::JSONB)
            ) ORDER BY CASE WHEN p_group_by = 'supplier' THEN matched_contracts END DESC NULLS LAST,
                       sum_value DESC, group_id
        ) FROM ranked), '[]'::JSONB),
        'meta', jsonb_build_object(
            'source', 'datalake_contract_groups_v2',
            'group_by', p_group_by,
            'completeness', CASE
                WHEN run_info.id IS NULL THEN 'INCOMPLETE'
                WHEN totals.quarantine_count > 0 THEN 'INCOMPLETE'
                WHEN totals.total_groups > request.result_limit THEN 'PRESENTATION_LIMITED'
                ELSE 'COMPLETE'
            END,
            'total_count', totals.total_count,
            'total_groups', totals.total_groups,
            'quarantine_count', totals.quarantine_count,
            'limit', request.result_limit,
            'snapshot_at', request.snapshot_at,
            'snapshot_id', concat(COALESCE(run_info.id::TEXT, 'no-run'), ':', request.snapshot_at::TEXT),
            'ingestion_run_id', run_info.id,
            'ingestion_run_status', run_info.status,
            'freshness_at', totals.freshness_at,
            'window_start', p_date_start,
            'window_end', p_date_end,
            'date_semantics', 'event_date=data_assinatura|data_publicacao_fonte|data_publicacao|data_inicio'
        )
    ) INTO result
    FROM request CROSS JOIN totals LEFT JOIN run_info ON TRUE;

    RETURN result;
END;
$$;

COMMENT ON FUNCTION public.supplier_contracts_page_v2(TEXT, TEXT, TEXT, TEXT[], TEXT[], DATE, DATE, NUMERIC, INTEGER, DATE, BIGINT, TEXT) IS
    'Complete server-side contract aggregates plus snapshot-bound keyset details. Issues #355/#356.';

COMMENT ON FUNCTION public.supplier_contracts_grouped_v2(TEXT, TEXT, TEXT[], TEXT[], DATE, DATE, INTEGER, TEXT) IS
    'Complete server-side supplier/authority rankings. Presentation limits never alter aggregates. Issue #355.';

COMMIT;
