-- Migration 020: TD-2.4 — Sync local DataLake schema with expected schema
-- Aplica correcoes de schema drift identificadas durante validacao E2E.
--
-- Problemas corrigidos:
--   1. entity_coverage table missing
--   2. v_coverage_gaps_by_municipio view missing
--   3. ingestion_runs.source column missing
--   4. 3 stuck ingestion runs (IDs 3, 4, 5) reset to 'failed'
--   5. ingestion_checkpoints structure — add columns for sync API (checkpoint.py)
--
-- ADAPTACAO VS STORY ORIGINAL:
--   O banco local usa schema v2 (baseline 001-v2, nao v1 004/009/012).
--   Esta migration foi adaptada para:
--     - Usar public. prefix (v2 pattern)
--     - DO $$ blocks com IF NOT EXISTS para constraints (v2 pattern)
--     - ingestion_runs usa completed_at (nao finished_at) e metadata (jsonb)
--       em vez de error_message (colunas v2)
--     - ingestion_checkpoints adiciona scope_key, last_id, updated_at para
--       sync API mantendo colunas v2 existentes (uf, modalidade_id, etc.)
--     - Triggers criados condicionalmente (se matched_entity_id existir)
--       para evitar runtime error em INSERT
--
-- Depende de: supabase/migrations/001-v2_initial_schema.sql (ou equivalente)
--             sc_public_entities, pncp_raw_bids, ingestion_runs existentes
-- Idempotente: Sim (IF NOT EXISTS, CREATE OR REPLACE, DO $$ blocks)

BEGIN;

-- ============================================================
-- 1. entity_coverage table (schema v2 pattern)
-- Fonte: supabase/migrations/002-v2-td-2.2_entity_coverage.sql
-- ============================================================
CREATE TABLE IF NOT EXISTS public.entity_coverage (
    entity_id    INTEGER NOT NULL,
    source       TEXT NOT NULL,
    last_seen_at TIMESTAMPTZ,
    total_bids   INTEGER NOT NULL DEFAULT 0,
    is_covered   BOOLEAN NOT NULL DEFAULT FALSE,
    within_200km BOOLEAN NOT NULL DEFAULT FALSE
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'entity_coverage_pkey') THEN
        ALTER TABLE ONLY public.entity_coverage
            ADD CONSTRAINT entity_coverage_pkey PRIMARY KEY (entity_id, source);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'entity_coverage_entity_id_fkey') THEN
        ALTER TABLE ONLY public.entity_coverage
            ADD CONSTRAINT entity_coverage_entity_id_fkey
            FOREIGN KEY (entity_id) REFERENCES public.sc_public_entities(id)
            ON DELETE CASCADE;
    END IF;
END $$;

-- Indexes for fast gap detection
CREATE INDEX IF NOT EXISTS idx_cov_covered ON public.entity_coverage USING btree (is_covered, within_200km);
CREATE INDEX IF NOT EXISTS idx_cov_last_seen ON public.entity_coverage USING btree (last_seen_at);
CREATE INDEX IF NOT EXISTS idx_cov_source ON public.entity_coverage USING btree (source, is_covered);

-- Popula registros iniciais para entidades ativas (se vazia)
INSERT INTO public.entity_coverage (entity_id, source, is_covered, within_200km)
SELECT e.id, s.source, FALSE, COALESCE(e.raio_200km, FALSE)
FROM public.sc_public_entities e
CROSS JOIN (VALUES ('pncp'), ('dom_sc'), ('pcp'), ('compras_gov')) AS s(source)
WHERE e.is_active = TRUE
ON CONFLICT (entity_id, source) DO NOTHING;

-- ============================================================
-- 1a. Trigger functions and triggers
-- Criados condicionalmente: so vinculam a pncp_raw_bids se a
-- coluna matched_entity_id existir. Caso contrario, as funcoes
-- sao criadas mas os triggers nao — evitando runtime error
-- em INSERT INTO pncp_raw_bids.
-- ============================================================

-- Trigger function: update entity_coverage on bid insert
CREATE OR REPLACE FUNCTION public.update_entity_coverage()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.matched_entity_id IS NOT NULL THEN
        INSERT INTO public.entity_coverage (entity_id, source, last_seen_at, total_bids, is_covered, within_200km)
        VALUES (
            NEW.matched_entity_id,
            NEW.source,
            NEW.data_publicacao,
            1,
            COALESCE(NEW.data_publicacao >= CURRENT_DATE - 90, FALSE),
            COALESCE((SELECT raio_200km FROM public.sc_public_entities WHERE id = NEW.matched_entity_id), FALSE)
        )
        ON CONFLICT (entity_id, source) DO UPDATE
        SET
            last_seen_at = GREATEST(COALESCE(public.entity_coverage.last_seen_at, '1970-01-01'::date), COALESCE(NEW.data_publicacao, '1970-01-01'::date)),
            total_bids = public.entity_coverage.total_bids + 1,
            is_covered = GREATEST(COALESCE(public.entity_coverage.last_seen_at, '1970-01-01'::date), COALESCE(NEW.data_publicacao, '1970-01-01'::date)) >= CURRENT_DATE - 90;
    END IF;
    RETURN NEW;
