-- Migration 017: Reforcar index em matched_entity_id
-- Story TD-2.3: Normalizacao e Constraints
-- Deficit TD-DB-07 (MEDIUM): Tabela pncp_raw_bids sem index em matched_entity_id,
--   forcando nested loop scan em coverage queries com LEFT JOIN.
--
-- Contexto:
--   O index idx_bids_matched_entity foi definido na migration 001, mas o schema
--   real de producao pode nao te-lo (schema diverge das migrations — vide TD-2.1).
--   Esta migration garante que o index exista em producao usando IF NOT EXISTS.
--
-- Index partial:
--   WHERE matched_entity_id IS NOT NULL porque:
--   1. A maioria das coverage queries filtra por entidades com match
--   2. Registros sem match (~40% dos bids) sao irrelevantes para coverage
--   3. Reduz tamanho do index significativamente
--   4. Melhor selectivity para o planner

-- ============================================================
-- 1. Index em matched_entity_id (partial)
-- ============================================================
--
-- Usamos CONCURRENTLY para evitar lock em producao.
-- Mesmo que o index ja exista (criado na migration 001 e aplicado),
-- IF NOT EXISTS torna esta operacao segura para re-execucao.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bids_matched_entity
    ON pncp_raw_bids (matched_entity_id)
    WHERE matched_entity_id IS NOT NULL;

COMMENT ON INDEX idx_bids_matched_entity IS
    'TD-DB-07: Partial index on matched_entity_id for coverage JOIN performance (Story TD-2.3)';

-- ============================================================
-- 2. Index composto para match_logging (reforco)
-- ============================================================
--
-- O migration 010 define idx_match_logging_lookup para (match_method, matched_entity_id).
-- Reforcar com IF NOT EXISTS para garantir consistencia em producao.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_match_logging_lookup
    ON pncp_raw_bids (match_method, matched_entity_id)
    WHERE matched_entity_id IS NOT NULL;

COMMENT ON INDEX idx_match_logging_lookup IS
    'TD-DB-07: Composite index for match_logging lookup (match_method + matched_entity_id)';

-- ============================================================
-- 3. Verificacao (query de diagnostico)
-- ============================================================
--
-- Para confirmar que o index e usado em coverage queries:
--
--   EXPLAIN ANALYZE
--   SELECT ec.entity_id, ec.source, ec.is_covered, b.pncp_id
--   FROM entity_coverage ec
--   LEFT JOIN pncp_raw_bids b ON b.matched_entity_id = ec.entity_id
--   WHERE ec.is_covered = FALSE
--   LIMIT 100;
--
-- Deve mostrar: "Index Scan using idx_bids_matched_entity"
-- ao inves de "Nested Loop" ou "Seq Scan on pncp_raw_bids"
