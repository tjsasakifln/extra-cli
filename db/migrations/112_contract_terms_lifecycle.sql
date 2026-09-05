-- 112_contract_terms_lifecycle.sql
-- #548: aditivo, retificação, rescisão, revogação, anulação as distinct events.
-- A later-invalidated contract must not remain a silent commercial win.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

ALTER TABLE public.pncp_supplier_contracts
    ADD COLUMN IF NOT EXISTS lifecycle_event_last TEXT,
    ADD COLUMN IF NOT EXISTS lifecycle_event_at DATE;

CREATE TABLE IF NOT EXISTS public.contract_terms (
    term_id         TEXT PRIMARY KEY,
    contrato_id     TEXT NOT NULL REFERENCES public.pncp_supplier_contracts(contrato_id) ON DELETE CASCADE,
    tipo_termo      TEXT NOT NULL CHECK (tipo_termo IN (
        'ADITIVO', 'RETIFICACAO', 'RESCISAO', 'REVOGACAO', 'ANULACAO', 'OUTRO'
    )),
    numero_termo    TEXT,
    data_assinatura DATE,
    valor           NUMERIC(18,2),
    prazo_dias      INTEGER,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    rule_version    TEXT NOT NULL,
    payload_hash    TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_contract_terms_natural
    ON public.contract_terms (
        contrato_id,
        tipo_termo,
        COALESCE(numero_termo, ''),
        COALESCE(data_assinatura, DATE 'epoch')
    );

CREATE INDEX IF NOT EXISTS idx_contract_terms_contrato
    ON public.contract_terms (contrato_id, data_assinatura DESC);

COMMENT ON TABLE public.contract_terms IS
    'Official PNCP contract terms (#548). Aditivo ≠ retificação ≠ rescisão/revogação/anulação.';
COMMENT ON COLUMN public.pncp_supplier_contracts.lifecycle_event_last IS
    'Latest official term type. REVOGACAO/ANULACAO/RESCISAO exclude commercial actionability. #548.';

CREATE OR REPLACE FUNCTION public.apply_contract_terms(p_records JSONB)
RETURNS TABLE (action TEXT, term_id TEXT)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH input AS (
        SELECT DISTINCT ON (rec->>'term_id')
            rec->>'term_id' AS in_term_id,
            rec->>'contrato_id' AS contrato_id,
            rec->>'tipo_termo' AS tipo_termo,
            NULLIF(rec->>'numero_termo', '') AS numero_termo,
            NULLIF(rec->>'data_assinatura', '')::DATE AS data_assinatura,
            NULLIF(rec->>'valor', '')::NUMERIC AS valor,
            NULLIF(rec->>'prazo_dias', '')::INTEGER AS prazo_dias,
            COALESCE(NULLIF(rec->>'rule_version', ''), 'pncp-contract-terms-v1') AS rule_version,
            NULLIF(rec->>'payload_hash', '') AS payload_hash
        FROM jsonb_array_elements(p_records) AS rec
        WHERE COALESCE(rec->>'term_id', '') <> ''
          AND COALESCE(rec->>'contrato_id', '') <> ''
        ORDER BY rec->>'term_id'
    ), upserted AS (
        INSERT INTO public.contract_terms AS target (
            term_id, contrato_id, tipo_termo, numero_termo, data_assinatura,
            valor, prazo_dias, first_seen_at, last_seen_at, rule_version, payload_hash
        )
        SELECT
            input.in_term_id, input.contrato_id, input.tipo_termo, input.numero_termo,
            input.data_assinatura, input.valor, input.prazo_dias, NOW(), NOW(),
            input.rule_version, input.payload_hash
        FROM input
        JOIN public.pncp_supplier_contracts contract
            ON contract.contrato_id = input.contrato_id
        ON CONFLICT ON CONSTRAINT contract_terms_pkey DO UPDATE SET
            last_seen_at = NOW(),
            valor = COALESCE(EXCLUDED.valor, target.valor),
            prazo_dias = COALESCE(EXCLUDED.prazo_dias, target.prazo_dias)
        RETURNING target.term_id, target.contrato_id, target.tipo_termo, target.data_assinatura, (xmax = 0) AS is_insert
    )
    SELECT CASE WHEN upserted.is_insert THEN 'inserted' ELSE 'updated' END,
           upserted.term_id
    FROM upserted;

    -- Terminal events stay sticky unless a newer *dated* term exists.
    -- An undated later ADITIVO must not clobber REVOGACAO/ANULACAO/RESCISAO.
    UPDATE public.pncp_supplier_contracts AS contract
    SET lifecycle_event_last = term.tipo_termo,
        lifecycle_event_at = term.data_assinatura
    FROM public.contract_terms AS term
    WHERE contract.contrato_id = term.contrato_id
      AND term.term_id IN (
          SELECT rec->>'term_id' FROM jsonb_array_elements(p_records) rec
      )
      AND (
          (
              term.data_assinatura IS NOT NULL
              AND (
                  contract.lifecycle_event_at IS NULL
                  OR term.data_assinatura >= contract.lifecycle_event_at
              )
          )
          OR (
              term.data_assinatura IS NULL
              AND COALESCE(contract.lifecycle_event_last, '') NOT IN (
                  'REVOGACAO', 'ANULACAO', 'RESCISAO'
              )
          )
      );
END;
$$;

COMMIT;