END;
$$;

-- Trigger function: update when matched_entity_id is set after initial insert
CREATE OR REPLACE FUNCTION public.update_entity_coverage_on_update()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.matched_entity_id IS NOT NULL AND (OLD.matched_entity_id IS NULL OR OLD.matched_entity_id <> NEW.matched_entity_id) THEN
        INSERT INTO public.entity_coverage (entity_id, source, last_seen_at, total_bids, is_covered, within_200km)
        VALUES (
            NEW.matched_entity_id,
            NEW.source,
            NEW.data_publicacao,
            1,
            COALESCE(NEW.data_publicacao >= CURRENT_DATE - 90, FALSE),
            COALESCE((SELECT raio_200km FROM public.sc_public_entities WHERE id = NEW.matched_entity_id), FALSE)
        )
        ON CONFLICT (entity_id, source) DO UPDATE
        SET
            last_seen_at = GREATEST(COALESCE(public.entity_coverage.last_seen_at, '1970-01-01'::date), COALESCE(NEW.data_publicacao, '1970-01-01'::date)),
            total_bids = public.entity_coverage.total_bids + 1,
            is_covered = GREATEST(COALESCE(public.entity_coverage.last_seen_at, '1970-01-01'::date), COALESCE(NEW.data_publicacao, '1970-01-01'::date)) >= CURRENT_DATE - 90;
    END IF;
    RETURN NEW;
END;
$$;

-- Cria triggers apenas se matched_entity_id existir em pncp_raw_bids
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'pncp_raw_bids'
          AND column_name = 'matched_entity_id'
    ) THEN
        DROP TRIGGER IF EXISTS trg_bids_coverage ON public.pncp_raw_bids;
        CREATE TRIGGER trg_bids_coverage
            AFTER INSERT ON public.pncp_raw_bids
            FOR EACH ROW EXECUTE FUNCTION public.update_entity_coverage();

        DROP TRIGGER IF EXISTS trg_bids_coverage_update ON public.pncp_raw_bids;
        CREATE TRIGGER trg_bids_coverage_update
            AFTER UPDATE ON public.pncp_raw_bids
            FOR EACH ROW EXECUTE FUNCTION public.update_entity_coverage_on_update();
    END IF;
END $$;

-- Comments
COMMENT ON TABLE public.entity_coverage IS 'Cobertura de licitacoes por ente publico e fonte — Story TD-2.4';
COMMENT ON COLUMN public.entity_coverage.entity_id IS 'FK → sc_public_entities.id';
COMMENT ON COLUMN public.entity_coverage.source IS 'Fonte de dados: pncp|dom_sc|pcp|compras_gov';
COMMENT ON COLUMN public.entity_coverage.last_seen_at IS 'Ultima vez que este ente foi visto nesta fonte';
COMMENT ON COLUMN public.entity_coverage.total_bids IS 'Total de licitacoes coletadas deste ente';
COMMENT ON COLUMN public.entity_coverage.is_covered IS 'Tem publicacoes nos ultimos 90 dias?';
COMMENT ON COLUMN public.entity_coverage.within_200km IS 'Desnormalizado de sc_public_entities.raio_200km';

-- ============================================================
-- 2. v_coverage_gaps_by_municipio view
-- Fonte: supabase/migrations/003-v2 + db/migrations/012
-- ============================================================
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
        )) / NULLIF(COUNT(*), 0),
        1
    ) AS pct_gap,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE EXISTS (
            SELECT 1 FROM public.entity_coverage ec
            WHERE ec.entity_id = e.id AND ec.is_covered = TRUE
        )) / NULLIF(COUNT(*), 0),
        1
    ) AS pct_coberto
FROM public.sc_public_entities e
WHERE e.is_active = TRUE
GROUP BY e.municipio
ORDER BY entes_descobertos DESC, pct_gap DESC;

COMMENT ON VIEW public.v_coverage_gaps_by_municipio IS
    'Agregacao de gaps de cobertura por municipio — Story TD-2.4';

-- ============================================================
-- 3. ingestion_runs — add source column + reset stuck runs
-- ============================================================

-- 3a. Add source column (se ausente)
ALTER TABLE public.ingestion_runs ADD COLUMN IF NOT EXISTS source TEXT;

-- 3a2. Add completed_at and metadata columns (B2G-FIX-04: schema v2 drift)
ALTER TABLE public.ingestion_runs ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;
ALTER TABLE public.ingestion_runs ADD COLUMN IF NOT EXISTS metadata JSONB;

-- 3b. Reset stuck ingestion runs (IDs 3, 4, 5)
-- Adaptado para schema v2: usa completed_at (nao finished_at)
-- e metadata jsonb (nao error_message text)
UPDATE public.ingestion_runs
SET
    status = 'failed',
    completed_at = NOW(),
    metadata = jsonb_build_object(
        'reset_reason', 'Stuck run reset by Story TD-2.4 migration 020',
        'reset_timestamp', NOW() AT TIME ZONE 'UTC',
        'original_started_at', started_at AT TIME ZONE 'UTC',
        'stuck_duration_days', ROUND(EXTRACT(EPOCH FROM (NOW() - started_at)) / 86400, 1)
    )
