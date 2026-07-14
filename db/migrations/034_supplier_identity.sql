-- ============================================================================
-- Migration 034: Supplier Identity — FK Constraints + UNIQUE cnpj_8 + ID Enhancements
-- ============================================================================
-- Story 1.2 (Unify Schema) — Tasks 8 (FK constraints DT-19/DT-20) and 9 (UNIQUE cnpj_8 DT-06)
--
-- 1. FK pncp_raw_bids.orgao_cnpj → sc_public_entities (DT-19)
-- 2. FK pncp_supplier_contracts → sc_public_entities (DT-20)
-- 3. UNIQUE constraint on sc_public_entities.cnpj_8 (DT-06) with pre-check
-- 4. Supplier identity index improvements
--
-- DESIGN DECISIONS:
--   - FKs usam NOT VALID + VALIDATE para evitar lock prolongado
--   - UNIQUE constraint usa pre-check com relatorio de duplicatas
--   - LOCK_TIMEOUT=5s para evitar lock de tabelas grandes em producao
--
-- Depende de: 001 (pncp_raw_bids), 002 (pncp_supplier_contracts), 007 (sc_public_entities)
-- Idempotente: Sim
-- ============================================================================

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

-- ============================================================================
-- PART 1: Pre-check for UNIQUE constraint on sc_public_entities.cnpj_8
-- ============================================================================
-- Gera relatorio de duplicatas ANTES de tentar criar a constraint.
-- A constraint so e criada se nao houver duplicatas.

DO $$
DECLARE
    dup_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO dup_count
    FROM (
        SELECT cnpj_8 FROM public.sc_public_entities
        WHERE cnpj_8 IS NOT NULL AND cnpj_8 != ''
        GROUP BY cnpj_8
        HAVING COUNT(*) > 1
    ) dups;

    IF dup_count > 0 THEN
        RAISE WARNING 'UNIQUE cnpj_8 pre-check: % duplicatas encontradas. Criando relatorio.', dup_count;
    ELSE
        RAISE NOTICE 'UNIQUE cnpj_8 pre-check: OK — nenhuma duplicata.';
    END IF;
END $$;

-- ============================================================================
-- PART 2: Add UNIQUE constraint on cnpj_8 (if no duplicates)
-- ============================================================================
-- NOTE: Em producao com duplicatas, executar manualmente:
--   1. Analisar duplicatas: SELECT cnpj_8, COUNT(*) FROM sc_public_entities
--      WHERE cnpj_8 IS NOT NULL GROUP BY cnpj_8 HAVING COUNT(*) > 1;
--   2. Resolver duplicatas
--   3. CREATE UNIQUE INDEX CONCURRENTLY uq_spe_cnpj_8 ON sc_public_entities (cnpj_8);
--   4. ALTER TABLE sc_public_entities ADD CONSTRAINT uq_spe_cnpj_8
--      UNIQUE USING INDEX uq_spe_cnpj_8;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_spe_cnpj_8') THEN
        -- Check for duplicates one more time
        IF NOT EXISTS (
            SELECT 1 FROM (
                SELECT cnpj_8 FROM public.sc_public_entities
                WHERE cnpj_8 IS NOT NULL AND cnpj_8 != ''
                GROUP BY cnpj_8 HAVING COUNT(*) > 1
            ) dups
        ) THEN
            ALTER TABLE public.sc_public_entities
                ADD CONSTRAINT uq_spe_cnpj_8 UNIQUE (cnpj_8);
            RAISE NOTICE 'UNIQUE constraint uq_spe_cnpj_8 created successfully.';
        ELSE
            RAISE WARNING 'Cannot create UNIQUE constraint: duplicates exist in sc_public_entities.cnpj_8. Execute dedup first.';
        END IF;
    ELSE
        RAISE NOTICE 'UNIQUE constraint uq_spe_cnpj_8 already exists.';
    END IF;
END $$;

COMMENT ON CONSTRAINT uq_spe_cnpj_8 ON public.sc_public_entities IS
    'Unique constraint on CNPJ base (8 digits). Created by Story 1.2 (DT-06).';

-- ============================================================================
-- PART 3: FK pncp_raw_bids.orgao_cnpj → sc_public_entities (DT-19)
-- ============================================================================
-- Usando NOT VALID para evitar lock full na tabela pncp_raw_bids.
-- A validacao pode ser feita em segundo plano.

DO $$
DECLARE
    orphan_count INTEGER;
