-- ============================================================================
-- Migration 041: Fix FK Constraints — 14-digit CNPJ vs 8-digit cnpj_8 mismatch
-- ============================================================================
-- Story 1.2 (Unify Schema) — CRITICAL bugfix
--
-- PROBLEM:
-- Migration 034 created 3 FKs that reference sc_public_entities(cnpj_8) which
-- stores 8-digit CNPJ base, but the source columns contain full 14-digit CNPJ:
--
--   fk_bids_orgao_entity:
--     pncp_raw_bids.orgao_cnpj (14-digit) → sc_public_entities.cnpj_8 (8-digit)
--   fk_contracts_orgao_entity:
--     pncp_supplier_contracts.orgao_cnpj (14-digit) → sc_public_entities.cnpj_8 (8-digit)
--   fk_contracts_supplier_entity:
--     pncp_supplier_contracts.fornecedor_cnpj (14-digit) → sc_public_entities.cnpj_8 (8-digit)
--
-- A FK constraint compares values literally: "12345678901234" != "12345678",
-- so the FKs can never be validated and will reject all INSERT/UPDATE.
--
-- FIX:
-- 1. Drop the 3 broken FKs
-- 2. Add GENERATED ALWAYS AS (LEFT(col, 8)) STORED columns to child tables
-- 3. Create new FKs on the generated 8-digit columns
-- 4. All new FKs use NOT VALID to avoid locking -- VALIDATE separately
--
-- Depende de: 034_supplier_identity.sql (criou as FKs quebradas)
-- Idempotente: Sim (DROP IF EXISTS / IF NOT EXISTS)
-- ============================================================================

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

-- ============================================================================
-- PART 1: Drop broken FKs
-- ============================================================================
-- As FKs originais comparam CNPJ de 14 digitos com cnpj_8 de 8 digitos.
-- Mesmo com NOT VALID, elas blockeriam qualquer INSERT/UPDATE que nao
-- encontrasse um valor de 14 digitos em sc_public_entities.cnpj_8.

ALTER TABLE IF EXISTS public.pncp_raw_bids
    DROP CONSTRAINT IF EXISTS fk_bids_orgao_entity;

ALTER TABLE IF EXISTS public.pncp_supplier_contracts
    DROP CONSTRAINT IF EXISTS fk_contracts_orgao_entity;

ALTER TABLE IF EXISTS public.pncp_supplier_contracts
    DROP CONSTRAINT IF EXISTS fk_contracts_supplier_entity;

RAISE NOTICE 'Part 1: Dropped 3 broken FKs (fk_bids_orgao_entity, fk_contracts_orgao_entity, fk_contracts_supplier_entity).';

-- ============================================================================
-- PART 2: Add generated cnpj_8 columns to child tables
-- ============================================================================
-- Colunas GENERATED ALWAYS AS STORED mantem-se sincronizadas automaticamente
-- com o valor original. Nao podem ser escritas diretamente (somente leitura).
-- Usamos LEFT(col, 8) para extrair os primeiros 8 digitos do CNPJ,
-- que e exatamente o que as views existentes ja fazem via LEFT() nas JOINs.

-- pncp_raw_bids: orgao_cnpj -> orgao_cnpj_8
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'pncp_raw_bids'
          AND column_name = 'orgao_cnpj_8'
    ) THEN
        ALTER TABLE public.pncp_raw_bids
            ADD COLUMN orgao_cnpj_8 TEXT
            GENERATED ALWAYS AS (LEFT(orgao_cnpj, 8)) STORED;
        RAISE NOTICE 'Added orgao_cnpj_8 to pncp_raw_bids.';
    ELSE
        RAISE NOTICE 'orgao_cnpj_8 already exists on pncp_raw_bids.';
    END IF;
END $$;

-- pncp_supplier_contracts: orgao_cnpj -> orgao_cnpj_8
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'pncp_supplier_contracts'
          AND column_name = 'orgao_cnpj_8'
    ) THEN
        ALTER TABLE public.pncp_supplier_contracts
            ADD COLUMN orgao_cnpj_8 TEXT
            GENERATED ALWAYS AS (LEFT(orgao_cnpj, 8)) STORED;
        RAISE NOTICE 'Added orgao_cnpj_8 to pncp_supplier_contracts.';
    ELSE
        RAISE NOTICE 'orgao_cnpj_8 already exists on pncp_supplier_contracts.';
    END IF;
END $$;

-- pncp_supplier_contracts: fornecedor_cnpj -> fornecedor_cnpj_8
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'pncp_supplier_contracts'
          AND column_name = 'fornecedor_cnpj_8'
    ) THEN
        ALTER TABLE public.pncp_supplier_contracts
            ADD COLUMN fornecedor_cnpj_8 TEXT
            GENERATED ALWAYS AS (LEFT(fornecedor_cnpj, 8)) STORED;
        RAISE NOTICE 'Added fornecedor_cnpj_8 to pncp_supplier_contracts.';
    ELSE
        RAISE NOTICE 'fornecedor_cnpj_8 already exists on pncp_supplier_contracts.';
    END IF;
