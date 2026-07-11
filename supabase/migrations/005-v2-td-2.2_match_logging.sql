-- ============================================================================
-- 005-v2-td-2.2_match_logging.sql — Match Logging (Adaptada de v1 010)
-- ============================================================================
-- Story TD-2.2: Aplicar Migrations 009-012 Adaptadas
-- Debito: TD-DB-02b (LOW) — match_logging ausente na cadeia de migrations
--
-- Adaptada da migration v1 010 (match_logging.sql) para o schema v2 baseline.
-- As colunas match_method, match_score, match_confidence NAO existem no
-- baseline 001-v2. Esta migration e a unica das 4 que realmente adiciona
-- novos objetos ao schema.
--
-- Uso no monitor.py:
--   _match_entities_cascade() grava estas colunas apos cada tentativa de match
--
-- Principios:
--   - Reexecutavel: ADD COLUMN IF NOT EXISTS / CREATE INDEX IF NOT EXISTS
--   - Schema qualificado (public.)
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. Add match-logging columns to pncp_raw_bids
-- ============================================================================

-- 1.1 Estrategia de matching que produziu o match
ALTER TABLE public.pncp_raw_bids
    ADD COLUMN IF NOT EXISTS match_method TEXT;

-- 1.2 Score do match (0.000 = no match, 1.000 = exact)
ALTER TABLE public.pncp_raw_bids
    ADD COLUMN IF NOT EXISTS match_score DECIMAL(4,3);

-- 1.3 Confianca do match (high, medium, low)
ALTER TABLE public.pncp_raw_bids
    ADD COLUMN IF NOT EXISTS match_confidence TEXT;

-- ============================================================================
-- 2. Indexes for match quality analysis
-- ============================================================================

-- Index para analise de qualidade de matching / debugging de unmatched bids
CREATE INDEX IF NOT EXISTS idx_bids_match_method
    ON public.pncp_raw_bids (match_method)
    WHERE match_method IS NOT NULL;

-- Index composto para analise de cobertura: quais metodos estao produzindo matches
CREATE INDEX IF NOT EXISTS idx_bids_match_coverage
    ON public.pncp_raw_bids (match_method, matched_entity_id)
    WHERE matched_entity_id IS NOT NULL;

-- ============================================================================
-- 3. Comments
-- ============================================================================
COMMENT ON COLUMN public.pncp_raw_bids.match_method IS
    'Estrategia de matching: cnpj | name_normalized | fuzzy | unmatched';

COMMENT ON COLUMN public.pncp_raw_bids.match_score IS
    'Score do match (0.000-1.000). 1.000 = exact match.';

COMMENT ON COLUMN public.pncp_raw_bids.match_confidence IS
    'Confianca: high (>=0.95) | medium (>=threshold) | low (<threshold)';

-- ============================================================================
-- 4. Register in _migrations tracking table
-- ============================================================================
INSERT INTO public._migrations (version, name, applied_at, checksum, rollback_sql)
VALUES (
    '005-v2',
    'td-2.2_match_logging',
    NOW(),
    'sha256=0d4da4537dda19b04f8789696f90bbb46aeb6c259ca9067cb7a03d170154161d',
    'ALTER TABLE public.pncp_raw_bids DROP COLUMN IF EXISTS match_method; ALTER TABLE public.pncp_raw_bids DROP COLUMN IF EXISTS match_score; ALTER TABLE public.pncp_raw_bids DROP COLUMN IF EXISTS match_confidence;'
)
ON CONFLICT (version) DO NOTHING;

COMMIT;
