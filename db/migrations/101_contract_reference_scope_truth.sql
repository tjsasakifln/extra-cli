-- 101_contract_reference_scope_truth.sql
-- Fix #452 (lexical TI matching) and #453 (explicit benchmark geography).
--
-- The legacy regional percentile view remains available for compatible
-- consumers.  A scope-aware view is added beside it.  National reference
-- percentiles remain deliberately absent until the existing national coverage
-- authority and a comparable national corpus both authorize the claim.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

CREATE OR REPLACE FUNCTION public.contract_category_v1(object_text TEXT)
RETURNS TEXT
LANGUAGE SQL
IMMUTABLE
PARALLEL SAFE
RETURNS NULL ON NULL INPUT
AS $category$
    SELECT CASE
        WHEN object_text ILIKE '%obra%'
          OR object_text ILIKE '%construção%'
          OR object_text ILIKE '%pavimentação%'
          OR object_text ILIKE '%edificação%'
          OR object_text ILIKE '%engenharia%'
        THEN 'OBRAS'
        WHEN object_text ILIKE '%limpeza%'
          OR object_text ILIKE '%conservação%'
          OR object_text ILIKE '%manutenção%'
          OR object_text ILIKE '%zeladoria%'
        THEN 'FACILITIES'
        WHEN object_text ILIKE '%saúde%'
          OR object_text ILIKE '%medicamento%'
          OR object_text ILIKE '%hospitalar%'
          OR object_text ILIKE '%medico%'
          OR object_text ILIKE '%médico%'
          OR object_text ILIKE '%farmacêutico%'
          OR object_text ILIKE '%laboratório%'
        THEN 'SAÚDE'
        WHEN object_text ILIKE '%alimentação%'
          OR object_text ILIKE '%alimento%'
          OR object_text ILIKE '%merenda%'
          OR object_text ILIKE '%gênero alimentício%'
        THEN 'ALIMENTAÇÃO'
        WHEN object_text ILIKE '%software%'
          OR object_text ~* '(^|[^[:alpha:]])ti([^[:alpha:]]|$)'
          OR object_text ILIKE '%tecnologia%'
          OR object_text ILIKE '%sistema%'
          OR object_text ILIKE '%informática%'
        THEN 'TI'
        WHEN object_text ILIKE '%transporte%'
          OR object_text ILIKE '%veículo%'
          OR object_text ILIKE '%frota%'
          OR object_text ILIKE '%ônibus%'
          OR object_text ILIKE '%locação de veículo%'
        THEN 'TRANSPORTE'
        WHEN object_text ILIKE '%segurança%'
          OR object_text ILIKE '%vigilância%'
          OR object_text ILIKE '%monitoramento%'
          OR object_text ILIKE '%porteiro%'
        THEN 'SEGURANÇA'
        WHEN object_text ILIKE '%consultoria%'
          OR object_text ILIKE '%assessoria%'
          OR object_text ILIKE '%advocacia%'
          OR object_text ILIKE '%jurídico%'
          OR object_text ILIKE '%contábil%'
        THEN 'CONSULTORIA'
        WHEN object_text ILIKE '%combustível%'
          OR object_text ILIKE '%gasolina%'
          OR object_text ILIKE '%diesel%'
          OR object_text ILIKE '%etanol%'
        THEN 'COMBUSTÍVEL'
        ELSE 'OUTROS'
    END
$category$;

COMMENT ON FUNCTION public.contract_category_v1(TEXT) IS
'Canonical contract category ladder v1. TI uses a lexical token, never an unconstrained substring.';

CREATE OR REPLACE VIEW public.v_contract_intel_percentis AS
WITH categorias AS (
    SELECT
        c.valor_total AS valor,
        public.contract_category_v1(c.objeto_contrato) AS categoria_agrupada
    FROM public.pncp_supplier_contracts c
    WHERE c.is_active IS TRUE
      AND c.valor_total IS NOT NULL
      AND c.valor_total > 0
      AND (c.data_inicio IS NOT NULL OR c.data_publicacao IS NOT NULL)
      AND EXISTS (
          SELECT 1
          FROM public.v_target_universe_active u
          WHERE u.cnpj8 = LEFT(c.orgao_cnpj, 8)
      )
)
SELECT
    categoria_agrupada AS categoria,
    COUNT(*) AS qtd_contratos,
    ROUND(SUM(valor)::numeric, 2) AS valor_total,
    ROUND(AVG(valor)::numeric, 2) AS ticket_medio,
    ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY valor)::numeric, 2) AS p25_valor,
    ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY valor)::numeric, 2) AS p50_valor,
    ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY valor)::numeric, 2) AS p75_valor
