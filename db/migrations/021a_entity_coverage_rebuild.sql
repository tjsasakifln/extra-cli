-- Migration 021: COVERAGE-2.4 — Entity Coverage Rebuild
-- Reconstroi a tabela entity_coverage com dados de todas as fontes das Fases 1 e 2,
-- adiciona suporte a match_method, corrige triggers, e implementa comandos de rebuild.
--
-- Fonte: Story COVERAGE-2.4
--
-- Problemas corrigidos:
--   1. entity_coverage sem coluna match_method (necessario para COVERAGE-1.8 hierarquico)
--   2. Triggers de coverage desativados (nao acionam em INSERT/UPDATE)
--   3. Apenas fontes pncp e ciga_ckan populadas — faltam dom_sc, pcp, compras_gov,
--      sc_compras, doe_sc, mides_bigquery, transparencia
--   4. v_unmatched_bids nao existe no banco (definido na migration 011 mas nunca aplicado)
--   5. View v_coverage_trend ausente
--   6. Funcao generate_coverage_snapshot ausente
--
-- Depende de: migration 020 (entity_coverage table, sc_public_entities, pncp_raw_bids)
-- Idempotente: Sim (CREATE OR REPLACE, IF NOT EXISTS, DO $$ blocks)

BEGIN;

-- ============================================================
-- 1. Add match_method column to entity_coverage
-- ============================================================
ALTER TABLE public.entity_coverage
    ADD COLUMN IF NOT EXISTS match_method TEXT;

COMMENT ON COLUMN public.entity_coverage.match_method IS
    'Metodo de match: direct|cnpj_fallback|hierarchical|name_match — adicionado por COVERAGE-2.4';

-- ============================================================
-- 2. Initialize coverage for ALL known sources
-- Fontes das Fases 1 e 2 do EPIC-COVERAGE-100PCT:
--   - pncp (PNCP API)
--   - dom_sc (DOM-SC)
--   - pcp (Portal de Compras Publicas)
--   - compras_gov (Compras Governamentais)
--   - ciga_ckan (CIGA CKAN)
--   - sc_compras (SC Compras)
--   - doe_sc (DOE-SC)
--   - mides_bigquery (MiDES BigQuery)
--   - transparencia (Portal Transparencia)
-- ============================================================
INSERT INTO public.entity_coverage (entity_id, source, is_covered, within_200km)
SELECT e.id, s.source, FALSE, COALESCE(e.raio_200km, FALSE)
FROM public.sc_public_entities e
CROSS JOIN (VALUES
    ('pncp'),
    ('dom_sc'),
    ('pcp'),
    ('compras_gov'),
    ('ciga_ckan'),
    ('sc_compras'),
    ('doe_sc'),
    ('mides_bigquery'),
    ('transparencia')
) AS s(source)
WHERE e.is_active = TRUE
ON CONFLICT (entity_id, source) DO NOTHING;

-- ============================================================
-- 3. Rebuild coverage from actual bid data
-- ============================================================

-- Step 3a: Direct matches via matched_entity_id
UPDATE public.entity_coverage ec
SET
    is_covered = TRUE,
    last_seen_at = b.latest_pub,
    total_bids = b.bid_count,
    match_method = 'direct'
FROM (
    SELECT
        matched_entity_id AS entity_id,
        source,
        MAX(data_publicacao) AS latest_pub,
        COUNT(*) AS bid_count
    FROM public.pncp_raw_bids
    WHERE matched_entity_id IS NOT NULL
      AND is_active = TRUE
    GROUP BY matched_entity_id, source
) b
WHERE ec.entity_id = b.entity_id
  AND ec.source = b.source;

-- Step 3b: CNPJ-8 fallback for matched bids
UPDATE public.entity_coverage ec
SET
    is_covered = TRUE,
    last_seen_at = b.latest_pub,
    total_bids = b.bid_count,
    match_method = 'cnpj_fallback'
