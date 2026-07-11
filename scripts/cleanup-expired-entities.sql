-- cleanup-expired-entities.sql
-- Script de cleanup periodico para enriched_entities TTL
-- Uso: psql $DATABASE_URL -f scripts/cleanup-expired-entities.sql
-- Ou via cron: 0 3 * * 0 psql $DATABASE_URL -f /path/to/cleanup-expired-entities.sql
--
-- Story TD-2.3 (TD-DB-03): Remove registros expirados de enriched_entities
-- com mais de 90 dias desde a ultima atualizacao.
--
-- Configuracao:
--   TTL_DAYS: 90 (default) — pode ser alterado na chamada da funcao
--
-- Dependencias:
--   - Function ttl_cleanup_enriched_entities() da migration 015
--
-- Log:
--   O resultado e logado via RAISE NOTICE e retornado como resultado da query.

-- ============================================================
-- Execucao (modo verbose)
-- ============================================================

SELECT
    'TTL_CLEANUP' AS operation,
    NOW() AS executed_at,
    ttl_cleanup_enriched_entities(90) AS records_deleted;

-- ============================================================
-- Verificacao pos-execucao
-- ============================================================

-- Registros ainda expirados (se > 0, TTL pode precisar ser ajustado)
SELECT
    'REMAINING_EXPIRED' AS check_type,
    COUNT(*) AS record_count,
    MIN(enriched_at) AS oldest_enriched_at,
    MAX(enriched_at) AS newest_enriched_at
FROM enriched_entities
WHERE enriched_at < CURRENT_DATE - 90;

-- Estatisticas da tabela
SELECT
    'TABLE_STATS' AS stat_type,
    COUNT(*) AS total_records,
    COUNT(*) FILTER (WHERE enriched_at < CURRENT_DATE - 30) AS older_than_30d,
    COUNT(*) FILTER (WHERE enriched_at < CURRENT_DATE - 90) AS older_than_90d,
    MIN(enriched_at) AS oldest,
    MAX(enriched_at) AS newest
FROM enriched_entities;
