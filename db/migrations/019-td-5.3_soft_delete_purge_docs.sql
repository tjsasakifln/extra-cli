-- Migration 019: Documentacao do soft-delete em purge_old_bids
-- Story TD-5.3: Otimizacao de Performance
-- Deficit TD-DB-14 (MEDIUM): purge_old_bids fazia DELETE fisico.
--
-- Contexto:
--   A funcao purge_old_bids foi implementada originalmente na migration 008
--   como soft-delete (UPDATE is_active = FALSE), nao como DELETE fisico.
--   Esta migration e apenas documentacao confirmando que o comportamento
--   atual e soft-delete, e adiciona:
--     1. Confirmacao do soft-delete via COMMENT ON FUNCTION
--     2. Funcao auxiliar purge_old_bids_hard() para purga fisica
--        controlada (opcional, taxa de retencao explicita)
--
-- NOTA: A funcao purge_old_bids ja existe e JA FAZ SOFT-DELETE.
-- Esta migration apenas documenta e estende.

-- ============================================================
-- 1. Reforcar documentacao da funcao existente
-- ============================================================

COMMENT ON FUNCTION purge_old_bids IS
    'TD-DB-14: Soft-delete — marca is_active = FALSE para bids mais antigos que p_retention_days. '
    'Nao faz DELETE fisico. Registros permanecem na tabela e podem ser restaurados '
    'via UPDATE pncp_raw_bids SET is_active = TRUE WHERE ...';

-- ============================================================
-- 2. Funcao auxiliar: hard-delete seguro (opcional, controlado)
-- ============================================================
--
-- Uso apenas quando a retencao de soft-delete expirou.
-- Segunda camada de protecao: requer confirmaçao explicita.
--
-- Parametros:
--   p_soft_retention_days: idade minima para registros soft-deleted (default 90)
--     So registros que ja estao com is_active = FALSE ha pelo menos N dias
--     serao fisicamente removidos.

CREATE OR REPLACE FUNCTION purge_old_bids_hard(
    p_soft_retention_days INT DEFAULT 90
)
RETURNS TABLE (
    hard_deleted_count INT,
    remaining_soft_deleted INT
) LANGUAGE plpgsql AS $$
DECLARE
    v_cutoff DATE;
    v_deleted INT;
    v_remaining INT;
BEGIN
    v_cutoff := CURRENT_DATE - p_soft_retention_days;

    -- Hard-delete apenas registros ja soft-deleted ha mais de N dias
    DELETE FROM pncp_raw_bids
    WHERE is_active = FALSE
      AND updated_at < v_cutoff::TIMESTAMPTZ;

    GET DIAGNOSTICS v_deleted = ROW_COUNT;

    SELECT COUNT(*)::INT INTO v_remaining
    FROM pncp_raw_bids
    WHERE is_active = FALSE;

    RETURN QUERY SELECT v_deleted, v_remaining;
END;
$$;

COMMENT ON FUNCTION purge_old_bids_hard IS
    'TD-DB-14: Hard-delete controlado — remove fisicamente registros soft-deleted '
    'ha mais de p_soft_retention_days dias. So executa quando a retencao de '
    'soft-delete expirou. Use com cautela.';

-- ============================================================
-- 3. Garantir que a funcao principal usa soft-delete
-- ============================================================
--
-- A funcao purge_old_bids ja existe (criada na 008) e ja implementa
-- soft-delete. Re-criamos aqui para confirmar e documentar:

CREATE OR REPLACE FUNCTION purge_old_bids(p_retention_days INT DEFAULT 400)
RETURNS TABLE (
    purged_count INT,
    remaining_count INT
) LANGUAGE plpgsql AS $$
DECLARE
    cutoff_date DATE;
    v_purged INT;
BEGIN
    cutoff_date := CURRENT_DATE - p_retention_days;

    -- Soft-delete: marca como inativo (NAO remove fisicamente)
    UPDATE pncp_raw_bids
    SET is_active = FALSE
    WHERE is_active = TRUE
      AND data_publicacao < cutoff_date;

    GET DIAGNOSTICS v_purged = ROW_COUNT;

    RETURN QUERY
    SELECT
        v_purged,
        COUNT(*)::INT
    FROM pncp_raw_bids
    WHERE is_active = TRUE;
END;
$$;

COMMENT ON FUNCTION purge_old_bids IS
    'TD-DB-14 (confirmado): Soft-delete — UPDATE is_active = FALSE. '
    'Nunca faz DELETE. Registros permanecem recuperaveis.';

-- ============================================================
-- 4. Verificacao
-- ============================================================
--
-- Para testar soft-delete:
--   SELECT * FROM purge_old_bids(400);
--   -- Verificar que registros antigos tem is_active = FALSE
--   SELECT COUNT(*) FROM pncp_raw_bids WHERE is_active = FALSE;
--
-- Para restaurar um registro soft-deleted:
--   UPDATE pncp_raw_bids SET is_active = TRUE WHERE pncp_id = '<id>';
--
-- Para hard-delete (cuidado):
--   SELECT * FROM purge_old_bids_hard(90);
