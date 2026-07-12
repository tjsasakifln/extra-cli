-- Migration 021b: Views and functions for COVERAGE-2.4
-- Executed after 021a (column, data, triggers)

BEGIN;

-- 5. v_unmatched_bids view
CREATE OR REPLACE VIEW public.v_unmatched_bids AS
SELECT
    pncp_id, source, orgao_cnpj, orgao_razao_social,
    municipio, codigo_municipio_ibge, data_publicacao,
    match_method, match_score, match_confidence, ingested_at,
    CASE
        WHEN orgao_cnpj IS NOT NULL AND orgao_cnpj != '' THEN 'has_cnpj'
        ELSE 'name_only'
    END AS match_opportunity,
    CASE
        WHEN data_publicacao >= CURRENT_DATE - 90 THEN 'recent'
        ELSE 'historical'
    END AS recency
FROM public.pncp_raw_bids
WHERE matched_entity_id IS NULL
  AND ((orgao_cnpj IS NOT NULL AND orgao_cnpj != '')
       OR (orgao_razao_social IS NOT NULL AND orgao_razao_social != ''))
ORDER BY data_publicacao DESC NULLS LAST, ingested_at DESC;

COMMENT ON VIEW public.v_unmatched_bids IS
    'Bids sem matched_entity_id — para debugging do entity name-matching';

-- 6. v_coverage_trend
CREATE OR REPLACE VIEW public.v_coverage_trend AS
SELECT
    snapshot_date, source, total_entities, covered_entities, pct_covered,
    pct_covered - LAG(pct_covered) OVER (
        PARTITION BY source ORDER BY snapshot_date
    ) AS variacao_pct,
    ROW_NUMBER() OVER (PARTITION BY source ORDER BY snapshot_date DESC) AS rn_desc
FROM public.coverage_snapshots
ORDER BY snapshot_date DESC, source;

COMMENT ON VIEW public.v_coverage_trend IS
    'Evolucao semanal da cobertura com calculo de variacao';

-- generate_coverage_snapshot function
CREATE OR REPLACE FUNCTION public.generate_coverage_snapshot(snap_date DATE DEFAULT CURRENT_DATE)
RETURNS INT
LANGUAGE plpgsql AS $$
DECLARE
    inserted INT := 0;
    rec RECORD;
BEGIN
    FOR rec IN
        SELECT ec.source,
               COUNT(*) AS total_entities,
               SUM(CASE WHEN ec.is_covered THEN 1 ELSE 0 END) AS covered_entities
        FROM public.entity_coverage ec
        WHERE EXISTS (
            SELECT 1 FROM public.sc_public_entities e
            WHERE e.id = ec.entity_id AND e.is_active = TRUE
        )
        GROUP BY ec.source
    LOOP
        INSERT INTO public.coverage_snapshots (snapshot_date, source, total_entities, covered_entities, pct_covered)
        VALUES (snap_date, rec.source, rec.total_entities, rec.covered_entities,
                ROUND(100.0 * rec.covered_entities / NULLIF(rec.total_entities, 0), 2))
        ON CONFLICT DO NOTHING;
        inserted := inserted + 1;
    END LOOP;
    RETURN inserted;
END;
$$;

COMMENT ON FUNCTION public.generate_coverage_snapshot IS
    'Gera snapshot de cobertura para todas as fontes';

-- 7. v_coverage_summary (recreate with public schema)
CREATE OR REPLACE VIEW public.v_coverage_summary AS
SELECT ec.source, ec.within_200km, ec.is_covered,
       COUNT(*) AS entity_count,
       ROUND((COUNT(*)::NUMERIC * 100.0) / NULLIF(SUM(COUNT(*)) OVER (PARTITION BY ec.within_200km), 0), 1) AS pct
FROM public.entity_coverage ec
WHERE EXISTS (SELECT 1 FROM public.sc_public_entities e WHERE e.id = ec.entity_id AND e.is_active = TRUE)
GROUP BY ec.source, ec.within_200km, ec.is_covered
ORDER BY ec.source, ec.within_200km, ec.is_covered;

COMMENT ON VIEW public.v_coverage_summary IS
    'Sumario de cobertura por source e raio_200km — COVERAGE-2.4';

-- 9. v_coverage_gaps (recreate with public schema — drop first to avoid column mismatch)
DROP VIEW IF EXISTS public.v_coverage_gaps CASCADE;
CREATE OR REPLACE VIEW public.v_coverage_gaps AS
SELECT e.id, e.razao_social, e.cnpj_8, e.municipio,
       e.natureza_juridica, e.raio_200km,
       ARRAY(SELECT ec.source FROM public.entity_coverage ec
             WHERE ec.entity_id = e.id AND ec.is_covered = TRUE) AS fontes_ativas,
       (SELECT COUNT(DISTINCT ec2.source) FROM public.entity_coverage ec2
        WHERE ec2.entity_id = e.id AND ec2.is_covered = TRUE) = 0 AS gap_total
FROM public.sc_public_entities e
WHERE e.is_active = TRUE
  AND NOT EXISTS (SELECT 1 FROM public.entity_coverage ec
                  WHERE ec.entity_id = e.id AND ec.is_covered = TRUE)
ORDER BY e.municipio, e.razao_social;

COMMENT ON VIEW public.v_coverage_gaps IS
    'Entes publicos com gap TOTAL de cobertura — COVERAGE-2.4';

COMMIT;