FROM (
    SELECT
        e.id AS entity_id,
        b.source,
        MAX(b.data_publicacao) AS latest_pub,
        COUNT(*) AS bid_count
    FROM public.pncp_raw_bids b
    JOIN public.sc_public_entities e ON LEFT(b.orgao_cnpj, 8) = e.cnpj_8
    WHERE b.matched_entity_id IS NULL
      AND b.orgao_cnpj IS NOT NULL
      AND b.is_active = TRUE
      AND e.is_active = TRUE
    GROUP BY e.id, b.source
) b
WHERE ec.entity_id = b.entity_id
  AND ec.source = b.source
  AND ec.is_covered = FALSE;  -- so update if not already covered

-- Step 3c: Name-based matches (using match_method from pncp_raw_bids)
UPDATE public.entity_coverage ec
SET
    is_covered = TRUE,
    last_seen_at = b.latest_pub,
    total_bids = b.bid_count,
    match_method = 'name_match'
FROM (
    SELECT
        matched_entity_id AS entity_id,
        source,
        MAX(data_publicacao) AS latest_pub,
        COUNT(*) AS bid_count
    FROM public.pncp_raw_bids
    WHERE matched_entity_id IS NOT NULL
      AND match_method IN ('name_fuzzy', 'name_contains', 'name_normalized')
      AND is_active = TRUE
    GROUP BY matched_entity_id, source
) b
WHERE ec.entity_id = b.entity_id
  AND ec.source = b.source
  AND ec.is_covered = FALSE;

-- ============================================================
-- 4. Recreate trigger functions with full source support
-- ============================================================

-- Trigger function: update entity_coverage on bid INSERT
CREATE OR REPLACE FUNCTION public.update_entity_coverage()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.matched_entity_id IS NOT NULL THEN
        INSERT INTO public.entity_coverage (
            entity_id, source, last_seen_at, total_bids, is_covered, within_200km, match_method
        )
        VALUES (
            NEW.matched_entity_id,
            NEW.source,
            NEW.data_publicacao,
            1,
            COALESCE(NEW.data_publicacao >= CURRENT_DATE - 90, FALSE),
            COALESCE((SELECT raio_200km FROM public.sc_public_entities WHERE id = NEW.matched_entity_id), FALSE),
            COALESCE(NEW.match_method, 'direct')
        )
        ON CONFLICT (entity_id, source) DO UPDATE
        SET
            last_seen_at = GREATEST(
                COALESCE(public.entity_coverage.last_seen_at, '1970-01-01'::date),
                COALESCE(NEW.data_publicacao, '1970-01-01'::date)
            ),
            total_bids = public.entity_coverage.total_bids + 1,
            is_covered = GREATEST(
                COALESCE(public.entity_coverage.last_seen_at, '1970-01-01'::date),
                COALESCE(NEW.data_publicacao, '1970-01-01'::date)
            ) >= CURRENT_DATE - 90,
            match_method = CASE
                WHEN public.entity_coverage.match_method IN ('direct', 'hierarchical') THEN public.entity_coverage.match_method
                ELSE COALESCE(NEW.match_method, 'direct')
            END;
    END IF;
    RETURN NEW;
END;
$$;

-- Trigger function: update when matched_entity_id is set after initial insert
CREATE OR REPLACE FUNCTION public.update_entity_coverage_on_update()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.matched_entity_id IS NOT NULL
       AND (OLD.matched_entity_id IS NULL OR OLD.matched_entity_id <> NEW.matched_entity_id)
    THEN
        INSERT INTO public.entity_coverage (
            entity_id, source, last_seen_at, total_bids, is_covered, within_200km, match_method
        )
        VALUES (
            NEW.matched_entity_id,
            NEW.source,
            NEW.data_publicacao,
            1,
            COALESCE(NEW.data_publicacao >= CURRENT_DATE - 90, FALSE),
            COALESCE((SELECT raio_200km FROM public.sc_public_entities WHERE id = NEW.matched_entity_id), FALSE),
            COALESCE(NEW.match_method, 'direct')
        )
        ON CONFLICT (entity_id, source) DO UPDATE
        SET
            last_seen_at = GREATEST(
                COALESCE(public.entity_coverage.last_seen_at, '1970-01-01'::date),
                COALESCE(NEW.data_publicacao, '1970-01-01'::date)
            ),
            total_bids = public.entity_coverage.total_bids + 1,
            is_covered = GREATEST(
                COALESCE(public.entity_coverage.last_seen_at, '1970-01-01'::date),
                COALESCE(NEW.data_publicacao, '1970-01-01'::date)
            ) >= CURRENT_DATE - 90,
            match_method = CASE
                WHEN public.entity_coverage.match_method IN ('direct', 'hierarchical')
                THEN public.entity_coverage.match_method
                ELSE COALESCE(NEW.match_method, 'direct')
            END;
    END IF;
    RETURN NEW;
