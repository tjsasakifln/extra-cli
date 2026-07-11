-- Migration 013: GIN trigram index on pncp_supplier_contracts.objeto_contrato
-- Story TD-1.1: Otimizacao de Queries
-- Deficit TD-DB-08 (HIGH): Tabela pncp_supplier_contracts (~3.69M registros)
-- nao tem GIN index em objeto_contrato, forcando full table scan em todas
-- as buscas textuais por objeto de contrato.
--
-- Uso no datalake_helper.py:
--   supplier_contracts() faz ILIKE chain em keywords → objeto_contrato
--   (linhas ~493-500 em scripts/datalake_helper.py)
--
-- Uso no backend/local_datalake.py:
--   get_supplier_contracts(), get_contracts_by_orgao() filtram por is_active
--
-- Index parcial (WHERE is_active = true) porque registros soft-deleted
-- nunca sao consultados. GIN com gin_trgm_ops para suportar ILIKE e
-- similaridade trigram.
--
-- NOTA: O migration 002 original criava idx_psc_objeto_trgm na tabela,
-- mas o schema atual (com is_active, numero_controle_pncp, etc.) foi
-- evoluido diretamente via DDL e perdeu esse index. A SCHEMA.md lista
-- 36 indexes em pncp_supplier_contracts — nenhum GIN em objeto_contrato.

-- ============================================================
-- Garantir extensao pg_trgm (necessaria para gin_trgm_ops)
-- ============================================================
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================
-- 1. GIN index com gin_trgm_ops em objeto_contrato
-- ============================================================
--
-- CREATE INDEX CONCURRENTLY permite que a tabela permaneca disponivel
-- para leitura/escrita durante a criacao do index (nao bloqueia escritas).
--
-- Partial index: WHERE is_active = TRUE porque:
--   1. soft-deleted records (is_active = FALSE) nunca sao consultados
--   2. Reduz tamanho do index em ~30% (menos registros para indexar)
--   3. Melhor selectivity ratio no planner

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_psc_objeto_contrato_gin
    ON pncp_supplier_contracts
    USING GIN (objeto_contrato gin_trgm_ops)
    WHERE is_active = TRUE;

COMMENT ON INDEX idx_psc_objeto_contrato_gin IS
    'TD-DB-08: GIN trigram index on objeto_contrato for fast textual search (Story TD-1.1)';

-- ============================================================
-- 2. Verificacao do index (query de diagnostico)
-- ============================================================
--
-- Para verificar se o index esta sendo usado:
--
--   EXPLAIN ANALYZE
--   SELECT * FROM pncp_supplier_contracts
--   WHERE is_active = TRUE
--     AND objeto_contrato ILIKE '%limpeza%'
--   LIMIT 100;
--
-- Deve mostrar: "Index Scan using idx_psc_objeto_contrato_gin"
-- (NÃO "Seq Scan on pncp_supplier_contracts")