WHERE id IN (3, 4, 5)
  AND status = 'running';

-- ============================================================
-- 4. ingestion_checkpoints — add columns for sync API
-- O schema v2 existente tem colunas: id, source, uf,
-- modalidade_id, last_date, last_page, records_fetched, status,
-- error_message, started_at, completed_at, crawl_batch_id.
-- Precisamos adicionar scope_key, last_id, updated_at para a
-- sync API (scripts/crawl/checkpoint.py) que usa PK (source, scope_key).
-- ============================================================

ALTER TABLE public.ingestion_checkpoints ADD COLUMN IF NOT EXISTS scope_key TEXT;
ALTER TABLE public.ingestion_checkpoints ADD COLUMN IF NOT EXISTS last_id TEXT;
ALTER TABLE public.ingestion_checkpoints ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;
ALTER TABLE public.ingestion_checkpoints ADD COLUMN IF NOT EXISTS uf TEXT;
ALTER TABLE public.ingestion_checkpoints ADD COLUMN IF NOT EXISTS modalidade_id INT;
ALTER TABLE public.ingestion_checkpoints ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;

-- Popula scope_key para registros existentes (converte uf+modalidade_id)
UPDATE public.ingestion_checkpoints
SET scope_key = COALESCE(uf || '_' || modalidade_id::TEXT, 'default')
WHERE scope_key IS NULL;

-- Seta default para scope_key
ALTER TABLE public.ingestion_checkpoints ALTER COLUMN scope_key SET DEFAULT 'default';

-- Adiciona constraint UNIQUE (source, scope_key) para ON CONFLICT na sync API
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_ingestion_checkpoints_source_scope'
    ) THEN
        ALTER TABLE public.ingestion_checkpoints
            ADD CONSTRAINT uq_ingestion_checkpoints_source_scope
            UNIQUE (source, scope_key);
    END IF;
END $$;

-- Seta default para updated_at
ALTER TABLE public.ingestion_checkpoints ALTER COLUMN updated_at SET DEFAULT NOW();

-- Popula updated_at para registros existentes
UPDATE public.ingestion_checkpoints
SET updated_at = COALESCE(completed_at, NOW())
WHERE updated_at IS NULL;

-- Comments
COMMENT ON COLUMN public.ingestion_checkpoints.scope_key IS
    'Sync API scope identifier (default ou uf_modalidade_id) — adicionado por Story TD-2.4';
COMMENT ON COLUMN public.ingestion_checkpoints.last_id IS
    'Ultimo record ID (source-specific) — adicionado por Story TD-2.4';
COMMENT ON COLUMN public.ingestion_checkpoints.updated_at IS
    'Timestamp da ultima atualizacao — adicionado por Story TD-2.4';

-- ============================================================
-- 5. v_coverage_summary — recreate if missing
-- Fonte: supabase/migrations/003-v2
-- ============================================================
CREATE OR REPLACE VIEW public.v_coverage_summary AS
SELECT
    ec.source,
    ec.within_200km,
    ec.is_covered,
    COUNT(*) AS entity_count,
    ROUND(
        (COUNT(*)::NUMERIC * 100.0) / SUM(COUNT(*)) OVER (PARTITION BY ec.within_200km), 1
    ) AS pct
FROM public.entity_coverage ec
WHERE EXISTS (
    SELECT 1 FROM public.sc_public_entities e
    WHERE e.id = ec.entity_id AND e.is_active = TRUE
)
GROUP BY ec.source, ec.within_200km, ec.is_covered
ORDER BY ec.source, ec.within_200km, ec.is_covered;

COMMENT ON VIEW public.v_coverage_summary IS
    'Sumario de cobertura por source e raio_200km — Story TD-2.4';

-- ============================================================
-- 6. Register in tracking (se tabela _migrations existir)
-- ============================================================
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = '_migrations') THEN
        INSERT INTO public._migrations (version, name, applied_at, checksum, rollback_sql)
        VALUES (
            '020',
            'td-2.4_sync_local_schema',
            NOW(),
            'sha256=manual-td-2-4',
            'DROP TABLE IF EXISTS public.entity_coverage CASCADE; DROP VIEW IF EXISTS public.v_coverage_gaps_by_municipio CASCADE; DROP VIEW IF EXISTS public.v_coverage_summary CASCADE; ALTER TABLE public.ingestion_runs DROP COLUMN IF EXISTS source; ALTER TABLE public.ingestion_checkpoints DROP COLUMN IF EXISTS scope_key; ALTER TABLE public.ingestion_checkpoints DROP COLUMN IF EXISTS last_id; ALTER TABLE public.ingestion_checkpoints DROP COLUMN IF EXISTS updated_at;'
        )
        ON CONFLICT (version) DO NOTHING;
    END IF;
END $$;

COMMIT;
