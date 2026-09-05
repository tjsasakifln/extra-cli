-- 111_pncp_procurement_results.sql
-- #545: official PNCP item resultados / adjudicacao / homologacao
-- before contract signature. Never fabricates contrato_id.
--
-- ROLLBACK: db/rollback/111_pncp_procurement_results_rollback.sql

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

CREATE TABLE IF NOT EXISTS public.pncp_procurement_results (
    result_id               TEXT PRIMARY KEY,
    parent_procurement_id   TEXT NOT NULL,
    contrato_id             TEXT,
    event_type              TEXT NOT NULL CHECK (event_type IN ('RESULT_PUBLISHED', 'HOMOLOGATED')),
    item_numero             INTEGER,
    situacao                TEXT,
    winner_cnpj             TEXT,
    winner_nome             TEXT,
    valor_homologado        NUMERIC(18,2),
    event_at                DATE,
    source_published_at     DATE,
    first_seen_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    rule_version            TEXT NOT NULL,
    payload_hash            TEXT,
    CHECK (contrato_id IS NULL OR btrim(contrato_id) <> '')
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_ppr_natural
    ON public.pncp_procurement_results (
        parent_procurement_id,
        COALESCE(item_numero, -1),
        COALESCE(winner_cnpj, ''),
        event_type
    );

CREATE INDEX IF NOT EXISTS idx_ppr_parent
    ON public.pncp_procurement_results (parent_procurement_id, event_at DESC);
CREATE INDEX IF NOT EXISTS idx_ppr_winner
    ON public.pncp_procurement_results (winner_cnpj, event_at DESC)
    WHERE winner_cnpj IS NOT NULL;

COMMENT ON TABLE public.pncp_procurement_results IS
    'Official PNCP pre-signature results (#545). contrato_id is NULL until a real contract exists; link is parent_procurement_id.';
COMMENT ON COLUMN public.pncp_procurement_results.event_at IS
    'Official result date. Distinct from first_seen_at and from contract data_assinatura.';
COMMENT ON COLUMN public.pncp_procurement_results.source_published_at IS
    'Official publication of the result, not lake observation.';
COMMENT ON COLUMN public.pncp_procurement_results.first_seen_at IS
    'Lake first observation of this result event.';
COMMENT ON COLUMN public.pncp_procurement_results.contrato_id IS
    'Filled only when a pncp_supplier_contracts row exists for the same parent_procurement_id. Never invented.';

CREATE OR REPLACE FUNCTION public.apply_pncp_procurement_results(p_records JSONB)
RETURNS TABLE (action TEXT, result_id TEXT)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH input AS (
        SELECT DISTINCT ON (rec->>'result_id')
            rec->>'result_id' AS in_result_id,
            rec->>'parent_procurement_id' AS parent_procurement_id,
            NULLIF(btrim(rec->>'contrato_id'), '') AS contrato_id,
            rec->>'event_type' AS event_type,
            NULLIF(rec->>'item_numero', '')::INTEGER AS item_numero,
            NULLIF(btrim(rec->>'situacao'), '') AS situacao,
            NULLIF(btrim(rec->>'winner_cnpj'), '') AS winner_cnpj,
            NULLIF(btrim(rec->>'winner_nome'), '') AS winner_nome,
            NULLIF(rec->>'valor_homologado', '')::NUMERIC AS valor_homologado,
            NULLIF(rec->>'event_at', '')::DATE AS event_at,
            NULLIF(rec->>'source_published_at', '')::DATE AS source_published_at,
            COALESCE(NULLIF(rec->>'first_seen_at', '')::TIMESTAMPTZ, NOW()) AS first_seen_at,
            COALESCE(NULLIF(rec->>'rule_version', ''), 'pncp-procurement-results-v1') AS rule_version,
            NULLIF(rec->>'payload_hash', '') AS payload_hash
        FROM jsonb_array_elements(p_records) AS rec
        WHERE COALESCE(rec->>'result_id', '') <> ''
          AND COALESCE(rec->>'parent_procurement_id', '') <> ''
          AND COALESCE(rec->>'event_type', '') IN ('RESULT_PUBLISHED', 'HOMOLOGATED')
        ORDER BY rec->>'result_id'
    ), upserted AS (
        INSERT INTO public.pncp_procurement_results AS target (
            result_id, parent_procurement_id, contrato_id, event_type, item_numero,
            situacao, winner_cnpj, winner_nome, valor_homologado, event_at,
            source_published_at, first_seen_at, last_seen_at, rule_version, payload_hash
        )
        SELECT
            input.in_result_id, input.parent_procurement_id,
            CASE
                WHEN EXISTS (
                    SELECT 1 FROM public.pncp_supplier_contracts c
                    WHERE c.contrato_id = input.contrato_id
                ) THEN input.contrato_id
                ELSE NULL
            END,
            input.event_type, input.item_numero, input.situacao, input.winner_cnpj,
            input.winner_nome, input.valor_homologado, input.event_at,
            input.source_published_at, input.first_seen_at, NOW(),
            input.rule_version, input.payload_hash
        FROM input
        ON CONFLICT ON CONSTRAINT pncp_procurement_results_pkey DO UPDATE SET
            last_seen_at = NOW(),
            situacao = COALESCE(EXCLUDED.situacao, target.situacao),
            winner_nome = COALESCE(EXCLUDED.winner_nome, target.winner_nome),
            valor_homologado = COALESCE(EXCLUDED.valor_homologado, target.valor_homologado),
            event_type = EXCLUDED.event_type,
            payload_hash = COALESCE(EXCLUDED.payload_hash, target.payload_hash),
            contrato_id = COALESCE(target.contrato_id, EXCLUDED.contrato_id)
        RETURNING target.result_id, (xmax = 0) AS is_insert
    )
    SELECT CASE WHEN upserted.is_insert THEN 'inserted' ELSE 'updated' END,
           upserted.result_id
    FROM upserted;
END;
$$;

-- Link existing contracts without inventing ids.
CREATE OR REPLACE FUNCTION public.link_procurement_results_to_contracts()
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    n INTEGER;
BEGIN
    UPDATE public.pncp_procurement_results AS result
    SET contrato_id = contract.contrato_id
    FROM public.pncp_supplier_contracts AS contract
    WHERE result.contrato_id IS NULL
      AND contract.parent_procurement_id = result.parent_procurement_id
      AND contract.contrato_id IS NOT NULL;
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END;
$$;

COMMIT;
