-- Fix: empty-string numero_processo/numero_edital collide on partial unique index
-- uq_oi_orgao_processo_edital (requires all three NOT NULL). NULLIF empty → NULL
-- so records without process number do not share a synthetic unique key.
-- Also COALESCE content_hash conflicts are out of scope here; identity remains
-- numero_controle_pncp.

CREATE OR REPLACE FUNCTION upsert_qw01_pncp_opportunities(batch JSONB)
RETURNS TABLE(action TEXT, record_id BIGINT, result_content_hash TEXT)
LANGUAGE plpgsql
AS $$
DECLARE
    rec JSONB;
BEGIN
    FOR rec IN SELECT * FROM jsonb_array_elements(batch)
    LOOP
        IF COALESCE(rec->>'numero_controle_pncp', '') = '' THEN
            RAISE EXCEPTION 'QW-01 PNCP record missing numero_controle_pncp';
        END IF;

        INSERT INTO opportunity_intel (
            source, source_id, source_url, content_hash, numero_controle_pncp,
            crawl_batch_id, run_id, orgao_cnpj, orgao_nome, ente_federativo,
            uf, municipio, codigo_ibge, numero_processo, numero_edital,
            modalidade, modalidade_id, objeto, categoria, valor_estimado,
            valor_semantica, data_publicacao, data_abertura, data_encerramento,
            status_fonte, status_canonico, status_motivo, status_data,
            link_edital, link_anexos, proveniencia, metadata
        ) VALUES (
            'pncp', rec->>'source_id', rec->>'source_url', rec->>'content_hash',
            rec->>'numero_controle_pncp', rec->>'crawl_batch_id', (rec->>'run_id')::BIGINT,
            rec->>'orgao_cnpj', rec->>'orgao_nome', rec->>'ente_federativo',
            -- Never impute UF=SC: blank/missing stays NULL (aligns with transformer).
            NULLIF(BTRIM(COALESCE(rec->>'uf', '')), ''), rec->>'municipio', rec->>'codigo_ibge',
            NULLIF(BTRIM(rec->>'numero_processo'), ''),
            NULLIF(BTRIM(rec->>'numero_edital'), ''),
            rec->>'modalidade',
            (rec->>'modalidade_id')::INTEGER, rec->>'objeto', rec->>'categoria',
            (rec->>'valor_estimado')::NUMERIC, rec->>'valor_semantica',
            (rec->>'data_publicacao')::TIMESTAMPTZ, (rec->>'data_abertura')::TIMESTAMPTZ,
            (rec->>'data_encerramento')::TIMESTAMPTZ, rec->>'status_fonte',
            COALESCE(rec->>'status_canonico', 'unknown'), rec->>'status_motivo',
            (rec->>'status_data')::TIMESTAMPTZ, rec->>'link_edital',
            CASE WHEN jsonb_typeof(rec->'link_anexos') = 'array'
                THEN ARRAY(SELECT * FROM jsonb_array_elements_text(rec->'link_anexos')) END,
            COALESCE(rec->'proveniencia', '{}'::jsonb), COALESCE(rec->'metadata', '{}'::jsonb)
        )
        ON CONFLICT (numero_controle_pncp)
            WHERE numero_controle_pncp IS NOT NULL AND is_active = TRUE
        DO UPDATE SET
            source_url = COALESCE(EXCLUDED.source_url, opportunity_intel.source_url),
            content_hash = EXCLUDED.content_hash,
            crawl_batch_id = EXCLUDED.crawl_batch_id,
            run_id = EXCLUDED.run_id,
            last_seen_at = NOW(),
            orgao_cnpj = COALESCE(EXCLUDED.orgao_cnpj, opportunity_intel.orgao_cnpj),
            orgao_nome = COALESCE(EXCLUDED.orgao_nome, opportunity_intel.orgao_nome),
            uf = COALESCE(NULLIF(BTRIM(EXCLUDED.uf), ''), opportunity_intel.uf),
            municipio = COALESCE(EXCLUDED.municipio, opportunity_intel.municipio),
            codigo_ibge = COALESCE(EXCLUDED.codigo_ibge, opportunity_intel.codigo_ibge),
            numero_processo = COALESCE(
                NULLIF(BTRIM(EXCLUDED.numero_processo), ''),
                opportunity_intel.numero_processo
            ),
            numero_edital = COALESCE(
                NULLIF(BTRIM(EXCLUDED.numero_edital), ''),
                opportunity_intel.numero_edital
            ),
            modalidade = COALESCE(EXCLUDED.modalidade, opportunity_intel.modalidade),
            modalidade_id = COALESCE(EXCLUDED.modalidade_id, opportunity_intel.modalidade_id),
            objeto = EXCLUDED.objeto,
            categoria = COALESCE(EXCLUDED.categoria, opportunity_intel.categoria),
            valor_estimado = COALESCE(EXCLUDED.valor_estimado, opportunity_intel.valor_estimado),
            valor_semantica = COALESCE(EXCLUDED.valor_semantica, opportunity_intel.valor_semantica),
            data_publicacao = COALESCE(EXCLUDED.data_publicacao, opportunity_intel.data_publicacao),
            data_abertura = COALESCE(EXCLUDED.data_abertura, opportunity_intel.data_abertura),
            data_encerramento = COALESCE(EXCLUDED.data_encerramento, opportunity_intel.data_encerramento),
            status_fonte = EXCLUDED.status_fonte,
            status_canonico = EXCLUDED.status_canonico,
            status_motivo = EXCLUDED.status_motivo,
            status_data = EXCLUDED.status_data,
            link_edital = COALESCE(EXCLUDED.link_edital, opportunity_intel.link_edital),
            link_anexos = COALESCE(EXCLUDED.link_anexos, opportunity_intel.link_anexos),
            proveniencia = EXCLUDED.proveniencia,
            metadata = EXCLUDED.metadata,
            is_active = TRUE
        RETURNING
            CASE WHEN xmax = 0 THEN 'insert' ELSE 'update' END,
            id,
            content_hash
        INTO action, record_id, result_content_hash;
        RETURN NEXT;
    END LOOP;
END;
$$;

-- Normalize legacy empty strings so they no longer participate in the partial unique index.
UPDATE opportunity_intel
SET numero_processo = NULL
WHERE numero_processo IS NOT NULL AND BTRIM(numero_processo) = '';

UPDATE opportunity_intel
SET numero_edital = NULL
WHERE numero_edital IS NOT NULL AND BTRIM(numero_edital) = '';
