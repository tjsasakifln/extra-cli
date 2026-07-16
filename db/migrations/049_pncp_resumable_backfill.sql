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

ALTER TABLE public.pncp_raw_bids
    ALTER COLUMN esfera_id TYPE TEXT USING esfera_id::TEXT,
    ALTER COLUMN data_publicacao TYPE TIMESTAMPTZ USING data_publicacao::TIMESTAMPTZ,
    ALTER COLUMN data_abertura TYPE TIMESTAMPTZ USING data_abertura::TIMESTAMPTZ,
    ALTER COLUMN data_encerramento TYPE TIMESTAMPTZ USING data_encerramento::TIMESTAMPTZ;

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
