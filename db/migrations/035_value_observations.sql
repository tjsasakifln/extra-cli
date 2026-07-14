-- ============================================================================
-- Migration 035: Value Observations + Retention Policies
-- ============================================================================
-- Story 1.2 (Unify Schema) — Task 10 (Retention Policies DT-22)
--
-- 1. Enhanced purge_old_bids with configurable retention
-- 2. Value observation materialization for bid_simulator
-- 3. Retention metadata columns
--
-- DESIGN:
--   - Politica de retencao configurada via parametros (nao hardcoded)
--   - Purging seguro com dry-run mode e batch processing
--   - LOCK_TIMEOUT=5s para operacoes em tabelas grandes
--
-- Depende de: 008 (purge_rpc), 030 (canonical views)
-- Idempotente: Sim
-- ============================================================================

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

-- ============================================================================
-- PART 1: Enhanced purge function with configurable retention
-- ============================================================================
-- Substitui a purge_rpc basica (008) por uma versao com:
--   - Parametros de configuracao (dias, dry_run, batch_size)
--   - Suporte a soft-delete (is_active = FALSE)
--   - Logging de resultados
--   ============================================================================

CREATE OR REPLACE FUNCTION public.fn_purge_old_data(
    p_table     TEXT DEFAULT 'pncp_raw_bids',
    p_field     TEXT DEFAULT 'data_publicacao',
    p_retention_days INTEGER DEFAULT 730,  -- 2 anos
    p_dry_run   BOOLEAN DEFAULT TRUE,
    p_batch_size INTEGER DEFAULT 10000
)
RETURNS TABLE (
    action      TEXT,
    table_name  TEXT,
    rows_affected BIGINT,
    duration_ms DOUBLE PRECISION
) LANGUAGE plpgsql AS $$
DECLARE
    cutoff_date DATE;
    v_count     BIGINT;
    start_ts    TIMESTAMPTZ;
    end_ts      TIMESTAMPTZ;
BEGIN
    cutoff_date := CURRENT_DATE - p_retention_days;
    start_ts := clock_timestamp();

    -- Validate table/field to prevent SQL injection (whitelist)
    IF p_table NOT IN ('pncp_raw_bids', 'pncp_supplier_contracts') THEN
        RETURN QUERY SELECT 'error'::TEXT, p_table, 0::BIGINT, 0::DOUBLE PRECISION;
        RETURN;
    END IF;
    IF p_field NOT IN ('data_publicacao', 'data_encerramento', 'ingested_at') THEN
        RETURN QUERY SELECT 'error'::TEXT, p_field, 0::BIGINT, 0::DOUBLE PRECISION;
        RETURN;
    END IF;

    IF p_table = 'pncp_raw_bids' THEN
        EXECUTE format(
            'SELECT COUNT(*) FROM %I WHERE %I < $1 AND is_active = TRUE',
            p_table, p_field
        ) INTO v_count USING cutoff_date;

        IF p_dry_run THEN
            end_ts := clock_timestamp();
            RETURN QUERY SELECT 'dry-run'::TEXT, p_table, v_count,
                EXTRACT(EPOCH FROM (end_ts - start_ts)) * 1000;
        ELSE
            -- Batch delete (soft-delete: is_active = FALSE preserves FK integrity)
            LOOP
                EXECUTE format(
                    'UPDATE %I SET is_active = FALSE WHERE %I < $1 AND is_active = TRUE LIMIT $2',
                    p_table, p_field
                ) USING cutoff_date, p_batch_size;

                EXIT WHEN NOT FOUND;
            END LOOP;

            end_ts := clock_timestamp();
            RETURN QUERY SELECT 'purged'::TEXT, p_table, v_count,
                EXTRACT(EPOCH FROM (end_ts - start_ts)) * 1000;
        END IF;
    ELSE
        -- pncp_supplier_contracts (mesma logica)
        EXECUTE format(
            'SELECT COUNT(*) FROM %I WHERE %I < $1 AND is_active = TRUE',
            p_table, p_field
        ) INTO v_count USING cutoff_date;

        IF p_dry_run THEN
            end_ts := clock_timestamp();
            RETURN QUERY SELECT 'dry-run'::TEXT, p_table, v_count,
                EXTRACT(EPOCH FROM (end_ts - start_ts)) * 1000;
        ELSE
            LOOP
                EXECUTE format(
                    'UPDATE %I SET is_active = FALSE WHERE %I < $1 AND is_active = TRUE LIMIT $2',
                    p_table, p_field
                ) USING cutoff_date, p_batch_size;
                EXIT WHEN NOT FOUND;
            END LOOP;

            end_ts := clock_timestamp();
            RETURN QUERY SELECT 'purged'::TEXT, p_table, v_count,
                EXTRACT(EPOCH FROM (end_ts - start_ts)) * 1000;
        END IF;
    END IF;
