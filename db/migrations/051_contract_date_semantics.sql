-- ============================================================================
-- Migration 051: Contract date semantics (fix data_publicacao vs dataAssinatura)
-- ============================================================================
-- Problem: contracts_crawler mapped PNCP dataAssinatura → data_publicacao, so
-- historical / future signature dates appeared as "publication" inside a recent
-- crawl window. data_publicacao is LEGACY and must not be dropped.
--
-- This migration:
--   - Adds explicit date columns with clear semantics
--   - Backfills data_assinatura from historical data_publicacao
--   - Extends upsert_pncp_supplier_contracts to accept optional new fields
--     without breaking old callers (NULLIF / COALESCE, optional JSONB keys)
--   - On conflict: refresh last_seen_at; fill new date fields only when NULL
-- ============================================================================

-- 1) New columns (retrocompatible)
ALTER TABLE pncp_supplier_contracts
    ADD COLUMN IF NOT EXISTS data_assinatura DATE,
    ADD COLUMN IF NOT EXISTS data_publicacao_fonte DATE,
    ADD COLUMN IF NOT EXISTS data_atualizacao_fonte DATE,
    ADD COLUMN IF NOT EXISTS source_event_date DATE,
    ADD COLUMN IF NOT EXISTS source_date_semantics TEXT,
    ADD COLUMN IF NOT EXISTS first_seen_at TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS source_updated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS query_window_start DATE,
    ADD COLUMN IF NOT EXISTS query_window_end DATE;

COMMENT ON COLUMN pncp_supplier_contracts.data_assinatura IS
    'PNCP dataAssinatura (contract signature date). Not publication.';
COMMENT ON COLUMN pncp_supplier_contracts.data_publicacao_fonte IS
    'True publication date from source when available (dataPublicacaoPncp / dataPublicacao / dataPublicacaoContrato).';
COMMENT ON COLUMN pncp_supplier_contracts.data_atualizacao_fonte IS
    'Source last-update date when available (dataAtualizacao*).';
COMMENT ON COLUMN pncp_supplier_contracts.source_event_date IS
    'Best event date for the contract act: data_assinatura preferred, else data_publicacao_fonte.';
COMMENT ON COLUMN pncp_supplier_contracts.source_date_semantics IS
    'How dates were derived, e.g. dataAssinatura_as_event, dataPublicacaoPncp, dataPublicacao, unknown.';
COMMENT ON COLUMN pncp_supplier_contracts.data_publicacao IS
    'LEGACY mixed semantics. Historically held dataAssinatura. Prefer data_publicacao_fonte / data_assinatura.';
COMMENT ON COLUMN pncp_supplier_contracts.first_seen_at IS
    'First time this contrato_id was ingested by our pipeline.';
COMMENT ON COLUMN pncp_supplier_contracts.last_seen_at IS
    'Last time this contrato_id was seen in a crawl batch.';
COMMENT ON COLUMN pncp_supplier_contracts.source_updated_at IS
    'Optional timestamp from source indicating when the record was last updated upstream.';
COMMENT ON COLUMN pncp_supplier_contracts.query_window_start IS
    'Crawl query window start (dataInicial) that produced this observation, if known.';
COMMENT ON COLUMN pncp_supplier_contracts.query_window_end IS
    'Crawl query window end (dataFinal) that produced this observation, if known.';

-- 2) Backfill: historical data_publicacao actually stored assinatura
UPDATE pncp_supplier_contracts
SET data_assinatura = data_publicacao
WHERE data_assinatura IS NULL
  AND data_publicacao IS NOT NULL;

UPDATE pncp_supplier_contracts
SET source_event_date = COALESCE(data_assinatura, data_publicacao_fonte, data_publicacao)
WHERE source_event_date IS NULL
  AND COALESCE(data_assinatura, data_publicacao_fonte, data_publicacao) IS NOT NULL;

UPDATE pncp_supplier_contracts
SET source_date_semantics = 'dataAssinatura_as_event'
WHERE source_date_semantics IS NULL
  AND data_assinatura IS NOT NULL
  AND data_publicacao_fonte IS NULL;

UPDATE pncp_supplier_contracts
SET first_seen_at = COALESCE(first_seen_at, ingested_at, NOW())
WHERE first_seen_at IS NULL;

UPDATE pncp_supplier_contracts
SET last_seen_at = COALESCE(last_seen_at, ingested_at, NOW())
WHERE last_seen_at IS NULL;

