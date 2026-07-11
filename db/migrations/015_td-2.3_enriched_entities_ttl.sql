-- Migration 015: TTL enforcement for enriched_entities
-- Story TD-2.3: Normalizacao e Constraints
-- Deficit TD-DB-03 (MEDIUM): enriched_entities sem TTL enforcement
--   13.8K registros sem politica de expiracao, risco de dados obsoletos acumulados
--
-- Estrategia:
--   1. Funcao de limpeza que remove registros com enriched_at > 90 dias
--   2. Script `scripts/cleanup-expired-entities.sql` para execucao periodica
--   3. Trigger BEFORE INSERT/UPDATE para validar TTL (opcional — ver abaixo)
--
-- NOTA: Nao implementamos trigger blocking porque a aplicacao precisa conseguir
--       inserir dados mesmo que estejam "expirados" (o cleanup e async).
--       A limpeza e feita por job periodico (cron) rodando o script.

-- ============================================================
-- 1. Funcao de limpeza TTL
-- ============================================================
--
-- Remove registros de enriched_entities que nao foram atualizados
-- nos ultimos 90 dias (configuravel via parametro p_ttl_days).
--
-- Uso:
--   SELECT ttl_cleanup_enriched_entities();          -- default 90 dias
--   SELECT ttl_cleanup_enriched_entities(30);         -- 30 dias
--   SELECT ttl_cleanup_enriched_entities(180);        -- 6 meses
--
-- Retorna: numero de registros removidos (INT)

CREATE OR REPLACE FUNCTION ttl_cleanup_enriched_entities(
    p_ttl_days INT DEFAULT 90
)
RETURNS INT
LANGUAGE plpgsql
VOLATILE
AS $$
DECLARE
    v_deleted INT;
BEGIN
    -- Validacao do parametro (COALESCE para tratar NULL)
    IF COALESCE(p_ttl_days, 0) < 1 THEN
        RAISE EXCEPTION 'p_ttl_days must be >= 1, got %', p_ttl_days;
    END IF;

    DELETE FROM enriched_entities
    WHERE enriched_at < CURRENT_DATE - p_ttl_days;

    GET DIAGNOSTICS v_deleted = ROW_COUNT;

    -- Log da operacao (via RAISE NOTICE para visibilidade em logs do cron)
    RAISE NOTICE 'TTL cleanup: removed % expired records from enriched_entities (TTL=% days)',
        v_deleted, p_ttl_days;

    RETURN v_deleted;
END;
$$;

COMMENT ON FUNCTION ttl_cleanup_enriched_entities IS
    'TD-DB-03: Remove registros expirados de enriched_entities baseado em enriched_at + TTL configurado (default 90 dias)';

-- ============================================================
-- 2. Refresh do index existente (garantir que cobre TTL)
-- ============================================================
--
-- O index idx_ee_enriched_at ja existe (criado na migration 003)
-- e cobre a coluna enriched_at usada na query de limpeza.
-- Nao e necessario recria-lo.
--
-- Verificacao:
--   SELECT schemaname, tablename, indexname, indexdef
--   FROM pg_indexes
--   WHERE tablename = 'enriched_entities';
--
-- Deve mostrar: idx_ee_enriched_at ON enriched_entities (enriched_at)

-- ============================================================
-- 3. Adicionar CHECK constraint enriched_at nao futura
-- ============================================================
--
-- Garantir que enriched_at nao esteja no futuro (dado inconsistente)

ALTER TABLE enriched_entities
    ADD CONSTRAINT chk_ee_enriched_at_not_future
    CHECK (enriched_at <= NOW() + INTERVAL '1 hour')
    NOT VALID;  -- NOT VALID para nao bloquear em producao (validacao gradual)

COMMENT ON CONSTRAINT chk_ee_enriched_at_not_future ON enriched_entities IS
    'TD-DB-03: enriched_at nao pode estar no futuro (tolerancia de 1h para fuso)';

-- ============================================================
-- 4. Adicionar NOT NULL onde apropriado
-- ============================================================

ALTER TABLE enriched_entities
    ADD CONSTRAINT chk_ee_cnpj_not_empty
    CHECK (cnpj <> '')
    NOT VALID;

ALTER TABLE enriched_entities
    ADD CONSTRAINT chk_ee_enriched_source_not_empty
    CHECK (enriched_source <> '')
    NOT VALID;

COMMENT ON CONSTRAINT chk_ee_cnpj_not_empty ON enriched_entities IS
    'TD-DB-03: CNPJ nao pode ser string vazia';
COMMENT ON CONSTRAINT chk_ee_enriched_source_not_empty ON enriched_entities IS
    'TD-DB-03: enriched_source nao pode ser string vazia';