END $$;

-- ============================================================================
-- PART 3: Create valid FKs on generated columns
-- ============================================================================
-- As novas FKs usam as colunas geradas de 8 digitos, que tem o mesmo tipo
-- (TEXT) e mesmo comprimento que sc_public_entities.cnpj_8.
--
-- NOT VALID: evita lock full nas tabelas durante a criacao.
-- A validacao deve ser executada separadamente em horario de baixo trafego:
--   ALTER TABLE pncp_raw_bids VALIDATE CONSTRAINT fk_bids_orgao_entity_v2;
--   ALTER TABLE pncp_supplier_contracts VALIDATE CONSTRAINT fk_contracts_orgao_entity_v2;
--   ALTER TABLE pncp_supplier_contracts VALIDATE CONSTRAINT fk_contracts_supplier_entity_v2;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_bids_orgao_entity_v2') THEN
        ALTER TABLE public.pncp_raw_bids
            ADD CONSTRAINT fk_bids_orgao_entity_v2
            FOREIGN KEY (orgao_cnpj_8) REFERENCES public.sc_public_entities(cnpj_8)
            ON UPDATE CASCADE ON DELETE SET NULL
            NOT VALID;
        RAISE NOTICE 'FK fk_bids_orgao_entity_v2 created (NOT VALID).';
    ELSE
        RAISE NOTICE 'FK fk_bids_orgao_entity_v2 already exists.';
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_contracts_orgao_entity_v2') THEN
        ALTER TABLE public.pncp_supplier_contracts
            ADD CONSTRAINT fk_contracts_orgao_entity_v2
            FOREIGN KEY (orgao_cnpj_8) REFERENCES public.sc_public_entities(cnpj_8)
            ON UPDATE CASCADE ON DELETE SET NULL
            NOT VALID;
        RAISE NOTICE 'FK fk_contracts_orgao_entity_v2 created (NOT VALID).';
    ELSE
        RAISE NOTICE 'FK fk_contracts_orgao_entity_v2 already exists.';
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_contracts_supplier_entity_v2') THEN
        ALTER TABLE public.pncp_supplier_contracts
            ADD CONSTRAINT fk_contracts_supplier_entity_v2
            FOREIGN KEY (fornecedor_cnpj_8) REFERENCES public.sc_public_entities(cnpj_8)
            ON UPDATE CASCADE ON DELETE SET NULL
            NOT VALID;
        RAISE NOTICE 'FK fk_contracts_supplier_entity_v2 created (NOT VALID).';
    ELSE
        RAISE NOTICE 'FK fk_contracts_supplier_entity_v2 already exists.';
    END IF;
END $$;

-- ============================================================================
-- PART 4: Comments documenting the fix
-- ============================================================================

COMMENT ON COLUMN public.pncp_raw_bids.orgao_cnpj_8 IS
    'CNPJ base 8 digitos (generated). FK target for sc_public_entities. Fix 041.';

COMMENT ON COLUMN public.pncp_supplier_contracts.orgao_cnpj_8 IS
    'CNPJ base 8 digitos (generated). FK target for sc_public_entities. Fix 041.';

COMMENT ON COLUMN public.pncp_supplier_contracts.fornecedor_cnpj_8 IS
    'CNPJ base 8 digitos (generated). FK target for sc_public_entities. Fix 041.';

COMMENT ON CONSTRAINT fk_bids_orgao_entity_v2 ON public.pncp_raw_bids IS
    'FK orgao_cnpj_8 -> sc_public_entities.cnpj_8. Fix 041 (substitui fk_bids_orgao_entity que usava 14-digit orgao_cnpj contra cnpj_8 de 8 digitos). Validar: ALTER TABLE pncp_raw_bids VALIDATE CONSTRAINT fk_bids_orgao_entity_v2;';

COMMENT ON CONSTRAINT fk_contracts_orgao_entity_v2 ON public.pncp_supplier_contracts IS
    'FK orgao_cnpj_8 -> sc_public_entities.cnpj_8. Fix 041. Validar: ALTER TABLE pncp_supplier_contracts VALIDATE CONSTRAINT fk_contracts_orgao_entity_v2;';

COMMENT ON CONSTRAINT fk_contracts_supplier_entity_v2 ON public.pncp_supplier_contracts IS
    'FK fornecedor_cnpj_8 -> sc_public_entities.cnpj_8. Fix 041. Validar: ALTER TABLE pncp_supplier_contracts VALIDATE CONSTRAINT fk_contracts_supplier_entity_v2;';