-- 3) Upsert RPC: optional new fields, safe for old callers
CREATE OR REPLACE FUNCTION upsert_pncp_supplier_contracts(p_records JSONB)
RETURNS TABLE (
    action      TEXT,
    contrato_id TEXT
) LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    WITH input AS (
        SELECT DISTINCT ON ((rec->>'contrato_id'))
            rec->>'contrato_id'              AS in_contrato_id,
            rec->>'orgao_cnpj'               AS orgao_cnpj,
            rec->>'orgao_nome'               AS orgao_nome,
            rec->>'fornecedor_cnpj'          AS fornecedor_cnpj,
            rec->>'fornecedor_nome'          AS fornecedor_nome,
            rec->>'objeto_contrato'          AS objeto_contrato,
            NULLIF(rec->>'valor_total', '')::NUMERIC AS valor_total,
            NULLIF(rec->>'data_inicio', '')::DATE    AS data_inicio,
            NULLIF(rec->>'data_fim', '')::DATE       AS data_fim,
            NULLIF(rec->>'data_publicacao', '')::DATE AS data_publicacao,
            rec->>'uf'                       AS uf,
            rec->>'municipio'                AS municipio,
            COALESCE(rec->>'source', 'pncp') AS source,
            rec->>'source_id'                AS source_id,
            -- New optional date-semantics fields (NULL when absent / blank)
            NULLIF(rec->>'data_assinatura', '')::DATE AS data_assinatura,
            NULLIF(rec->>'data_publicacao_fonte', '')::DATE AS data_publicacao_fonte,
            NULLIF(rec->>'data_atualizacao_fonte', '')::DATE AS data_atualizacao_fonte,
            NULLIF(rec->>'source_event_date', '')::DATE AS source_event_date,
            NULLIF(rec->>'source_date_semantics', '') AS source_date_semantics,
            NULLIF(rec->>'source_updated_at', '')::TIMESTAMPTZ AS source_updated_at,
            NULLIF(rec->>'query_window_start', '')::DATE AS query_window_start,
            NULLIF(rec->>'query_window_end', '')::DATE AS query_window_end
        FROM jsonb_array_elements(p_records) AS rec
        WHERE COALESCE(rec->>'contrato_id', '') <> ''
        ORDER BY (rec->>'contrato_id')
    ),
    upserted AS (
        INSERT INTO pncp_supplier_contracts AS t (
            contrato_id, orgao_cnpj, orgao_nome,
            fornecedor_cnpj, fornecedor_nome,
            objeto_contrato, valor_total,
            data_inicio, data_fim, data_publicacao,
            uf, municipio, source, source_id,
            data_assinatura, data_publicacao_fonte, data_atualizacao_fonte,
            source_event_date, source_date_semantics,
            first_seen_at, last_seen_at, source_updated_at,
            query_window_start, query_window_end
        )
        SELECT
            i.in_contrato_id, i.orgao_cnpj, i.orgao_nome,
            i.fornecedor_cnpj, i.fornecedor_nome,
            i.objeto_contrato, i.valor_total,
            i.data_inicio, i.data_fim, i.data_publicacao,
            i.uf, i.municipio, i.source, i.source_id,
            i.data_assinatura, i.data_publicacao_fonte, i.data_atualizacao_fonte,
            i.source_event_date, i.source_date_semantics,
            NOW(), NOW(), i.source_updated_at,
            i.query_window_start, i.query_window_end
        FROM input i
        ON CONFLICT ON CONSTRAINT pncp_supplier_contracts_contrato_id_key DO UPDATE SET
            last_seen_at = NOW(),
            -- Fill new semantic date fields only when existing is NULL
            data_assinatura = COALESCE(t.data_assinatura, EXCLUDED.data_assinatura),
            data_publicacao_fonte = COALESCE(t.data_publicacao_fonte, EXCLUDED.data_publicacao_fonte),
            data_atualizacao_fonte = COALESCE(t.data_atualizacao_fonte, EXCLUDED.data_atualizacao_fonte),
            source_event_date = COALESCE(t.source_event_date, EXCLUDED.source_event_date),
            source_date_semantics = COALESCE(t.source_date_semantics, EXCLUDED.source_date_semantics),
            source_updated_at = COALESCE(t.source_updated_at, EXCLUDED.source_updated_at),
            query_window_start = COALESCE(t.query_window_start, EXCLUDED.query_window_start),
            query_window_end = COALESCE(t.query_window_end, EXCLUDED.query_window_end)
        RETURNING t.contrato_id, (xmax = 0) AS is_insert
    )
    SELECT
        CASE WHEN u.is_insert THEN 'inserted'::TEXT ELSE 'updated'::TEXT END,
        u.contrato_id
    FROM upserted u;
END;
$$;

COMMENT ON FUNCTION upsert_pncp_supplier_contracts(JSONB) IS
    'Batch upsert contracts by contrato_id. 051: date semantics columns + last_seen_at on conflict; fills null semantic dates only.';
