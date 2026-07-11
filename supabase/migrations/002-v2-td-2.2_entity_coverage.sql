-- ============================================================================
-- 002-v2-td-2.2_entity_coverage.sql — Entity Coverage (Adaptada de v1 009)
-- ============================================================================
-- Story TD-2.2: Aplicar Migrations 009-012 Adaptadas
-- Debito: TD-DB-02a (HIGH) — entity_coverage ausente na cadeia de migrations
--
-- Adaptada da migration v1 009 (indexes_and_coverage.sql) para o schema v2
-- baseline. A tabela entity_coverage ja existe no baseline (001-v2), mas esta
-- migration garante reexecutabilidade e registro em _migrations.
--
-- Principios:
--   - Reexecutavel: IF NOT EXISTS / OR REPLACE / DROP IF EXISTS
--   - Schema qualificado (public.) para consistencia
--   - Sem seed data (aplicacao gerencia)
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. Tabela entity_coverage
-- ============================================================================
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

-- ============================================================================
-- 2. Indexes
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_cov_covered ON public.entity_coverage USING btree (is_covered, within_200km);
CREATE INDEX IF NOT EXISTS idx_cov_last_seen ON public.entity_coverage USING btree (last_seen_at);
CREATE INDEX IF NOT EXISTS idx_cov_source ON public.entity_coverage USING btree (source, is_covered);

-- ============================================================================
-- 3. Trigger Functions
-- ============================================================================

-- 3.1 update_entity_coverage — AFTER INSERT on pncp_raw_bids
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

-- 3.2 update_entity_coverage_on_update — AFTER UPDATE on pncp_raw_bids
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

-- ============================================================================
-- 4. Triggers
-- ============================================================================

DROP TRIGGER IF EXISTS trg_bids_coverage ON public.pncp_raw_bids;
CREATE TRIGGER trg_bids_coverage
    AFTER INSERT ON public.pncp_raw_bids
    FOR EACH ROW EXECUTE FUNCTION public.update_entity_coverage();

DROP TRIGGER IF EXISTS trg_bids_coverage_update ON public.pncp_raw_bids;
CREATE TRIGGER trg_bids_coverage_update
    AFTER UPDATE ON public.pncp_raw_bids
    FOR EACH ROW EXECUTE FUNCTION public.update_entity_coverage_on_update();

-- ============================================================================
-- 5. Comments
-- ============================================================================
COMMENT ON TABLE public.entity_coverage IS 'Cobertura de licitacoes por ente publico e fonte — Story 001.5/001.7, adaptado de v1 009';
COMMENT ON COLUMN public.entity_coverage.entity_id IS 'FK → sc_public_entities.id';
COMMENT ON COLUMN public.entity_coverage.source IS 'Fonte de dados: pncp|dom_sc|pcp|compras_gov|sc_compras|tce_sc|transparencia';
COMMENT ON COLUMN public.entity_coverage.last_seen_at IS 'Ultima vez que este ente foi visto nesta fonte';
COMMENT ON COLUMN public.entity_coverage.total_bids IS 'Total de licitacoes coletadas deste ente';
COMMENT ON COLUMN public.entity_coverage.is_covered IS 'Tem publicacoes nos ultimos 90 dias?';
COMMENT ON COLUMN public.entity_coverage.within_200km IS 'Desnormalizado de sc_public_entities.raio_200km';

-- ============================================================================
-- 6. Register in _migrations tracking table
-- ============================================================================
INSERT INTO public._migrations (version, name, applied_at, checksum, rollback_sql)
VALUES (
    '002-v2',
    'td-2.2_entity_coverage',
    NOW(),
    'sha256=e83b7c1c111e064b85ef308438c8297e1a7d5b4984c94a3bdf46e0b34f213718',
    'DROP TABLE IF EXISTS public.entity_coverage CASCADE;'
)
ON CONFLICT (version) DO NOTHING;

COMMIT;
