-- 111_pncp_procurement_results.sql
-- #545: official PNCP item resultados / adjudicacao / homologacao
-- before contract signature. Never fabricates contrato_id.
--
-- engineering_object is resolved by an EXACT natural-key join against the
-- parent compra (pncp_raw_bids.numero_controle_pncp, falling back to
-- pncp_supplier_contracts.parent_procurement_id). No fuzzy text matching;
-- absent parent leaves it NULL (UNKNOWN), never invented.
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
    engineering_object       TEXT,
    engineering_object_source TEXT CHECK (
        engineering_object_source IS NULL
        OR engineering_object_source IN ('pncp_raw_bids', 'pncp_supplier_contracts')
    ),
    event_at                DATE,
    source_published_at     DATE,
    first_seen_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    rule_version            TEXT NOT NULL,
    payload_hash            TEXT,
    CHECK (contrato_id IS NULL OR btrim(contrato_id) <> ''),
    CHECK (engineering_object_source IS NULL OR engineering_object IS NOT NULL)
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
COMMENT ON COLUMN public.pncp_procurement_results.engineering_object IS
    'objetoCompra/objeto_contrato of the parent compra, resolved by exact parent_procurement_id join. NULL when the parent is not present in either source table — never inferred or copied from unlinked text.';
COMMENT ON COLUMN public.pncp_procurement_results.engineering_object_source IS
    'Which table resolved engineering_object: pncp_raw_bids (compra pai) preferred, pncp_supplier_contracts as fallback.';

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
    ), contracts_by_parent AS (
        -- pncp_supplier_contracts has many rows per parent_procurement_id
        -- (one per item/contract). Collapse to a single deterministic
        -- objeto_contrato per parent before joining, so the join below
        -- cannot fan out and duplicate result_id rows.
        SELECT DISTINCT ON (parent_procurement_id)
            parent_procurement_id, objeto_contrato
        FROM public.pncp_supplier_contracts
        WHERE parent_procurement_id IS NOT NULL
          AND objeto_contrato IS NOT NULL
        ORDER BY parent_procurement_id, objeto_contrato
    ), resolved AS (
        SELECT
            input.*,
            COALESCE(bids.objeto_compra, contracts.objeto_contrato) AS resolved_engineering_object,
            CASE
                WHEN bids.objeto_compra IS NOT NULL THEN 'pncp_raw_bids'
                WHEN contracts.objeto_contrato IS NOT NULL THEN 'pncp_supplier_contracts'
                ELSE NULL
            END AS resolved_engineering_object_source
        FROM input
        LEFT JOIN public.pncp_raw_bids AS bids
            ON bids.numero_controle_pncp = input.parent_procurement_id
        LEFT JOIN contracts_by_parent AS contracts
            ON contracts.parent_procurement_id = input.parent_procurement_id
    ), upserted AS (
        INSERT INTO public.pncp_procurement_results AS target (
            result_id, parent_procurement_id, contrato_id, event_type, item_numero,
            situacao, winner_cnpj, winner_nome, valor_homologado,
            engineering_object, engineering_object_source, event_at,
            source_published_at, first_seen_at, last_seen_at, rule_version, payload_hash
        )
        SELECT
            resolved.in_result_id, resolved.parent_procurement_id,
            CASE
                WHEN EXISTS (
                    SELECT 1 FROM public.pncp_supplier_contracts c
                    WHERE c.contrato_id = resolved.contrato_id
                ) THEN resolved.contrato_id
                ELSE NULL
            END,
            resolved.event_type, resolved.item_numero, resolved.situacao, resolved.winner_cnpj,
            resolved.winner_nome, resolved.valor_homologado,
            resolved.resolved_engineering_object, resolved.resolved_engineering_object_source,
            resolved.event_at, resolved.source_published_at, resolved.first_seen_at, NOW(),
            resolved.rule_version, resolved.payload_hash
        FROM resolved
        ON CONFLICT ON CONSTRAINT pncp_procurement_results_pkey DO UPDATE SET
            last_seen_at = NOW(),
            situacao = COALESCE(EXCLUDED.situacao, target.situacao),
            winner_nome = COALESCE(EXCLUDED.winner_nome, target.winner_nome),
            valor_homologado = COALESCE(EXCLUDED.valor_homologado, target.valor_homologado),
            engineering_object = COALESCE(target.engineering_object, EXCLUDED.engineering_object),
            engineering_object_source = COALESCE(target.engineering_object_source, EXCLUDED.engineering_object_source),
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

-- Backfill engineering_object for rows resolved before the join existed
-- (idempotent; only ever fills NULL, never overwrites).
CREATE OR REPLACE FUNCTION public.backfill_procurement_results_engineering_object()
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    n_bids INTEGER;
    n_contracts INTEGER;
BEGIN
    UPDATE public.pncp_procurement_results AS result
    SET engineering_object = bids.objeto_compra,
        engineering_object_source = 'pncp_raw_bids'
    FROM public.pncp_raw_bids AS bids
    WHERE result.engineering_object IS NULL
      AND bids.numero_controle_pncp = result.parent_procurement_id
      AND bids.objeto_compra IS NOT NULL;
    GET DIAGNOSTICS n_bids = ROW_COUNT;

    UPDATE public.pncp_procurement_results AS result
    SET engineering_object = contracts.objeto_contrato,
        engineering_object_source = 'pncp_supplier_contracts'
    FROM (
        SELECT DISTINCT ON (parent_procurement_id)
            parent_procurement_id, objeto_contrato
        FROM public.pncp_supplier_contracts
        WHERE parent_procurement_id IS NOT NULL
          AND objeto_contrato IS NOT NULL
        ORDER BY parent_procurement_id, objeto_contrato
    ) AS contracts
    WHERE result.engineering_object IS NULL
      AND contracts.parent_procurement_id = result.parent_procurement_id;
    GET DIAGNOSTICS n_contracts = ROW_COUNT;
    RETURN n_bids + n_contracts;
END;
$$;

COMMIT;
