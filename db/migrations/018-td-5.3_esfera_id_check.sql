-- Migration 018: CHECK constraint para esfera_id em pncp_raw_bids
-- Story TD-5.3: Otimizacao de Performance
-- Deficit TD-DB-09 (LOW): Coluna esfera_id sem CHECK constraint,
--   permitindo valores invalidos.
--
-- Contexto:
--   A coluna esfera_id e INT e armazena codigos numericos:
--     1 = Federal (F)
--     2 = Estadual (E)
--     3 = Municipal (M)
--     4 = Distrital (D)
--
--   O assessment original sugeria CHECK (esfera_id IN ('F','E','M','D')),
--   mas a coluna e INT. Adaptado para valores inteiros.
--
--   O RPC search_datalake usa p_esferas INT[], entao a constraint
--   com inteiros e consistente com o resto do sistema.

-- ============================================================
-- 1. Limpeza preventiva: garantir que nao ha dados invalidos
-- ============================================================
--
-- Caso existam registros com esfera_id fora de {1,2,3,4},
-- resetamos para NULL (desconhecido) para nao bloquear a constraint.

UPDATE pncp_raw_bids
SET esfera_id = NULL
WHERE esfera_id IS NOT NULL
  AND esfera_id NOT IN (1, 2, 3, 4);

-- ============================================================
-- 2. CHECK constraint
-- ============================================================

ALTER TABLE pncp_raw_bids
ADD CONSTRAINT chk_pncp_raw_bids_esfera_id
CHECK (esfera_id IS NULL OR esfera_id IN (1, 2, 3, 4));

COMMENT ON CONSTRAINT chk_pncp_raw_bids_esfera_id ON pncp_raw_bids IS
    'TD-DB-09: esfera_id deve ser 1=Federal, 2=Estadual, 3=Municipal, 4=Distrital, ou NULL';

-- ============================================================
-- 3. Verificacao
-- ============================================================
--
-- Para confirmar que a constraint esta ativa:
--   INSERT INTO pncp_raw_bids (pncp_id, esfera_id, source)
--   VALUES ('test-constraint-999', 99, 'pncp');
--   -- ERROR: new row for relation "pncp_raw_bids" violates check constraint
--
-- Para listar registros com esfera_id invalido (antes da limpeza):
--   SELECT pncp_id, esfera_id FROM pncp_raw_bids
--   WHERE esfera_id IS NOT NULL AND esfera_id NOT IN (1, 2, 3, 4);
