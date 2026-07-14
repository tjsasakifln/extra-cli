-- ============================================================================
-- Migration 033: Contract Versioning
-- ============================================================================
-- Story 1.2 (Unify Schema) — Contract versioning support
--
-- Adiciona versionamento e auditoria de mudancas em pncp_supplier_contracts
-- usando uma tabela de historico com trigger para capturar todas as
-- alteracoes (INSERT, UPDATE, DELETE) sem modificar a tabela principal.
--
-- Depende de: 002 (pncp_supplier_contracts existe)
-- Idempotente: Sim (IF NOT EXISTS)
-- Uso de LOCK_TIMEOUT para evitar lock prolongado em producao
-- ============================================================================

BEGIN;

-- Set safety timeouts for this migration
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

-- ============================================================================
-- 1. Contract history table
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.contract_version_history (
    id              BIGSERIAL PRIMARY KEY,
    contrato_id     TEXT NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1,
    changed_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    changed_by      TEXT NOT NULL DEFAULT 'migration_033',
    change_type     TEXT NOT NULL DEFAULT 'snapshot',
    snapshot        JSONB NOT NULL,

    CONSTRAINT uq_contract_version UNIQUE (contrato_id, version)
);

COMMENT ON TABLE public.contract_version_history IS
    'Historical versions of pncp_supplier_contracts. Story 1.2';

COMMENT ON COLUMN public.contract_version_history.contrato_id IS
    'FK logica para pncp_supplier_contracts.contrato_id';
COMMENT ON COLUMN public.contract_version_history.version IS
    'Numero de versao incremental por contrato_id';
COMMENT ON COLUMN public.contract_version_history.change_type IS
    'Tipo: snapshot|upsert|correction|deletion';
COMMENT ON COLUMN public.contract_version_history.snapshot IS
    'Snapshot completo do registro no momento da captura';

-- Indexes
CREATE INDEX IF NOT EXISTS idx_cvh_contrato_id
    ON public.contract_version_history (contrato_id, version DESC);

CREATE INDEX IF NOT EXISTS idx_cvh_changed_at
    ON public.contract_version_history (changed_at DESC)
    WHERE change_type = 'snapshot';

-- ============================================================================
-- 2. Function to capture contract snapshots
-- ============================================================================
CREATE OR REPLACE FUNCTION public.fn_capture_contract_snapshot()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    max_version INTEGER;
BEGIN
    SELECT COALESCE(MAX(version), 0) + 1
    INTO max_version
    FROM public.contract_version_history
    WHERE contrato_id = COALESCE(NEW.contrato_id, OLD.contrato_id);

    INSERT INTO public.contract_version_history (
        contrato_id, version, changed_by, change_type, snapshot
    ) VALUES (
        COALESCE(NEW.contrato_id, OLD.contrato_id),
        max_version,
        current_user,
        CASE
            WHEN TG_OP = 'DELETE' THEN 'deletion'
            WHEN TG_OP = 'UPDATE' THEN 'snapshot'
            ELSE 'snapshot'
        END,
        row_to_json(COALESCE(NEW, OLD))::JSONB
    );

    RETURN COALESCE(NEW, OLD);
END;
$$;

-- ============================================================================
-- 3. Trigger to capture changes
-- ============================================================================
-- NOTE: Em producao com 3.7M contratos, este trigger pode ser INTENSO.
-- Ativar apenas se o versionamento for necessario.
-- Por seguranca, criamos como disabled — ativar manualmente se precisar.
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_contract_versioning') THEN
        CREATE TRIGGER trg_contract_versioning
            AFTER INSERT OR UPDATE OR DELETE ON public.pncp_supplier_contracts
            FOR EACH ROW
            EXECUTE FUNCTION public.fn_capture_contract_snapshot();

        -- Disable by default — ONLY enable when versioning is explicitly needed
        ALTER TABLE public.pncp_supplier_contracts DISABLE TRIGGER trg_contract_versioning;
    END IF;
END $$;

COMMENT ON TRIGGER trg_contract_versioning ON public.pncp_supplier_contracts IS
    'Contract versioning trigger — DISABLED by default. Enable via: ALTER TABLE ... ENABLE TRIGGER trg_contract_versioning; Story 1.2';

-- ============================================================================
-- Rollback SQL
-- ============================================================================
-- DROP TRIGGER IF EXISTS trg_contract_versioning ON public.pncp_supplier_contracts;
-- DROP FUNCTION IF EXISTS public.fn_capture_contract_snapshot;
-- DROP TABLE IF EXISTS public.contract_version_history;

COMMIT;