-- ============================================================================
-- PART 5: Indexes on generated columns for FK lookup performance
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_bids_orgao_cnpj_8
    ON public.pncp_raw_bids (orgao_cnpj_8)
    WHERE orgao_cnpj_8 IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_contracts_orgao_cnpj_8
    ON public.pncp_supplier_contracts (orgao_cnpj_8)
    WHERE orgao_cnpj_8 IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_contracts_fornecedor_cnpj_8
    ON public.pncp_supplier_contracts (fornecedor_cnpj_8)
    WHERE fornecedor_cnpj_8 IS NOT NULL;

RAISE NOTICE 'Fix 041 complete. Run VALIDATE CONSTRAINT separately for each FK in low-traffic window.';

-- ============================================================================
-- PART 6: Update schema integrity view to reference new FK names
-- ============================================================================
-- Migration 036 criou v_schema_integrity com os nomes antigos das FKs.
-- Como 041 substitui fk_bids_orgao_entity → fk_bids_orgao_entity_v2 (etc),
-- precisamos atualizar a view para que o check de integridade reflita
-- os nomes corretos.

CREATE OR REPLACE VIEW public.v_schema_integrity AS
SELECT
    'tables'::TEXT AS check_type,
    COUNT(*)::INTEGER AS total_expected,
    COUNT(*) FILTER (WHERE EXISTS (
        SELECT 1 FROM information_schema.tables t
        WHERE t.table_schema = 'public'
        AND t.table_name = o.object_name
    ))::INTEGER AS present,
    COUNT(*) FILTER (WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.tables t
        WHERE t.table_schema = 'public'
        AND t.table_name = o.object_name
    ))::INTEGER AS missing
FROM (VALUES
    ('pncp_raw_bids'), ('pncp_supplier_contracts'), ('sc_public_entities'),
    ('enriched_entities'), ('entity_coverage'), ('entity_hierarchy'),
    ('coverage_snapshots'), ('coverage_evidence'), ('opportunity_intel'),
    ('ingestion_runs'), ('ingestion_checkpoints')
) AS o(object_name)

UNION ALL

SELECT
    'views'::TEXT AS check_type,
    COUNT(*)::INTEGER,
    COUNT(*) FILTER (WHERE EXISTS (
        SELECT 1 FROM information_schema.views v
        WHERE v.table_schema = 'public'
        AND v.table_name = o.object_name
    ))::INTEGER,
    COUNT(*) FILTER (WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.views v
        WHERE v.table_schema = 'public'
        AND v.table_name = o.object_name
    ))::INTEGER
FROM (VALUES
    ('v_entities_canonical'), ('v_open_opportunities_canonical'),
    ('v_contracts_canonical'), ('v_suppliers_canonical'),
    ('v_value_observations_canonical'), ('v_latest_evidence'),
    ('v_source_health'), ('v_coverage_health'),
    ('v_schema_integrity'), ('v_capability_coverage_summary')
) AS o(object_name)

UNION ALL

SELECT
    'fk_constraints'::TEXT,
    COUNT(*)::INTEGER,
    COUNT(*) FILTER (WHERE EXISTS (
        SELECT 1 FROM pg_constraint c
        JOIN pg_class cl ON c.conrelid = cl.oid
        WHERE c.conname = o.object_name
    ))::INTEGER,
    COUNT(*) FILTER (WHERE NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        JOIN pg_class cl ON c.conrelid = cl.oid
        WHERE c.conname = o.object_name
    ))::INTEGER
FROM (VALUES
    ('fk_bids_orgao_entity_v2'), ('fk_contracts_supplier_entity_v2'),
    ('fk_contracts_orgao_entity_v2'), ('uq_spe_cnpj_8'),
    ('uq_oi_content_hash')
) AS o(object_name);

RAISE NOTICE 'Part 6: Updated v_schema_integrity view with new FK constraint names.';

-- ============================================================================
-- Rollback SQL
-- ============================================================================
-- ALTER TABLE public.pncp_raw_bids DROP CONSTRAINT IF EXISTS fk_bids_orgao_entity_v2;
-- ALTER TABLE public.pncp_supplier_contracts DROP CONSTRAINT IF EXISTS fk_contracts_orgao_entity_v2;
-- ALTER TABLE public.pncp_supplier_contracts DROP CONSTRAINT IF EXISTS fk_contracts_supplier_entity_v2;
-- ALTER TABLE public.pncp_raw_bids DROP COLUMN IF EXISTS orgao_cnpj_8;
-- ALTER TABLE public.pncp_supplier_contracts DROP COLUMN IF EXISTS orgao_cnpj_8;
-- ALTER TABLE public.pncp_supplier_contracts DROP COLUMN IF EXISTS fornecedor_cnpj_8;
-- DROP INDEX IF EXISTS idx_bids_orgao_cnpj_8;
-- DROP INDEX IF EXISTS idx_contracts_orgao_cnpj_8;
-- DROP INDEX IF EXISTS idx_contracts_fornecedor_cnpj_8;
-- ============================================================================

COMMIT;
