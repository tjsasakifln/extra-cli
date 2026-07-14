-- Migration 022: Add match_method column to entity_coverage
-- Story COVERAGE-1.8: Match Hierarquico Secretaria → Prefeitura
--
-- Adiciona coluna match_method a entity_coverage para distinguir
-- cobertura direta (CNPJ match) de cobertura hierarquica (herdada
-- da prefeitura via entity_hierarchy).
--
-- Dependencias: Migration 021 (entity_hierarchy)
--               Migration 009 (entity_coverage)

-- ============================================================
-- 1. Add match_method column
-- ============================================================
ALTER TABLE entity_coverage
    ADD COLUMN IF NOT EXISTS match_method TEXT;

COMMENT ON COLUMN entity_coverage.match_method IS
    'Metodo de cobertura: direct (match CNPJ) | hierarchical (herdado via entity_hierarchy) | null (sem cobertura)';

-- ============================================================
-- 2. Update trigger functions to include match_method
-- ============================================================

-- Recreate INSERT trigger with match_method support
CREATE OR REPLACE FUNCTION update_entity_coverage()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.matched_entity_id IS NOT NULL THEN
        INSERT INTO entity_coverage (entity_id, source, last_seen_at, total_bids, is_covered, within_200km, match_method)
        VALUES (
            NEW.matched_entity_id,
            NEW.source,
            NEW.data_publicacao,
            1,
            COALESCE(NEW.data_publicacao >= CURRENT_DATE - 90, FALSE),
            COALESCE((SELECT raio_200km FROM sc_public_entities WHERE id = NEW.matched_entity_id), FALSE),
            COALESCE(NEW.match_method, 'direct')
        )
        ON CONFLICT (entity_id, source) DO UPDATE
        SET
            last_seen_at = GREATEST(
                COALESCE(entity_coverage.last_seen_at, '1970-01-01'::date),
                COALESCE(NEW.data_publicacao, '1970-01-01'::date)
            ),
            total_bids = entity_coverage.total_bids + 1,
            is_covered = (
                GREATEST(
                    COALESCE(entity_coverage.last_seen_at, '1970-01-01'::date),
                    COALESCE(NEW.data_publicacao, '1970-01-01'::date)
                ) >= CURRENT_DATE - 90
            ),
            match_method = CASE
                WHEN entity_coverage.match_method IS NULL OR entity_coverage.match_method = 'hierarchical' THEN
                    COALESCE(NEW.match_method, 'direct')
                ELSE entity_coverage.match_method
            END;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Recreate UPDATE trigger with match_method support
CREATE OR REPLACE FUNCTION update_entity_coverage_on_update()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.matched_entity_id IS NOT NULL
       AND (OLD.matched_entity_id IS NULL OR OLD.matched_entity_id <> NEW.matched_entity_id)
    THEN
        INSERT INTO entity_coverage (entity_id, source, last_seen_at, total_bids, is_covered, within_200km, match_method)
        VALUES (
            NEW.matched_entity_id,
            NEW.source,
            NEW.data_publicacao,
            1,
            COALESCE(NEW.data_publicacao >= CURRENT_DATE - 90, FALSE),
            COALESCE((SELECT raio_200km FROM sc_public_entities WHERE id = NEW.matched_entity_id), FALSE),
            COALESCE(NEW.match_method, 'direct')
        )
        ON CONFLICT (entity_id, source) DO UPDATE
        SET
            last_seen_at = GREATEST(
                COALESCE(entity_coverage.last_seen_at, '1970-01-01'::date),
                COALESCE(NEW.data_publicacao, '1970-01-01'::date)
            ),
            total_bids = entity_coverage.total_bids + 1,
            is_covered = (
                GREATEST(
                    COALESCE(entity_coverage.last_seen_at, '1970-01-01'::date),
                    COALESCE(NEW.data_publicacao, '1970-01-01'::date)
                ) >= CURRENT_DATE - 90
            ),
            match_method = CASE
                WHEN entity_coverage.match_method IS NULL OR entity_coverage.match_method = 'hierarchical' THEN
                    COALESCE(NEW.match_method, 'direct')
                ELSE entity_coverage.match_method
            END;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- 3. Index for match_method queries
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_cov_match_method
    ON entity_coverage (match_method)
    WHERE match_method IS NOT NULL;

-- ============================================================
-- 4. Update v_coverage_summary to include match_method
-- ============================================================
-- B2G-FIX-04: DROP first because CREATE OR REPLACE cannot rename columns
DROP VIEW IF EXISTS v_coverage_summary;
CREATE OR REPLACE VIEW v_coverage_summary AS
SELECT
    ec.source,
    ec.within_200km,
    ec.is_covered,
    ec.match_method,
    COUNT(*) AS entity_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY ec.within_200km), 1) AS pct
FROM entity_coverage ec
WHERE EXISTS (SELECT 1 FROM sc_public_entities e WHERE e.id = ec.entity_id AND e.is_active = TRUE)
GROUP BY ec.source, ec.within_200km, ec.is_covered, ec.match_method
ORDER BY ec.source, ec.within_200km, ec.is_covered, ec.match_method;
