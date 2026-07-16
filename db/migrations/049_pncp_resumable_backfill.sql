-- Resumable, page-atomic PNCP backfill for a closed seven-day window.
-- The migration is intentionally limited to PNCP collection state,
-- provenance, raw payload retention, and idempotent upsert semantics.

BEGIN;

ALTER TABLE public.pncp_raw_bids
    ADD COLUMN IF NOT EXISTS numero_controle_pncp TEXT,
    ADD COLUMN IF NOT EXISTS informacao_complementar TEXT,
    ADD COLUMN IF NOT EXISTS situacao_compra TEXT,
    ADD COLUMN IF NOT EXISTS unidade_nome TEXT,
    ADD COLUMN IF NOT EXISTS link_sistema_origem TEXT,
    ADD COLUMN IF NOT EXISTS crawl_batch_id TEXT,
    ADD COLUMN IF NOT EXISTS ano_compra INTEGER,
    ADD COLUMN IF NOT EXISTS sequencial_compra INTEGER,
    ADD COLUMN IF NOT EXISTS synthetic_id BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS synthetic_id_reason TEXT,
    ADD COLUMN IF NOT EXISTS raw_payload JSONB;

-- Views that depend on pncp_raw_bids columns being type-altered must be
-- dropped first (PostgreSQL cannot ALTER TYPE while a view rule depends on
-- the column). Recreated immediately after the ALTER block.
DROP VIEW IF EXISTS public.v_open_opportunities_canonical CASCADE;
DROP VIEW IF EXISTS public.v_unmatched_bids CASCADE;
DROP VIEW IF EXISTS public.v_value_observations_canonical CASCADE;

-- Integer CHECK on esfera_id blocks ALTER to TEXT (text = integer has no operator).
ALTER TABLE public.pncp_raw_bids
    DROP CONSTRAINT IF EXISTS chk_pncp_raw_bids_esfera_id;

ALTER TABLE public.pncp_raw_bids
    ALTER COLUMN esfera_id TYPE TEXT USING esfera_id::TEXT,
    ALTER COLUMN data_publicacao TYPE TIMESTAMPTZ USING data_publicacao::TIMESTAMPTZ,
    ALTER COLUMN data_abertura TYPE TIMESTAMPTZ USING data_abertura::TIMESTAMPTZ,
    ALTER COLUMN data_encerramento TYPE TIMESTAMPTZ USING data_encerramento::TIMESTAMPTZ;

-- Recreate esfera check as text codes (legacy numeric spheres 1-4 as strings)
ALTER TABLE public.pncp_raw_bids
    ADD CONSTRAINT chk_pncp_raw_bids_esfera_id
    CHECK (
        esfera_id IS NULL
        OR esfera_id = ANY (ARRAY['1', '2', '3', '4']::text[])
    );

-- Recreate canonical views (same definitions as migrations 021d / 030)
CREATE OR REPLACE VIEW public.v_open_opportunities_canonical AS
SELECT
    b.pncp_id                AS bid_id,
    b.pncp_id                AS pncp_id,
    b.objeto_compra          AS objeto,
    b.valor_total_estimado   AS valor_estimado,
    b.modalidade_id,
    b.modalidade_nome        AS modalidade,
    b.esfera_id              AS esfera_id,
    b.uf,
    b.municipio,
    b.codigo_municipio_ibge  AS codigo_ibge,
    b.orgao_cnpj,
    b.orgao_razao_social     AS orgao_nome,
    b.data_publicacao,
    b.data_abertura,
    b.data_encerramento,
    b.link_pncp              AS link_edital,
    b.source,
    b.source_id,
    b.match_method,
    b.match_score,
    b.match_confidence,
    e.id                     AS matched_entity_id,
    e.razao_social           AS matched_entity_nome,
    e.raio_200km             AS within_200km,
    e.cnpj_8                 AS entity_cnpj_8
FROM public.pncp_raw_bids b
LEFT JOIN public.sc_public_entities e ON e.id = b.matched_entity_id
WHERE b.data_encerramento >= CURRENT_DATE
   OR (b.data_encerramento IS NULL AND b.data_publicacao >= CURRENT_DATE - INTERVAL '30 days');