END;
$$;

-- Recreate triggers (drop first to avoid duplicates)
DROP TRIGGER IF EXISTS trg_bids_coverage ON public.pncp_raw_bids;
CREATE TRIGGER trg_bids_coverage
    AFTER INSERT ON public.pncp_raw_bids
    FOR EACH ROW
    EXECUTE FUNCTION public.update_entity_coverage();

DROP TRIGGER IF EXISTS trg_bids_coverage_update ON public.pncp_raw_bids;
CREATE TRIGGER trg_bids_coverage_update
    AFTER UPDATE ON public.pncp_raw_bids
    FOR EACH ROW
    WHEN (OLD.matched_entity_id IS DISTINCT FROM NEW.matched_entity_id)
    EXECUTE FUNCTION public.update_entity_coverage_on_update();

-- ============================================================
-- 5. Recreate v_unmatched_bids view (from migration 011)
-- ============================================================
CREATE OR REPLACE VIEW public.v_unmatched_bids AS
SELECT
    pncp_id,
    source,
    orgao_cnpj,
    orgao_razao_social,
    municipio,
    codigo_municipio_ibge,
    data_publicacao,
    match_method,
    match_score,
    match_confidence,
    ingested_at,
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
  AND (
    (orgao_cnpj IS NOT NULL AND orgao_cnpj != '')
    OR (orgao_razao_social IS NOT NULL AND orgao_razao_social != '')
  )
ORDER BY data_publicacao DESC NULLS LAST, ingested_at DESC;

COMMENT ON VIEW public.v_unmatched_bids IS
    'Bids sem matched_entity_id — para debugging do entity name-matching';

COMMENT ON COLUMN public.v_unmatched_bids.match_opportunity IS
    'Indica se o bid tem CNPJ (has_cnpj) ou apenas nome (name_only) para match';
COMMENT ON COLUMN public.v_unmatched_bids.recency IS
    'Indica se o bid e recente (90 dias) ou historico';

-- ============================================================
-- 6. Create missing views (v_coverage_trend, generate_coverage_snapshot)
-- ============================================================

-- v_coverage_trend — from migration 012
CREATE OR REPLACE VIEW public.v_coverage_trend AS
SELECT
    snapshot_date,
    source,
    total_entities,
    covered_entities,
    pct_covered,
    pct_covered - LAG(pct_covered) OVER (
        PARTITION BY source ORDER BY snapshot_date
    ) AS variacao_pct,
    ROW_NUMBER() OVER (PARTITION BY source ORDER BY snapshot_date DESC) AS rn_desc
FROM public.coverage_snapshots
ORDER BY snapshot_date DESC, source;

COMMENT ON VIEW public.v_coverage_trend IS
    'Evolucao semanal da cobertura com calculo de variacao';

-- generate_coverage_snapshot() function — from migration 012
CREATE OR REPLACE FUNCTION public.generate_coverage_snapshot(snap_date DATE DEFAULT CURRENT_DATE)
RETURNS INT
LANGUAGE plpgsql AS $$
DECLARE
    inserted INT := 0;
    rec RECORD;
BEGIN
    FOR rec IN
        SELECT
            ec.source,
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
        VALUES (
            snap_date,
            rec.source,
            rec.total_entities,
            rec.covered_entities,
            ROUND(100.0 * rec.covered_entities / NULLIF(rec.total_entities, 0), 2)
        )
        ON CONFLICT DO NOTHING;
        inserted := inserted + 1;
    END LOOP;

    RETURN inserted;
END;
$$;

COMMENT ON FUNCTION public.generate_coverage_snapshot IS
    'Gera snapshot de cobertura para todas as fontes';

