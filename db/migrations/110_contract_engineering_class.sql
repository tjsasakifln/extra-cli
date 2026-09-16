-- 110_contract_engineering_class.sql
-- #544: persisted, versioned engineering class per contract.
-- Authority: scripts/contracts/engineering_class.py — consumers must not regex.
--
-- ROLLBACK:
--   psql "$LOCAL_DATALAKE_DSN" -f db/rollback/110_contract_engineering_class_rollback.sql

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

CREATE TABLE IF NOT EXISTS public.contract_engineering_class (
    contrato_id     TEXT PRIMARY KEY
                        REFERENCES public.pncp_supplier_contracts(contrato_id)
                        ON DELETE CASCADE,
    engineering_class TEXT NOT NULL CHECK (engineering_class IN (
        'OBRA_EXECUCAO',
        'OBRA_COM_PROJETO',
        'PROJETO_ENGENHARIA',
        'FISCALIZACAO_GERENCIAMENTO',
        'MANUTENCAO_PREDIAL_INFRA',
        'INSTALACOES',
        'FORNECIMENTO_COM_INSTALACAO',
        'NAO_ENGENHARIA'
    )),
    confidence      NUMERIC(6,5) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    categories      TEXT[] NOT NULL DEFAULT '{}',
    evidence        TEXT[] NOT NULL DEFAULT '{}',
    rule_version    TEXT NOT NULL,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cec_class_conf
    ON public.contract_engineering_class (engineering_class, confidence DESC);
CREATE INDEX IF NOT EXISTS idx_cec_computed
    ON public.contract_engineering_class (computed_at DESC);

COMMENT ON TABLE public.contract_engineering_class IS
    'Versioned engineering class per contract (#544). Canonical authority; do not reimplement with objeto regex.';

CREATE OR REPLACE FUNCTION public.apply_contract_engineering_class(p_records JSONB)
RETURNS TABLE (action TEXT, contrato_id TEXT)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH input AS (
        SELECT DISTINCT ON (rec->>'contrato_id')
            rec->>'contrato_id' AS in_contrato_id,
            rec->>'engineering_class' AS engineering_class,
            NULLIF(rec->>'confidence', '')::NUMERIC AS confidence,
            COALESCE(
                ARRAY(SELECT jsonb_array_elements_text(COALESCE(rec->'categories', '[]'::jsonb))),
                '{}'::TEXT[]
            ) AS categories,
            COALESCE(
                ARRAY(SELECT jsonb_array_elements_text(COALESCE(rec->'evidence', '[]'::jsonb))),
                '{}'::TEXT[]
            ) AS evidence,
            COALESCE(NULLIF(rec->>'rule_version', ''), 'engineering-class-v1') AS rule_version,
            COALESCE(NULLIF(rec->>'computed_at', '')::TIMESTAMPTZ, NOW()) AS computed_at
        FROM jsonb_array_elements(p_records) AS rec
        WHERE COALESCE(rec->>'contrato_id', '') <> ''
          AND COALESCE(rec->>'engineering_class', '') <> ''
        ORDER BY rec->>'contrato_id'
    ), upserted AS (
        INSERT INTO public.contract_engineering_class AS target (
            contrato_id, engineering_class, confidence, categories, evidence,
            rule_version, computed_at
        )
        SELECT
            input.in_contrato_id, input.engineering_class, input.confidence,
            input.categories, input.evidence, input.rule_version, input.computed_at
        FROM input
        JOIN public.pncp_supplier_contracts contract
            ON contract.contrato_id = input.in_contrato_id
        ON CONFLICT ON CONSTRAINT contract_engineering_class_pkey DO UPDATE SET
            engineering_class = EXCLUDED.engineering_class,
            confidence = EXCLUDED.confidence,
            categories = EXCLUDED.categories,
            evidence = EXCLUDED.evidence,
            rule_version = EXCLUDED.rule_version,
            computed_at = EXCLUDED.computed_at
        RETURNING target.contrato_id
    )
    SELECT 'upserted'::TEXT, upserted.contrato_id
    FROM upserted;
END;
$$;

COMMENT ON FUNCTION public.apply_contract_engineering_class(JSONB) IS
    'Idempotent persist of #544 engineering class. Does not invent contrato_id.';

COMMIT;