CREATE OR REPLACE VIEW public.v_unmatched_bids AS
SELECT
    pncp_id,
    source,
    orgao_cnpj,
    orgao_razao_social,
    municipio,
    codigo_municipio_ibge,
    data_publicacao,
    match_method,
    match_score,
    match_confidence,
    ingested_at,
    CASE
        WHEN orgao_cnpj IS NOT NULL AND orgao_cnpj <> '' THEN 'has_cnpj'
        ELSE 'name_only'
    END AS match_opportunity,
    CASE
        WHEN data_publicacao >= (CURRENT_DATE - INTERVAL '90 days') THEN 'recent'
        ELSE 'historical'
    END AS recency
FROM public.pncp_raw_bids
WHERE matched_entity_id IS NULL
  AND (
        (orgao_cnpj IS NOT NULL AND orgao_cnpj <> '')
     OR (orgao_razao_social IS NOT NULL AND orgao_razao_social <> '')
  )
ORDER BY data_publicacao DESC NULLS LAST, ingested_at DESC;

CREATE OR REPLACE VIEW public.v_value_observations_canonical AS
SELECT
    'bid'::text AS observation_type,
    b.pncp_id AS source_id,
    b.orgao_cnpj,
    b.municipio,
    b.uf,
    b.modalidade_id,
    b.modalidade_nome AS modalidade,
    b.objeto_compra AS objeto,
    b.valor_total_estimado AS valor,
    b.data_publicacao,
    e.cnpj_8 AS entity_cnpj_8,
    e.raio_200km AS within_200km
FROM public.pncp_raw_bids b
LEFT JOIN public.sc_public_entities e ON e.id = b.matched_entity_id
WHERE b.valor_total_estimado IS NOT NULL AND b.valor_total_estimado > 0
UNION ALL
SELECT
    'contract'::text AS observation_type,
    c.contrato_id AS source_id,
    c.orgao_cnpj,
    c.municipio,
    c.uf,
    NULL::integer AS modalidade_id,
    NULL::text AS modalidade,
    c.objeto_contrato AS objeto,
    c.valor_total AS valor,
    c.data_publicacao,
    e.cnpj_8 AS entity_cnpj_8,
    e.raio_200km AS within_200km
FROM public.pncp_supplier_contracts c
LEFT JOIN public.sc_public_entities e ON e.cnpj_8 = LEFT(c.fornecedor_cnpj, 8)
WHERE c.valor_total IS NOT NULL AND c.valor_total > 0;

CREATE TABLE IF NOT EXISTS public.pncp_backfill_runs (
    run_id TEXT PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'pncp' CHECK (source = 'pncp'),
    uf TEXT NOT NULL DEFAULT 'SC' CHECK (uf = 'SC'),
    window_start DATE NOT NULL,
    window_end DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'interrupted', 'failed', 'completed')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    pages_expected INTEGER NOT NULL DEFAULT 0,
    data_pages_expected INTEGER NOT NULL DEFAULT 0,
    pages_completed INTEGER NOT NULL DEFAULT 0,
    records_fetched INTEGER NOT NULL DEFAULT 0,
    unique_records INTEGER NOT NULL DEFAULT 0,
    duplicate_records INTEGER NOT NULL DEFAULT 0,
    inserted INTEGER NOT NULL DEFAULT 0,
    updated INTEGER NOT NULL DEFAULT 0,
    unchanged INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    CHECK (window_end - window_start = 6)
);

CREATE INDEX IF NOT EXISTS idx_pncp_backfill_runs_window
    ON public.pncp_backfill_runs (window_start, window_end, started_at DESC);

CREATE TABLE IF NOT EXISTS public.pncp_backfill_pages (
    run_id TEXT NOT NULL REFERENCES public.pncp_backfill_runs(run_id) ON DELETE CASCADE,
    modalidade_id INTEGER NOT NULL,
    page_number INTEGER NOT NULL CHECK (page_number >= 1),
    source_total_records INTEGER NOT NULL CHECK (source_total_records >= 0),
    source_total_pages INTEGER NOT NULL CHECK (source_total_pages >= 0),
    records_fetched INTEGER NOT NULL CHECK (records_fetched >= 0),
    unique_records INTEGER NOT NULL CHECK (unique_records >= 0),
    duplicate_records INTEGER NOT NULL CHECK (duplicate_records >= 0),
    inserted INTEGER NOT NULL CHECK (inserted >= 0),
    updated INTEGER NOT NULL CHECK (updated >= 0),
    unchanged INTEGER NOT NULL CHECK (unchanged >= 0),
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (run_id, modalidade_id, page_number)
);