-- ============================================================
-- 7. Recreate v_coverage_summary (with public prefix)
-- ============================================================
CREATE OR REPLACE VIEW public.v_coverage_summary AS
SELECT
    ec.source,
    ec.within_200km,
    ec.is_covered,
    COUNT(*) AS entity_count,
    ROUND(
        (COUNT(*)::NUMERIC * 100.0) / NULLIF(SUM(COUNT(*)) OVER (PARTITION BY ec.within_200km), 0), 1
    ) AS pct
FROM public.entity_coverage ec
WHERE EXISTS (
    SELECT 1 FROM public.sc_public_entities e
    WHERE e.id = ec.entity_id AND e.is_active = TRUE
)
GROUP BY ec.source, ec.within_200km, ec.is_covered
ORDER BY ec.source, ec.within_200km, ec.is_covered;

COMMENT ON VIEW public.v_coverage_summary IS
    'Sumario de cobertura por source e raio_200km — COVERAGE-2.4';

-- ============================================================
-- 8. Consistency check: find entities with bids but no coverage
-- ============================================================

-- Log inconsistencies (these should be resolved by the rebuild above)
DO $$
DECLARE
    inconsistent_count INT;
BEGIN
    SELECT COUNT(*) INTO inconsistent_count
    FROM public.sc_public_entities e
    WHERE e.id IN (
        SELECT DISTINCT matched_entity_id FROM public.pncp_raw_bids
        WHERE matched_entity_id IS NOT NULL
    )
    AND NOT EXISTS (
        SELECT 1 FROM public.entity_coverage ec
        WHERE ec.entity_id = e.id AND ec.is_covered = TRUE
    );

    IF inconsistent_count > 0 THEN
        RAISE WARNING 'Entities with bids but no coverage after rebuild: %', inconsistent_count;
    ELSE
        RAISE NOTICE 'All entities with bids now have coverage — consistent.';
    END IF;
END $$;

-- ============================================================
-- 9. Recreate v_coverage_gaps (public schema)
-- ============================================================
CREATE OR REPLACE VIEW public.v_coverage_gaps AS
SELECT
    e.id,
    e.razao_social,
    e.cnpj_8,
    e.municipio,
    e.natureza_juridica,
    e.raio_200km,
    e.distancia_fk,
    ARRAY(
        SELECT ec.source
        FROM public.entity_coverage ec
        WHERE ec.entity_id = e.id AND ec.is_covered = TRUE
    ) AS fontes_ativas,
    (
        SELECT COUNT(DISTINCT ec2.source)
        FROM public.entity_coverage ec2
        WHERE ec2.entity_id = e.id AND ec2.is_covered = TRUE
    ) = 0 AS gap_total
FROM public.sc_public_entities e
WHERE e.is_active = TRUE
  AND NOT EXISTS (
      SELECT 1 FROM public.entity_coverage ec
      WHERE ec.entity_id = e.id AND ec.is_covered = TRUE
  )
ORDER BY e.municipio, e.razao_social;

COMMENT ON VIEW public.v_coverage_gaps IS
    'Entes publicos com gap TOTAL de cobertura — COVERAGE-2.4';

-- ============================================================
-- 10. Metadata tracking
-- ============================================================
CREATE TABLE IF NOT EXISTS public._migrations (
    version     TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    checksum    TEXT,
    rollback_sql TEXT
);

INSERT INTO public._migrations (version, name, applied_at, checksum, rollback_sql)
VALUES (
    '021',
    'coverage-2.4_entity_coverage_rebuild',
    NOW(),
    'sha256=coverage-2-4-manual',
    'ALTER TABLE public.entity_coverage DROP COLUMN IF EXISTS match_method; DROP TRIGGER IF EXISTS trg_bids_coverage ON public.pncp_raw_bids; DROP TRIGGER IF EXISTS trg_bids_coverage_update ON public.pncp_raw_bids; DROP VIEW IF EXISTS public.v_unmatched_bids CASCADE; DROP VIEW IF EXISTS public.v_coverage_trend CASCADE; DROP FUNCTION IF EXISTS public.generate_coverage_snapshot;'
)
ON CONFLICT (version) DO NOTHING;

COMMIT;