END;
$$;

COMMENT ON FUNCTION public.fn_purge_old_data IS
    'Configurable data retention purge. Default: 730 days. Use dry_run=TRUE to preview. Story 1.2 (DT-22)';

-- ============================================================================
-- PART 2: Retention tracking table
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.retention_policy (
    id              BIGSERIAL PRIMARY KEY,
    table_name      TEXT NOT NULL,
    field_name      TEXT NOT NULL,
    retention_days  INTEGER NOT NULL DEFAULT 730,
    strategy        TEXT NOT NULL DEFAULT 'soft_delete',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_retention_policy UNIQUE (table_name, field_name),
    CONSTRAINT ck_retention_strategy CHECK (strategy IN ('soft_delete', 'hard_delete', 'archive'))
);

COMMENT ON TABLE public.retention_policy IS
    'Retention policy configuration. Story 1.2 (DT-22)';

-- Default policies
INSERT INTO public.retention_policy (table_name, field_name, retention_days, strategy)
VALUES
    ('pncp_raw_bids', 'data_publicacao', 730, 'soft_delete'),
    ('pncp_supplier_contracts', 'data_publicacao', 1095, 'soft_delete')  -- 3 anos para contratos
ON CONFLICT (table_name, field_name) DO NOTHING;

-- ============================================================================
-- PART 3: Value observation statistics function
-- ============================================================================
CREATE OR REPLACE FUNCTION public.fn_value_statistics(
    p_uf           TEXT DEFAULT NULL,
    p_modalidade_id INTEGER DEFAULT NULL,
    p_days         INTEGER DEFAULT 365
)
RETURNS TABLE (
    observation_type TEXT,
    total_observations BIGINT,
    avg_valor       NUMERIC(18,2),
    median_valor    NUMERIC(18,2),
    min_valor       NUMERIC(18,2),
    max_valor       NUMERIC(18,2),
    p25_valor       NUMERIC(18,2),
    p75_valor       NUMERIC(18,2),
    stddev_valor    NUMERIC(18,2)
) LANGUAGE plpgsql STABLE AS $$
BEGIN
    RETURN QUERY
    SELECT
        v.observation_type,
        COUNT(*)::BIGINT,
        ROUND(AVG(v.valor), 2),
        ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY v.valor)::NUMERIC, 2),
        ROUND(MIN(v.valor), 2),
        ROUND(MAX(v.valor), 2),
        ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY v.valor)::NUMERIC, 2),
        ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY v.valor)::NUMERIC, 2),
        ROUND(STDDEV(v.valor)::NUMERIC, 2)
    FROM public.v_value_observations_canonical v
    WHERE (p_uf IS NULL OR v.uf = p_uf)
      AND (p_modalidade_id IS NULL OR v.modalidade_id = p_modalidade_id)
      AND v.data_publicacao >= CURRENT_DATE - p_days
      AND v.valor IS NOT NULL
    GROUP BY v.observation_type
    ORDER BY v.observation_type;
END;
$$;

COMMENT ON FUNCTION public.fn_value_statistics IS
    'Statistical summary of value observations. Used by bid_simulator. Story 1.2';

-- ============================================================================
-- Rollback SQL
-- ============================================================================
-- DROP FUNCTION IF EXISTS public.fn_value_statistics;
-- DROP TABLE IF EXISTS public.retention_policy;
-- DROP FUNCTION IF EXISTS public.fn_purge_old_data;

COMMIT;
