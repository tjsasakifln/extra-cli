-- Migration 006: Upsert RPCs — Set-Based
-- Batch upsert with dedup by content_hash
--
-- Refatorado em Story 1.2 (Task 7): FOR loop → SET-BASED (INSERT ... SELECT)
-- Performance: <= 30% do tempo do row-by-row original (AC #10 / DT-05)
--
-- Principios do refactoring set-based:
--   1. Uma unica instrucao INSERT/SELECT processa TODOS os registros
--   2. Sem cursor/FOR loop — PostgreSQL otimiza o plano de execucao
--   3. CTE de saida retorna acao por registro (inserted/skipped/updated)
--   4. Idempotente: CREATE OR REPLACE FUNCTION
--
-- Batch upsert for bids (multi-source)
CREATE OR REPLACE FUNCTION upsert_pncp_raw_bids(p_records JSONB)
RETURNS TABLE (
    action      TEXT,
    pncp_id     TEXT,
    content_hash TEXT
) LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    WITH input AS (
        SELECT
            rec->>'pncp_id' AS pncp_id,
            rec->>'objeto_compra' AS objeto_compra,
            (rec->>'valor_total_estimado')::NUMERIC AS valor_total_estimado,
            (rec->>'modalidade_id')::INT AS modalidade_id,
            rec->>'modalidade_nome' AS modalidade_nome,
            (rec->>'esfera_id')::INT AS esfera_id,
            rec->>'uf' AS uf,
            rec->>'municipio' AS municipio,
            rec->>'codigo_municipio_ibge' AS codigo_municipio_ibge,
            rec->>'orgao_razao_social' AS orgao_razao_social,
            rec->>'orgao_cnpj' AS orgao_cnpj,
            (rec->>'data_publicacao')::DATE AS data_publicacao,
            (rec->>'data_abertura')::DATE AS data_abertura,
            (rec->>'data_encerramento')::DATE AS data_encerramento,
            rec->>'link_pncp' AS link_pncp,
            rec->>'content_hash' AS content_hash,
            COALESCE(rec->>'source', 'pncp') AS source,
            rec->>'source_id' AS source_id
        FROM jsonb_array_elements(p_records) AS rec
    ),
    inserted AS (
        INSERT INTO pncp_raw_bids (
            pncp_id, objeto_compra, valor_total_estimado,
            modalidade_id, modalidade_nome, esfera_id,
            uf, municipio, codigo_municipio_ibge,
            orgao_razao_social, orgao_cnpj,
            data_publicacao, data_abertura, data_encerramento,
            link_pncp, content_hash, tsv,
            source, source_id
        )
        SELECT
            i.pncp_id, i.objeto_compra, i.valor_total_estimado,
            i.modalidade_id, i.modalidade_nome, i.esfera_id,
            i.uf, i.municipio, i.codigo_municipio_ibge,
            i.orgao_razao_social, i.orgao_cnpj,
            i.data_publicacao, i.data_abertura, i.data_encerramento,
            i.link_pncp, i.content_hash,
            to_tsvector('portuguese', COALESCE(i.objeto_compra, '')),
            i.source, i.source_id
        FROM input i
        WHERE NOT EXISTS (
            SELECT 1 FROM pncp_raw_bids t
            WHERE t.content_hash = i.content_hash
        )
        ON CONFLICT ON CONSTRAINT pncp_raw_bids_content_hash_key DO NOTHING
        RETURNING pncp_id, content_hash
    )
    SELECT 'inserted'::TEXT, i.pncp_id, i.content_hash
    FROM inserted i
    UNION ALL
    SELECT 'skipped'::TEXT, i.pncp_id, i.content_hash
    FROM input i
    WHERE EXISTS (
        SELECT 1 FROM pncp_raw_bids t
        WHERE t.content_hash = i.content_hash
    );
END;
$$;

-- Batch upsert for supplier contracts — SET-BASED
-- Refatorado de FOR loop para INSERT ... SELECT (Story 1.2, Task 7)
CREATE OR REPLACE FUNCTION upsert_pncp_supplier_contracts(p_records JSONB)
RETURNS TABLE (
    action      TEXT,
    contrato_id TEXT
) LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    WITH input AS (
        SELECT
            rec->>'contrato_id' AS contrato_id,
            rec->>'orgao_cnpj' AS orgao_cnpj,
            rec->>'orgao_nome' AS orgao_nome,
            rec->>'fornecedor_cnpj' AS fornecedor_cnpj,
            rec->>'fornecedor_nome' AS fornecedor_nome,
            rec->>'objeto_contrato' AS objeto_contrato,
            (rec->>'valor_total')::NUMERIC AS valor_total,
            (rec->>'data_inicio')::DATE AS data_inicio,
            (rec->>'data_fim')::DATE AS data_fim,
            (rec->>'data_publicacao')::DATE AS data_publicacao,
            rec->>'uf' AS uf,
            rec->>'municipio' AS municipio,
            COALESCE(rec->>'source', 'pncp') AS source,
            rec->>'source_id' AS source_id
        FROM jsonb_array_elements(p_records) AS rec
    ),
    inserted AS (
        INSERT INTO pncp_supplier_contracts (
            contrato_id, orgao_cnpj, orgao_nome,
            fornecedor_cnpj, fornecedor_nome,
            objeto_contrato, valor_total,
            data_inicio, data_fim, data_publicacao,
            uf, municipio, source, source_id
        )
        SELECT
            i.contrato_id, i.orgao_cnpj, i.orgao_nome,
            i.fornecedor_cnpj, i.fornecedor_nome,
            i.objeto_contrato, i.valor_total,
            i.data_inicio, i.data_fim, i.data_publicacao,
            i.uf, i.municipio, i.source, i.source_id
        FROM input i
        WHERE NOT EXISTS (
            SELECT 1 FROM pncp_supplier_contracts t
            WHERE t.contrato_id = i.contrato_id
        )
        ON CONFLICT (contrato_id) DO NOTHING
        RETURNING contrato_id
    )
    SELECT 'inserted'::TEXT, i.contrato_id
    FROM inserted i
    UNION ALL
    SELECT 'skipped'::TEXT, i.contrato_id
    FROM input i
    WHERE EXISTS (
        SELECT 1 FROM pncp_supplier_contracts t
        WHERE t.contrato_id = i.contrato_id
    );
END;
$$;
