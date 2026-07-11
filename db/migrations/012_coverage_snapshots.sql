-- Migration 012: Coverage snapshots + gap views for weekly report
-- Story 001.7: Weekly Coverage Report Automation
--
-- Dependencias: Migration 009 (entity_coverage, v_coverage_summary)
--               Migration 007 (sc_public_entities)

-- ============================================================
-- 1. coverage_snapshots — tracking historico semanal
-- ============================================================
CREATE TABLE IF NOT EXISTS coverage_snapshots (
    id              SERIAL PRIMARY KEY,
    snapshot_date   DATE NOT NULL DEFAULT CURRENT_DATE,
    source          TEXT NOT NULL,
    total_entities  INT NOT NULL,
    covered_entities INT NOT NULL,
    pct_covered     DECIMAL(5,2) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cov_snap_date ON coverage_snapshots (snapshot_date);
CREATE INDEX IF NOT EXISTS idx_cov_snap_source ON coverage_snapshots (source, snapshot_date);

COMMENT ON TABLE coverage_snapshots IS
    'Snapshots semanais de cobertura por fonte — usado para tendencia no relatorio semanal (Story 001.7)';

-- ============================================================
-- 2. v_coverage_gaps — entes sem cobertura em NENHUMA fonte
-- ============================================================
CREATE OR REPLACE VIEW v_coverage_gaps AS
SELECT
    e.id,
    e.razao_social,
    e.cnpj_8,
    e.municipio,
    e.natureza_juridica,
    -- e.uf, (removed - column does not exist)
    e.raio_200km,
    e.distancia_fk,
    ARRAY(
        SELECT ec.source
        FROM entity_coverage ec
        WHERE ec.entity_id = e.id AND ec.is_covered = TRUE
    ) AS fontes_ativas,
    (
        SELECT COUNT(DISTINCT ec2.source)
        FROM entity_coverage ec2
        WHERE ec2.entity_id = e.id AND ec2.is_covered = TRUE
    ) = 0 AS gap_total
FROM sc_public_entities e
WHERE e.is_active = TRUE
  AND NOT EXISTS (
      SELECT 1 FROM entity_coverage ec
      WHERE ec.entity_id = e.id AND ec.is_covered = TRUE
  )
ORDER BY e.municipio, e.razao_social;

COMMENT ON VIEW v_coverage_gaps IS
    'Entes publicos com gap TOTAL de cobertura (is_covered = FALSE em todas as fontes) — Story 001.5/001.7';

-- ============================================================
-- 3. v_coverage_gaps_by_municipio — gaps agregados por cidade
-- ============================================================
CREATE OR REPLACE VIEW v_coverage_gaps_by_municipio AS
SELECT
    e.municipio,
    COUNT(*) AS total_entes,
    COUNT(*) FILTER (WHERE NOT EXISTS (
        SELECT 1 FROM entity_coverage ec
        WHERE ec.entity_id = e.id AND ec.is_covered = TRUE
    )) AS entes_descobertos,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE NOT EXISTS (
            SELECT 1 FROM entity_coverage ec
            WHERE ec.entity_id = e.id AND ec.is_covered = TRUE
        )) / NULLIF(COUNT(*), 0),
        1
    ) AS pct_gap,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE EXISTS (
            SELECT 1 FROM entity_coverage ec
            WHERE ec.entity_id = e.id AND ec.is_covered = TRUE
        )) / NULLIF(COUNT(*), 0),
        1
    ) AS pct_coberto
FROM sc_public_entities e
WHERE e.is_active = TRUE
GROUP BY e.municipio
ORDER BY entes_descobertos DESC, pct_gap DESC;

COMMENT ON VIEW v_coverage_gaps_by_municipio IS
    'Agregacao de gaps de cobertura por municipio — Story 001.5/001.7';

-- ============================================================
-- 4. v_coverage_trend — evolucao semanal da cobertura
-- ============================================================
CREATE OR REPLACE VIEW v_coverage_trend AS
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
FROM coverage_snapshots
ORDER BY snapshot_date DESC, source;

COMMENT ON VIEW v_coverage_trend IS
    'Evolucao semanal da cobertura com calculo de variacao — Story 001.5/001.7';

-- ============================================================
-- 5. generate_coverage_snapshot() — funcao para gerar snapshot manual
-- ============================================================
CREATE OR REPLACE FUNCTION generate_coverage_snapshot(snap_date DATE DEFAULT CURRENT_DATE)
RETURNS INT AS $$
DECLARE
    inserted INT := 0;
    rec RECORD;
BEGIN
    FOR rec IN
        SELECT
            ec.source,
            COUNT(*) AS total_entities,
            SUM(CASE WHEN ec.is_covered THEN 1 ELSE 0 END) AS covered_entities
        FROM entity_coverage ec
        WHERE EXISTS (
            SELECT 1 FROM sc_public_entities e
            WHERE e.id = ec.entity_id AND e.is_active = TRUE
        )
        GROUP BY ec.source
    LOOP
        INSERT INTO coverage_snapshots (snapshot_date, source, total_entities, covered_entities, pct_covered)
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
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION generate_coverage_snapshot IS
    'Gera snapshot de cobertura para todos as fontes — chamado pelo timer semanal (Story 001.7)';