FROM categorias
GROUP BY categoria_agrupada
ORDER BY valor_total DESC;

COMMENT ON VIEW public.v_contract_intel_percentis IS
'Regional P25/P50/P75 contract-value reference over the active, versioned 200 km target universe. Nominal PNCP valor_global, not unit price and not a national sample.';

DROP VIEW IF EXISTS public.v_contract_intel_reference_scopes_v1;

CREATE VIEW public.v_contract_intel_reference_scopes_v1 AS
WITH regional_run AS (
    SELECT
        r.id,
        r.seed_sha256,
        r.radius_km,
        r.total_rows,
        r.included_rows,
        r.excluded_rows,
        r.unresolved_rows,
        r.created_at,
        r.git_sha
    FROM public.target_universe_runs r
    ORDER BY r.id DESC
    LIMIT 1
),
regional_entities AS (
    SELECT COUNT(DISTINCT u.cnpj8)::bigint AS entity_count
    FROM public.v_target_universe_active u
),
regional_corpus AS (
    SELECT
        COUNT(*)::bigint AS active_contracts,
        COUNT(*) FILTER (WHERE c.valor_total IS NOT NULL AND c.valor_total > 0)::bigint AS eligible_contracts,
        COUNT(*) FILTER (WHERE c.valor_total IS NULL OR c.valor_total <= 0)::bigint AS missing_or_nonpositive_values,
        MAX(c.data_publicacao)::text AS max_data_publicacao,
        MAX(c.ingested_at)::text AS max_ingested_at
    FROM public.pncp_supplier_contracts c
    WHERE c.is_active IS TRUE
      AND (c.data_inicio IS NOT NULL OR c.data_publicacao IS NOT NULL)
      AND EXISTS (
          SELECT 1
          FROM public.v_target_universe_active u
          WHERE u.cnpj8 = LEFT(c.orgao_cnpj, 8)
      )
),
latest_national AS (
    SELECT a.*
    FROM public.national_coverage_answer a
    WHERE UPPER(BTRIM(a.requested_geography)) IN ('BR', 'BRASIL', 'BRAZIL', 'NATIONAL', 'NACIONAL')
      AND LOWER(BTRIM(a.requested_source)) = 'pncp'
      AND LOWER(BTRIM(a.requested_grain)) = 'publishing_org'
    ORDER BY a.produced_at DESC, a.id DESC
    LIMIT 1
),
regional AS (
    SELECT
        'REGIONAL'::text AS scope_kind,
        ('regional_200km:target_universe_run:' || r.id)::text AS scope_id,
        'DATA_READY'::text AS reference_state,
        jsonb_build_object(
            'kind', 'radius',
            'center', 'Florianopolis/SC reference base',
            'radius_km', r.radius_km,
            'universe_run_id', r.id,
            'inclusion_rate_pct', CASE WHEN r.total_rows > 0
                 THEN ROUND(100 * r.included_rows::numeric / r.total_rows::numeric, 4)
                 ELSE NULL::numeric
            END
        ) AS geography,
        jsonb_build_object(
            'seed_rows', r.total_rows,
            'included_rows', r.included_rows,
            'excluded_rows', r.excluded_rows,
            'unresolved_rows', r.unresolved_rows,
            'distinct_entity_roots', e.entity_count,
            'active_contracts', c.active_contracts,
            'eligible_contracts', c.eligible_contracts,
            'missing_or_nonpositive_values', c.missing_or_nonpositive_values
        ) AS denominator,
        c.max_ingested_at AS as_of,
        'target_universe_runs+pncp_supplier_contracts'::text AS source_id,
        COALESCE(r.git_sha, 'UNKNOWN')::text AS source_version,
        p.qtd_contratos::bigint AS sample_count,
        CASE WHEN r.total_rows > 0
             THEN ROUND(100 * (r.included_rows + r.excluded_rows)::numeric / r.total_rows::numeric, 4)
             ELSE NULL::numeric
        END AS coverage,
        jsonb_build_object(
            'unresolved_entities', r.unresolved_rows,
            'missing_or_nonpositive_values', c.missing_or_nonpositive_values,
            'value_missingness_pct', CASE WHEN c.active_contracts > 0
                 THEN ROUND(100 * c.missing_or_nonpositive_values::numeric / c.active_contracts::numeric, 4)
                 ELSE NULL::numeric
            END,
            'max_data_publicacao', c.max_data_publicacao
        ) AS missingness,
        jsonb_build_object(
            'classifier', 'public.contract_category_v1',
            'classifier_version', 'v1',
            'coverage_definition', '(included_rows + excluded_rows) / total_rows',
            'population', 'public.pncp_supplier_contracts with canonical_v2 eligibility intersect public.v_target_universe_active',
            'filters', jsonb_build_array(
                'canonical_v2_temporal_eligibility',
                'is_active=true',
                'valor>0',
                'buyer_cnpj8 in active target universe'
            ),
            'percentiles', 'percentile_cont(0.25,0.50,0.75)'
        ) AS method,
        ('sha256:' || r.seed_sha256)::text AS reference_hash,
        ARRAY[
            'Regional radius reference; not a national sample.',
            'PNCP valor_global is a nominal whole-contract value, not unit price.'
        ]::text[] AS limitations,
        p.categoria,
        p.qtd_contratos,
        p.valor_total,
        p.ticket_medio,
        p.p25_valor,
        p.p50_valor,
        p.p75_valor
    FROM public.v_contract_intel_percentis p
    CROSS JOIN regional_run r
    CROSS JOIN regional_entities e
    CROSS JOIN regional_corpus c
),
national_hold AS (
    SELECT
        'NATIONAL'::text AS scope_kind,
        COALESCE('national:' || n.universe_id, 'national:unavailable')::text AS scope_id,
        'DATA_HOLD'::text AS reference_state,
        jsonb_build_object('kind', 'country', 'country', 'BR') AS geography,
        jsonb_build_object(
            'expected_partitions', n.expected_partitions,
            'queried_partitions', n.queried_partitions,
            'closed_partitions', n.closed_partitions,
            'eligible_contracts', NULL
        ) AS denominator,
        COALESCE(n.payload ->> 'as_of', n.provenance ->> 'as_of') AS as_of,
        COALESCE(n.requested_source, 'national_coverage_authority')::text AS source_id,
        COALESCE(
            NULLIF(
                CONCAT_WS(
                    '+',
                    n.provenance ->> 'schema_version',
                    n.provenance ->> 'method_version',
                    n.provenance ->> 'core_method_version'
                ),
                ''
            ),
            'UNKNOWN'
        )::text AS source_version,
        NULL::bigint AS sample_count,
        n.coverage_pct,
        jsonb_build_object(
            'unclosed_partitions', CASE WHEN n.expected_partitions IS NOT NULL
                 THEN n.expected_partitions - n.closed_partitions ELSE NULL END,
            'partition_missingness_pct', CASE WHEN n.expected_partitions > 0
                 THEN ROUND(100 * (n.expected_partitions - n.closed_partitions)::numeric / n.expected_partitions::numeric, 4)
                 ELSE NULL::numeric
            END
        ) AS missingness,
        jsonb_build_object(
            'classifier', 'public.contract_category_v1',
            'classifier_version', 'v1',
            'coverage_definition', 'closed_partitions / expected_partitions',
            'status', 'withheld_until_authoritative_comparable_corpus'
        ) AS method,
        COALESCE(n.content_hash, 'UNKNOWN')::text AS reference_hash,
        ARRAY[
            'No national percentile or position is published without an authorized national denominator and comparable corpus.',
            'Observed row inventory does not prove national coverage.'
        ]::text[] || COALESCE(n.limitations, ARRAY[]::text[]) AS limitations,
        NULL::text AS categoria,
        NULL::bigint AS qtd_contratos,
        NULL::numeric AS valor_total,
        NULL::numeric AS ticket_medio,
        NULL::numeric AS p25_valor,
        NULL::numeric AS p50_valor,
        NULL::numeric AS p75_valor
    FROM (SELECT 1) anchor
    LEFT JOIN latest_national n ON TRUE
)
SELECT * FROM regional
UNION ALL
SELECT * FROM national_hold;

COMMENT ON VIEW public.v_contract_intel_reference_scopes_v1 IS
'Explicit regional and national reference contracts. National stays DATA_HOLD and contains no percentiles until both coverage authority and a comparable corpus exist.';

REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON public.v_contract_intel_reference_scopes_v1 FROM PUBLIC;
GRANT SELECT ON public.v_contract_intel_reference_scopes_v1 TO PUBLIC;

COMMIT;