CREATE TABLE IF NOT EXISTS public.pncp_backfill_records (
    run_id TEXT NOT NULL REFERENCES public.pncp_backfill_runs(run_id) ON DELETE CASCADE,
    pncp_id TEXT NOT NULL REFERENCES public.pncp_raw_bids(pncp_id),
    source TEXT NOT NULL DEFAULT 'pncp' CHECK (source = 'pncp'),
    uf TEXT NOT NULL DEFAULT 'SC' CHECK (uf = 'SC'),
    window_start DATE NOT NULL,
    window_end DATE NOT NULL,
    modalidade_id INTEGER NOT NULL,
    page_number INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    raw_payload JSONB,
    collected_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (run_id, modalidade_id, page_number, pncp_id)
);

ALTER TABLE public.pncp_backfill_records
    ADD COLUMN IF NOT EXISTS raw_payload JSONB;

CREATE INDEX IF NOT EXISTS idx_pncp_backfill_records_window
    ON public.pncp_backfill_records (window_start, window_end, pncp_id);

DROP FUNCTION IF EXISTS public.upsert_pncp_raw_bids(JSONB);
CREATE FUNCTION public.upsert_pncp_raw_bids(p_records JSONB)
RETURNS TABLE (inserted INTEGER, updated INTEGER, unchanged INTEGER)
LANGUAGE plpgsql
SET search_path TO public
AS $$
DECLARE
    v_total INTEGER;
    v_inserted INTEGER;
    v_updated INTEGER;
