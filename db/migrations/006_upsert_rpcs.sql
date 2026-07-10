-- Migration 006: Upsert RPCs
-- Batch upsert with dedup by content_hash

-- Batch upsert for bids (multi-source)
CREATE OR REPLACE FUNCTION upsert_pncp_raw_bids(p_records JSONB)
RETURNS TABLE (
    action      TEXT,
    pncp_id     TEXT,
    content_hash TEXT
) LANGUAGE plpgsql AS $$
DECLARE
    rec JSONB;
BEGIN
    FOR rec IN SELECT * FROM jsonb_array_elements(p_records)
    LOOP
        -- Generate tsvector from objeto_compra for Portuguese FTS
        rec := rec || jsonb_build_object(
            'tsv', to_tsvector('portuguese', COALESCE(rec->>'objeto_compra', ''))
        );

        INSERT INTO pncp_raw_bids (
            pncp_id, objeto_compra, valor_total_estimado,
            modalidade_id, modalidade_nome, esfera_id,
            uf, municipio, codigo_municipio_ibge,
            orgao_razao_social, orgao_cnpj,
            data_publicacao, data_abertura, data_encerramento,
            link_pncp, content_hash, tsv,
            source, source_id
        ) VALUES (
            rec->>'pncp_id',
            rec->>'objeto_compra',
            (rec->>'valor_total_estimado')::NUMERIC,
            (rec->>'modalidade_id')::INT,
            rec->>'modalidade_nome',
            (rec->>'esfera_id')::INT,
            rec->>'uf',
            rec->>'municipio',
            rec->>'codigo_municipio_ibge',
            rec->>'orgao_razao_social',
            rec->>'orgao_cnpj',
            (rec->>'data_publicacao')::DATE,
            (rec->>'data_abertura')::DATE,
            (rec->>'data_encerramento')::DATE,
            rec->>'link_pncp',
            rec->>'content_hash',
            to_tsvector('portuguese', COALESCE(rec->>'objeto_compra', '')),
            COALESCE(rec->>'source', 'pncp'),
            rec->>'source_id'
        )
        ON CONFLICT (content_hash) DO NOTHING;

        IF FOUND THEN
            RETURN QUERY SELECT 'inserted'::TEXT, rec->>'pncp_id', rec->>'content_hash';
        ELSE
            RETURN QUERY SELECT 'skipped'::TEXT, rec->>'pncp_id', rec->>'content_hash';
        END IF;
    END LOOP;
END;
$$;

-- Batch upsert for supplier contracts
CREATE OR REPLACE FUNCTION upsert_pncp_supplier_contracts(p_records JSONB)
RETURNS TABLE (
    action      TEXT,
    contrato_id TEXT
) LANGUAGE plpgsql AS $$
DECLARE
    rec JSONB;
BEGIN
    FOR rec IN SELECT * FROM jsonb_array_elements(p_records)
    LOOP
        INSERT INTO pncp_supplier_contracts (
            contrato_id, orgao_cnpj, orgao_nome,
            fornecedor_cnpj, fornecedor_nome,
            objeto_contrato, valor_total,
            data_inicio, data_fim, data_publicacao,
            uf, municipio, source, source_id
        ) VALUES (
            rec->>'contrato_id',
            rec->>'orgao_cnpj',
            rec->>'orgao_nome',
            rec->>'fornecedor_cnpj',
            rec->>'fornecedor_nome',
            rec->>'objeto_contrato',
            (rec->>'valor_total')::NUMERIC,
            (rec->>'data_inicio')::DATE,
            (rec->>'data_fim')::DATE,
            (rec->>'data_publicacao')::DATE,
            rec->>'uf',
            rec->>'municipio',
            COALESCE(rec->>'source', 'pncp'),
            rec->>'source_id'
        )
        ON CONFLICT (contrato_id) DO NOTHING;

        IF FOUND THEN
            RETURN QUERY SELECT 'inserted'::TEXT, rec->>'contrato_id';
        ELSE
            RETURN QUERY SELECT 'skipped'::TEXT, rec->>'contrato_id';
        END IF;
    END LOOP;
END;
$$;
