-- ============================================================================
-- _migrations.sql — Migration Tracking Table
-- ============================================================================
-- Story TD-2.1: Reconstruir Migrations do Zero
-- Debito: TD-DB-17 (LOW) — Sem tabela de tracking de migrations
--
-- Esta tabela e o coracao do novo sistema de migrations v2. Toda migration
-- aplicada DEVE registrar-se aqui com version, checksum e rollback_sql.
--
-- Uso:
--   1. Aplicar este DDL primeiro (cria a tabela de tracking)
--   2. Aplicar 001-v2_initial_schema.sql (cria todo o schema baseline)
--   3. Para migrations futuras: aplicar SQL + INSERT em _migrations
--
-- Regeneracao:
--   SELECT * FROM _migrations ORDER BY version;
--
-- Rollback:
--   -- Listar todas as migrations aplicadas
--   SELECT version, name, applied_at FROM _migrations ORDER BY applied_at DESC;
--
--   -- Reverter ate uma versao especifica (cuidado com dependencias)
--   -- Executar rollback_sql de cada migration em ordem reversa
-- ============================================================================

-- Create tracking table
CREATE TABLE IF NOT EXISTS public._migrations (
    version      TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    applied_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    checksum     TEXT,                       -- SHA256 do conteudo SQL (opcional, verificado pelo apply script)
    rollback_sql TEXT                        -- SQL para reverter a migration (opcional, pode ser NULL)
);

COMMENT ON TABLE public._migrations IS 'Tracking de migrations do schema — TD-DB-17, Story TD-2.1';

COMMENT ON COLUMN public._migrations.version IS 'Numero da migration (ex: 001-v2, 002-v2)';
COMMENT ON COLUMN public._migrations.name IS 'Nome descritivo da migration';
COMMENT ON COLUMN public._migrations.applied_at IS 'Timestamp de quando foi aplicada';
COMMENT ON COLUMN public._migrations.checksum IS 'SHA256 do conteudo SQL para detectar modificacoes';
COMMENT ON COLUMN public._migrations.rollback_sql IS 'SQL para reverter a migration, se aplicavel';

-- Index para consultas por ordem de aplicacao
CREATE INDEX IF NOT EXISTS idx_migrations_applied_at
    ON public._migrations (applied_at DESC);

-- ============================================================================
-- Register this migration
-- ============================================================================
INSERT INTO public._migrations (version, name, applied_at, checksum, rollback_sql)
VALUES (
    '_migrations',
    'migration_tracking_table',
    NOW(),
    NULL,
    'DROP TABLE IF EXISTS public._migrations CASCADE;'
)
ON CONFLICT (version) DO UPDATE
    SET applied_at = NOW()
    WHERE _migrations.version = '_migrations';
