-- Fix upsert_pncp_raw_bids ambiguous RETURNING / OUT parameter clash.
-- Compatible with minimal pncp_raw_bids columns present on local test DBs
-- (see db/migrations/001_pncp_raw_bids.sql). Full-column form lives in 049+;
-- this migration restores a working count-based RPC that monitor.py can call.

BEGIN;

DROP FUNCTION IF EXISTS public.upsert_pncp_raw_bids(JSONB);

CREATE FUNCTION public.upsert_pncp_raw_bids(p_records JSONB)
RETURNS TABLE (inserted INTEGER, updated INTEGER, unchanged INTEGER)
LANGUAGE plpgsql
SET search_path TO public
AS $$
DECLARE
    v_total INTEGER := 0;
    v_inserted INTEGER := 0;
    v_updated INTEGER := 0;
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
            rec->>'objeto_compra' AS objeto_compra,
            NULLIF(rec->>'valor_total_estimado', '')::NUMERIC AS valor_total_estimado,
            NULLIF(rec->>'modalidade_id', '')::INTEGER AS modalidade_id,
            rec->>'modalidade_nome' AS modalidade_nome,
            NULLIF(rec->>'esfera_id', '')::INTEGER AS esfera_id,
            rec->>'uf' AS uf,
            rec->>'municipio' AS municipio,
            rec->>'codigo_municipio_ibge' AS codigo_municipio_ibge,
            rec->>'orgao_razao_social' AS orgao_razao_social,
            rec->>'orgao_cnpj' AS orgao_cnpj,
            NULLIF(rec->>'data_publicacao', '')::DATE AS data_publicacao,
            NULLIF(rec->>'data_abertura', '')::DATE AS data_abertura,
            NULLIF(rec->>'data_encerramento', '')::DATE AS data_encerramento,
            rec->>'link_pncp' AS link_pncp,
            rec->>'content_hash' AS content_hash,
            COALESCE(rec->>'source', 'pncp') AS source,
            rec->>'source_id' AS source_id
        FROM jsonb_array_elements(p_records) WITH ORDINALITY AS item(rec, ordinal)
        WHERE NULLIF(rec->>'pncp_id', '') IS NOT NULL
        ORDER BY rec->>'pncp_id', ordinal DESC
    ),
    changed AS (
        INSERT INTO public.pncp_raw_bids (
            pncp_id, objeto_compra, valor_total_estimado,
            modalidade_id, modalidade_nome, esfera_id,
            uf, municipio, codigo_municipio_ibge,
            orgao_razao_social, orgao_cnpj,
            data_publicacao, data_abertura, data_encerramento,
            link_pncp, content_hash, tsv, source, source_id, updated_at
        )
        SELECT
            s.pncp_id,
            s.objeto_compra,
            s.valor_total_estimado,
            s.modalidade_id,
            s.modalidade_nome,
            s.esfera_id,
            s.uf,
            s.municipio,
            s.codigo_municipio_ibge,
            s.orgao_razao_social,
            s.orgao_cnpj,
            s.data_publicacao,
            s.data_abertura,
            s.data_encerramento,
            s.link_pncp,
            s.content_hash,
            to_tsvector('portuguese', COALESCE(s.objeto_compra, '')),
            s.source,
            s.source_id,
            now()
        FROM src s
        ON CONFLICT (pncp_id) DO UPDATE SET
            objeto_compra = EXCLUDED.objeto_compra,
            valor_total_estimado = EXCLUDED.valor_total_estimado,
            modalidade_id = EXCLUDED.modalidade_id,
            modalidade_nome = EXCLUDED.modalidade_nome,
            esfera_id = EXCLUDED.esfera_id,
            uf = EXCLUDED.uf,
            municipio = EXCLUDED.municipio,
            codigo_municipio_ibge = EXCLUDED.codigo_municipio_ibge,
            orgao_razao_social = EXCLUDED.orgao_razao_social,
            orgao_cnpj = EXCLUDED.orgao_cnpj,
            data_publicacao = EXCLUDED.data_publicacao,
            data_abertura = EXCLUDED.data_abertura,
            data_encerramento = EXCLUDED.data_encerramento,
            link_pncp = EXCLUDED.link_pncp,
            content_hash = EXCLUDED.content_hash,
            tsv = EXCLUDED.tsv,
            source = EXCLUDED.source,
            source_id = EXCLUDED.source_id,
            updated_at = now()
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
