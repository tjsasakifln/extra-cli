-- Migration 016: GIN trigram index on pncp_raw_bids.objeto_compra
-- Story TD-2.3: Normalizacao e Constraints
-- Deficit TD-DB-06 (MEDIUM): GIST trigram index em pncp_raw_bids.objeto_compra
--   superdimensionado (294 MB para ~200K registros ativos), com relacao
--   index/dados de 1.1x.
--
-- Analise GIST vs GIN:
--
-- | Caracteristica        | GIST                          | GIN                            |
-- |-----------------------|-------------------------------|--------------------------------|
-- | Tamanho do index      | Maior (294 MB reportado)      | Menor (~40-60% do GIST)        |
-- | Velocidade INSERT     | Mais rapido                   | Mais lento (compressao)        |
-- | Velocidade SELECT     | Mais lento (mais IO)          | Mais rapido (bitmap scan)      |
-- | word_similarity()     | Suportado nativamente         | NAO suportado diretamente      |
-- | ILIKE / LIKE          | Suportado (gist_trgm_ops)     | Suportado (gin_trgm_ops)       |
-- | %term% wildcard       | Suportado                     | Suportado (mais rapido)        |
--
-- Decisao: GIN
--   - Codigo existente usa ILIKE e tsquery, NAO word_similarity()
--     (confirmado por grep em .sql e .py — zero ocorrencias de word_similarity)
--   - GIN e 40-60% menor que GIST para trigram search
--   - GIN e significativamente mais rapido para SELECT com ILIKE
--   - Caso word_similarity seja necessario no futuro, manter GIST como fallback
--
-- Riscos mitigados:
--   - NOTA: Se existir GIST index em producao (criado manualmente), ele
--     permanecera ate remocao explicita. Este migration ADD o GIN sem remover
--     o GIST. A remocao do GIST deve ser feita APOS validacao de que o GIN
--     atende todos os casos de uso.
--   - Comando para verificar GIST existente:
--       SELECT indexname, indexdef FROM pg_indexes
--       WHERE tablename = 'pncp_raw_bids' AND indexdef LIKE '%objeto_compra%';

-- ============================================================
-- Garantir extensao pg_trgm (necessaria para gin_trgm_ops)
-- ============================================================
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================
-- 1. GIN index com gin_trgm_ops em objeto_compra
-- ============================================================
--
-- Partial index: WHERE is_active = TRUE porque:
--   1. Soft-deleted records (is_active = FALSE) nunca sao consultados
--   2. Reduz tamanho do index (~15-20% menos registros)
--   3. Melhor selectivity ratio no planner
--
-- NOTA sobre CONCURRENTLY:
--   Usamos CREATE INDEX CONCURRENTLY para nao bloquear escritas em producao.
--   Importante: CONCURRENTLY exige que a transacao seja a unica operacao
--   (nao pode ser combinado com outros DDL na mesma transacao).
--   Como esta migration contem apenas este comando DDL, e seguro.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bids_objeto_compra_gin
    ON pncp_raw_bids
    USING GIN (objeto_compra gin_trgm_ops)
    WHERE is_active = TRUE;

COMMENT ON INDEX idx_bids_objeto_compra_gin IS
    'TD-DB-06: GIN trigram index on objeto_compra for fast ILIKE search (Story TD-2.3)';

-- ============================================================
-- 2. Remocao do GIST antigo (se existir em producao)
-- ============================================================
--
-- Descomente APOS validar que GIN atende todos os casos de uso:
--
--   DROP INDEX IF EXISTS idx_bids_objeto_compra_gist;
--
-- Para verificar se o GIST existe:
--   SELECT indexname FROM pg_indexes
--   WHERE tablename = 'pncp_raw_bids'
--     AND indexname LIKE '%objeto_compra%'
--     AND indexdef ILIKE '%gist%';

-- ============================================================
-- 3. Verificacao do index (query de diagnostico)
-- ============================================================
--
-- Para verificar se o index esta sendo usado:
--
--   EXPLAIN ANALYZE
--   SELECT pncp_id, objeto_compra
--   FROM pncp_raw_bids
--   WHERE is_active = TRUE
--     AND objeto_compra ILIKE '%obra%'
--   LIMIT 50;
--
-- Deve mostrar: "Index Scan using idx_bids_objeto_compra_gin"
-- (NAO "Seq Scan on pncp_raw_bids")