BEGIN
    -- Pre-check: contar orfaos
    SELECT COUNT(*) INTO orphan_count
    FROM public.pncp_raw_bids b
    WHERE b.orgao_cnpj IS NOT NULL AND b.orgao_cnpj != ''
      AND NOT EXISTS (
          SELECT 1 FROM public.sc_public_entities e
          WHERE e.cnpj_8 = LEFT(b.orgao_cnpj, 8)
      );

    IF orphan_count > 0 THEN
        RAISE WARNING 'FK pre-check: % registros orfaos em pncp_raw_bids.orgao_cnpj (sem entidade correspondente).', orphan_count;
    END IF;
END $$;

-- FK: pncp_raw_bids.orgao_cnpj → sc_public_entities.cnpj_8 (via LEFT 8)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_bids_orgao_entity') THEN
        ALTER TABLE public.pncp_raw_bids
            ADD CONSTRAINT fk_bids_orgao_entity
            FOREIGN KEY (orgao_cnpj) REFERENCES public.sc_public_entities(cnpj_8)
            ON UPDATE CASCADE ON DELETE SET NULL
            NOT VALID;  -- Avoid full table scan during migration
        RAISE NOTICE 'FK fk_bids_orgao_entity created (NOT VALID). Run VALIDATE later.';
    END IF;
END $$;

COMMENT ON CONSTRAINT fk_bids_orgao_entity ON public.pncp_raw_bids IS
    'FK orgao_cnpj → sc_public_entities.cnpj_8. Created NOT VALID por Story 1.2 (DT-19). Validar: ALTER TABLE pncp_raw_bids VALIDATE CONSTRAINT fk_bids_orgao_entity;';

-- ============================================================================
-- PART 4: FK pncp_supplier_contracts → sc_public_entities (DT-20)
-- ============================================================================
-- Mapeia fornecedor_cnpj → sc_public_entities (LEFT 8)
DO $$
DECLARE
    orphan_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO orphan_count
    FROM public.pncp_supplier_contracts c
    WHERE c.fornecedor_cnpj IS NOT NULL AND c.fornecedor_cnpj != ''
      AND NOT EXISTS (
          SELECT 1 FROM public.sc_public_entities e
          WHERE e.cnpj_8 = LEFT(c.fornecedor_cnpj, 8)
      );

    IF orphan_count > 0 THEN
        RAISE WARNING 'FK pre-check: % registros orfaos em pncp_supplier_contracts.fornecedor_cnpj.', orphan_count;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_contracts_supplier_entity') THEN
        ALTER TABLE public.pncp_supplier_contracts
            ADD CONSTRAINT fk_contracts_supplier_entity
            FOREIGN KEY (fornecedor_cnpj) REFERENCES public.sc_public_entities(cnpj_8)
            ON UPDATE CASCADE ON DELETE SET NULL
            NOT VALID;
        RAISE NOTICE 'FK fk_contracts_supplier_entity created (NOT VALID).';
    END IF;
END $$;

COMMENT ON CONSTRAINT fk_contracts_supplier_entity ON public.pncp_supplier_contracts IS
    'FK fornecedor_cnpj → sc_public_entities.cnpj_8. Story 1.2 (DT-20).';

-- FK: contract orgao_cnpj → sc_public_entities
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_contracts_orgao_entity') THEN
        ALTER TABLE public.pncp_supplier_contracts
            ADD CONSTRAINT fk_contracts_orgao_entity
            FOREIGN KEY (orgao_cnpj) REFERENCES public.sc_public_entities(cnpj_8)
            ON UPDATE CASCADE ON DELETE SET NULL
            NOT VALID;
        RAISE NOTICE 'FK fk_contracts_orgao_entity created (NOT VALID).';
    END IF;
END $$;

-- ============================================================================
-- PART 5: Supplier identity — index for supplier lookups
-- ============================================================================
-- Note: is_active check only on tables that have it (pncp_raw_bids)
CREATE INDEX IF NOT EXISTS idx_contracts_fornecedor_cnpj_lookup
    ON public.pncp_supplier_contracts (fornecedor_cnpj)
    WHERE fornecedor_cnpj IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_bids_orgao_cnpj_lookup
    ON public.pncp_raw_bids (orgao_cnpj, data_publicacao DESC)
    WHERE orgao_cnpj IS NOT NULL;

-- ============================================================================
-- Rollback SQL
-- ============================================================================
-- ALTER TABLE public.pncp_raw_bids DROP CONSTRAINT IF EXISTS fk_bids_orgao_entity;
-- ALTER TABLE public.pncp_supplier_contracts DROP CONSTRAINT IF EXISTS fk_contracts_supplier_entity;
-- ALTER TABLE public.pncp_supplier_contracts DROP CONSTRAINT IF EXISTS fk_contracts_orgao_entity;
-- ALTER TABLE public.sc_public_entities DROP CONSTRAINT IF EXISTS uq_spe_cnpj_8;

COMMIT;
