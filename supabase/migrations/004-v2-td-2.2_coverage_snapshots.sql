-- ============================================================================
-- 004-v2-td-2.2_coverage_snapshots.sql — Coverage Snapshots (Adaptada de v1 012)
-- ============================================================================
-- Story TD-2.2: Aplicar Migrations 009-012 Adaptadas
-- Debito: TD-DB-02a (HIGH) — coverage_snapshots ausente na cadeia de migrations
--
-- Adaptada da migration v1 012 (coverage_snapshots.sql) para o schema v2
-- baseline. coverage_snapshots ja existe no baseline (001-v2), mas esta
-- migration garante reexecutabilidade e registro em _migrations.
--
-- Inclui tambem as views de gap e trend que dependem de coverage_snapshots,
-- e a funcao generate_coverage_snapshot para geracao manual de snapshots.
--
-- Principios:
--   - Reexecutavel: IF NOT EXISTS / OR REPLACE
--   - Schema qualificado (public.)
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. Tabela coverage_snapshots
-- ============================================================================
CREATE SEQUENCE IF NOT EXISTS public.coverage_snapshots_id_seq
    AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;

CREATE TABLE IF NOT EXISTS public.coverage_snapshots (
    id               INTEGER NOT NULL,
    snapshot_date    DATE NOT NULL DEFAULT CURRENT_DATE,
    source           TEXT NOT NULL,
    total_entities   INTEGER NOT NULL,
    covered_entities INTEGER NOT NULL,
    pct_covered      NUMERIC(5,2) NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER SEQUENCE public.coverage_snapshots_id_seq OWNED BY public.coverage_snapshots.id;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = 'public.coverage_snapshots'::regclass AND attname = 'id' AND atthasdef) THEN
        ALTER TABLE ONLY public.coverage_snapshots ALTER COLUMN id SET DEFAULT nextval('public.coverage_snapshots_id_seq'::regclass);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'coverage_snapshots_pkey') THEN
        ALTER TABLE ONLY public.coverage_snapshots
            ADD CONSTRAINT coverage_snapshots_pkey PRIMARY KEY (id);
    END IF;
END $$;

-- ============================================================================
-- 2. Indexes
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_cov_snap_date ON public.coverage_snapshots USING btree (snapshot_date);
CREATE INDEX IF NOT EXISTS idx_cov_snap_source ON public.coverage_snapshots USING btree (source, snapshot_date);

-- ============================================================================
-- 3. Views de Gap e Trend
-- ============================================================================

-- 3.1 v_coverage_gaps — Entes sem cobertura em NENHUMA fonte
-- Ja existe no baseline 001-v2 (Section 4.1)
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
    'Entes publicos com gap TOTAL de cobertura (is_covered = FALSE em todas as fontes) — Story 001.5/001.7';

-- 3.2 v_coverage_gaps_by_municipio — Gaps agregados por cidade
-- Ja existe no baseline 001-v2 (Section 4.2)
CREATE OR REPLACE VIEW public.v_coverage_gaps_by_municipio AS
SELECT
    e.municipio,
    COUNT(*) AS total_entes,
    COUNT(*) FILTER (WHERE NOT EXISTS (
        SELECT 1 FROM public.entity_coverage ec
        WHERE ec.entity_id = e.id AND ec.is_covered = TRUE
    )) AS entes_descobertos,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE NOT EXISTS (
            SELECT 1 FROM public.entity_coverage ec
            WHERE ec.entity_id = e.id AND ec.is_covered = TRUE
        )) / NULLIF(COUNT(*), 0), 1
    ) AS pct_gap,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE EXISTS (
            SELECT 1 FROM public.entity_coverage ec
            WHERE ec.entity_id = e.id AND ec.is_covered = TRUE
        )) / NULLIF(COUNT(*), 0), 1
    ) AS pct_coberto
FROM public.sc_public_entities e
WHERE e.is_active = TRUE
GROUP BY e.municipio
ORDER BY entes_descobertos DESC, pct_gap DESC;

COMMENT ON VIEW public.v_coverage_gaps_by_municipio IS
    'Agregacao de gaps de cobertura por municipio — Story 001.5/001.7';

-- 3.3 v_coverage_trend — Evolucao semanal da cobertura
-- Ja existe no baseline 001-v2 (Section 4.4)
CREATE OR REPLACE VIEW public.v_coverage_trend AS
SELECT
    cs.snapshot_date,
    cs.source,
    cs.total_entities,
    cs.covered_entities,
    cs.pct_covered,
    cs.pct_covered - LAG(cs.pct_covered) OVER (
        PARTITION BY cs.source ORDER BY cs.snapshot_date
    ) AS variacao_pct,
    ROW_NUMBER() OVER (
        PARTITION BY cs.source ORDER BY cs.snapshot_date DESC
    ) AS rn_desc
FROM public.coverage_snapshots cs
ORDER BY cs.snapshot_date DESC, cs.source;

COMMENT ON VIEW public.v_coverage_trend IS
    'Evolucao semanal da cobertura com calculo de variacao — Story 001.5/001.7';

-- ============================================================================
-- 4. Funcao generate_coverage_snapshot
-- ============================================================================
-- Ja existe no baseline 001-v2 (Section 3.7)
CREATE OR REPLACE FUNCTION public.generate_coverage_snapshot(snap_date DATE DEFAULT CURRENT_DATE)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
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
    'Gera snapshot de cobertura para todos as fontes — chamado pelo timer semanal (Story 001.7)';

-- ============================================================================
-- 5. Comments
-- ============================================================================
COMMENT ON TABLE public.coverage_snapshots IS 'Snapshots semanais de cobertura por fonte — usado para tendencia no relatorio semanal (Story 001.7)';

-- ============================================================================
-- 6. Register in _migrations tracking table
-- ======================================================================
INSERT INTO public._migrations (version, name, applied_at, checksum, rollback_sql)
VALUES (
    '004-v2',
    'td-2.2_coverage_snapshots',
    NOW(),
    'sha256=996398741a91076cdf42314291f3199af6cc65c52bf4e1580f39f179189d83d0',
    'DROP TABLE IF EXISTS public.coverage_snapshots CASCADE;'
)
ON CONFLICT (version) DO NOTHING;

COMMIT;