BEGIN
    IF p_records IS NULL OR jsonb_typeof(p_records) <> 'array' THEN
        RAISE EXCEPTION 'p_records must be a JSON array';
    END IF;

    WITH src AS (
        SELECT DISTINCT ON (rec->>'pncp_id')
            rec->>'pncp_id' AS pncp_id
        FROM jsonb_array_elements(p_records) WITH ORDINALITY AS item(rec, ordinal)
        WHERE NULLIF(rec->>'pncp_id', '') IS NOT NULL
        ORDER BY rec->>'pncp_id', ordinal DESC
    )
    SELECT COUNT(*)::INTEGER INTO v_total FROM src;

    WITH src AS (
        SELECT DISTINCT ON (rec->>'pncp_id')
            rec->>'pncp_id' AS pncp_id,
            COALESCE(rec->>'numero_controle_pncp', rec->>'pncp_id') AS numero_controle_pncp,
            rec->>'objeto_compra' AS objeto_compra,
            rec->>'informacao_complementar' AS informacao_complementar,
            NULLIF(rec->>'valor_total_estimado', '')::NUMERIC AS valor_total_estimado,
            NULLIF(rec->>'modalidade_id', '')::INTEGER AS modalidade_id,
            rec->>'modalidade_nome' AS modalidade_nome,
            rec->>'situacao_compra' AS situacao_compra,
            rec->>'esfera_id' AS esfera_id,
            rec->>'uf' AS uf,
            rec->>'municipio' AS municipio,
            rec->>'codigo_municipio_ibge' AS codigo_municipio_ibge,
            rec->>'orgao_razao_social' AS orgao_razao_social,
            rec->>'orgao_cnpj' AS orgao_cnpj,
            rec->>'unidade_nome' AS unidade_nome,
            NULLIF(rec->>'data_publicacao', '')::TIMESTAMPTZ AS data_publicacao,
            NULLIF(rec->>'data_abertura', '')::TIMESTAMPTZ AS data_abertura,
            NULLIF(rec->>'data_encerramento', '')::TIMESTAMPTZ AS data_encerramento,
            rec->>'link_sistema_origem' AS link_sistema_origem,
            rec->>'link_pncp' AS link_pncp,
            rec->>'content_hash' AS content_hash,
            COALESCE(rec->>'source', 'pncp') AS source,
            rec->>'source_id' AS source_id,
            rec->>'crawl_batch_id' AS crawl_batch_id,
            NULLIF(rec->>'ano_compra', '')::INTEGER AS ano_compra,
            NULLIF(rec->>'sequencial_compra', '')::INTEGER AS sequencial_compra,
            COALESCE(NULLIF(rec->>'synthetic_id', '')::BOOLEAN, FALSE) AS synthetic_id,
            rec->>'synthetic_id_reason' AS synthetic_id_reason,
            rec->'raw_payload' AS raw_payload
        FROM jsonb_array_elements(p_records) WITH ORDINALITY AS item(rec, ordinal)
        WHERE NULLIF(rec->>'pncp_id', '') IS NOT NULL
        ORDER BY rec->>'pncp_id', ordinal DESC
    ),
    changed AS (
        INSERT INTO public.pncp_raw_bids (
            pncp_id, numero_controle_pncp, objeto_compra, informacao_complementar,
            valor_total_estimado, modalidade_id, modalidade_nome, situacao_compra,
            esfera_id, uf, municipio, codigo_municipio_ibge, orgao_razao_social,
            orgao_cnpj, unidade_nome, data_publicacao, data_abertura, data_encerramento,
            link_sistema_origem, link_pncp, content_hash, source, source_id,
            crawl_batch_id, ano_compra, sequencial_compra, synthetic_id,
            synthetic_id_reason, raw_payload
        )
        SELECT
            pncp_id, numero_controle_pncp, objeto_compra, informacao_complementar,
            valor_total_estimado, modalidade_id, modalidade_nome, situacao_compra,
            esfera_id, uf, municipio, codigo_municipio_ibge, orgao_razao_social,
            orgao_cnpj, unidade_nome, data_publicacao, data_abertura, data_encerramento,
            link_sistema_origem, link_pncp, content_hash, source, source_id,
            crawl_batch_id, ano_compra, sequencial_compra, synthetic_id,
            synthetic_id_reason, raw_payload
        FROM src
        ON CONFLICT (pncp_id) DO UPDATE SET
            numero_controle_pncp = EXCLUDED.numero_controle_pncp,
            objeto_compra = EXCLUDED.objeto_compra,
            informacao_complementar = EXCLUDED.informacao_complementar,
            valor_total_estimado = EXCLUDED.valor_total_estimado,
            modalidade_id = EXCLUDED.modalidade_id,
            modalidade_nome = EXCLUDED.modalidade_nome,
            situacao_compra = EXCLUDED.situacao_compra,
            esfera_id = EXCLUDED.esfera_id,
            uf = EXCLUDED.uf,
            municipio = EXCLUDED.municipio,
            codigo_municipio_ibge = EXCLUDED.codigo_municipio_ibge,
            orgao_razao_social = EXCLUDED.orgao_razao_social,
            orgao_cnpj = EXCLUDED.orgao_cnpj,
            unidade_nome = EXCLUDED.unidade_nome,
            data_publicacao = EXCLUDED.data_publicacao,
            data_abertura = EXCLUDED.data_abertura,
            data_encerramento = EXCLUDED.data_encerramento,
            link_sistema_origem = EXCLUDED.link_sistema_origem,
            link_pncp = EXCLUDED.link_pncp,
            content_hash = EXCLUDED.content_hash,
            source = EXCLUDED.source,
            source_id = EXCLUDED.source_id,
            crawl_batch_id = EXCLUDED.crawl_batch_id,
            ano_compra = EXCLUDED.ano_compra,
            sequencial_compra = EXCLUDED.sequencial_compra,
            synthetic_id = EXCLUDED.synthetic_id,
            synthetic_id_reason = EXCLUDED.synthetic_id_reason,
            raw_payload = EXCLUDED.raw_payload
        WHERE public.pncp_raw_bids.content_hash IS DISTINCT FROM EXCLUDED.content_hash
        RETURNING (xmax = 0) AS was_inserted
    )
    SELECT
        COUNT(*) FILTER (WHERE was_inserted)::INTEGER,
        COUNT(*) FILTER (WHERE NOT was_inserted)::INTEGER
    INTO v_inserted, v_updated
    FROM changed;

    RETURN QUERY SELECT
        COALESCE(v_inserted, 0),
        COALESCE(v_updated, 0),
        GREATEST(0, v_total - COALESCE(v_inserted, 0) - COALESCE(v_updated, 0));
END;
$$;

COMMIT;
