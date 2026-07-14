BEGIN;

ALTER TABLE public.pncp_raw_bids
    ADD COLUMN IF NOT EXISTS situacao_compra TEXT,
    ADD COLUMN IF NOT EXISTS unidade_nome TEXT,
    ADD COLUMN IF NOT EXISTS link_sistema_origem TEXT,
    ADD COLUMN IF NOT EXISTS crawl_batch_id TEXT,
    ADD COLUMN IF NOT EXISTS numero_controle_pncp TEXT,
    ADD COLUMN IF NOT EXISTS ano_compra INTEGER,
    ADD COLUMN IF NOT EXISTS sequencial_compra INTEGER,
    ADD COLUMN IF NOT EXISTS informacao_complementar TEXT,
    ADD COLUMN IF NOT EXISTS source_id TEXT,
    ADD COLUMN IF NOT EXISTS synthetic_id BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS synthetic_id_reason TEXT;

UPDATE public.pncp_raw_bids
SET numero_controle_pncp = COALESCE(numero_controle_pncp, pncp_id)
WHERE numero_controle_pncp IS NULL;

CREATE INDEX IF NOT EXISTS idx_bids_numero_controle_pncp ON public.pncp_raw_bids (numero_controle_pncp);
CREATE INDEX IF NOT EXISTS idx_bids_ano_sequencial ON public.pncp_raw_bids (ano_compra, sequencial_compra);
CREATE INDEX IF NOT EXISTS idx_bids_source_id ON public.pncp_raw_bids (source_id);

CREATE TABLE IF NOT EXISTS public.sc_municipalities (
    codigo_ibge TEXT PRIMARY KEY,
    municipio TEXT NOT NULL,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    source TEXT NOT NULL DEFAULT 'sc_public_entities_seed',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO public.sc_municipalities (codigo_ibge, municipio, latitude, longitude, source)
SELECT DISTINCT ON (codigo_ibge)
    e.codigo_ibge,
    e.municipio,
    e.latitude,
    e.longitude,
    'sc_public_entities_seed'
FROM public.sc_public_entities e
WHERE e.codigo_ibge IS NOT NULL
  AND e.codigo_ibge <> ''
  AND e.municipio IS NOT NULL
ORDER BY e.codigo_ibge, e.raio_200km DESC, e.id
ON CONFLICT (codigo_ibge) DO UPDATE
SET municipio = EXCLUDED.municipio,
    latitude = COALESCE(public.sc_municipalities.latitude, EXCLUDED.latitude),
    longitude = COALESCE(public.sc_municipalities.longitude, EXCLUDED.longitude),
    updated_at = NOW();

CREATE TABLE IF NOT EXISTS public.pncp_enrichment_cache (
    pncp_id TEXT PRIMARY KEY REFERENCES public.pncp_raw_bids(pncp_id) ON DELETE CASCADE,
    detail_payload JSONB,
    items_payload JSONB,
    documents_payload JSONB,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.engineering_opportunities (
    id BIGSERIAL PRIMARY KEY,
    pncp_id TEXT NOT NULL UNIQUE REFERENCES public.pncp_raw_bids(pncp_id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    source_id TEXT,
    objeto_compra TEXT,
    orgao_cnpj TEXT,
    orgao_razao_social TEXT,
    codigo_municipio_ibge TEXT,
    municipio TEXT,
    uf TEXT,
    modalidade_id INTEGER,
    modalidade_nome TEXT,
    valor_total_estimado NUMERIC(18,2),
    data_publicacao TIMESTAMPTZ,
    data_abertura TIMESTAMPTZ,
    data_encerramento TIMESTAMPTZ,
    link_pncp TEXT,
    link_sistema_origem TEXT,
    is_engineering BOOLEAN NOT NULL DEFAULT FALSE,
    engineering_score INTEGER NOT NULL DEFAULT 0,
    engineering_confidence TEXT,
    engineering_categories TEXT[] NOT NULL DEFAULT '{}',
    classification_reasons JSONB NOT NULL DEFAULT '{}'::jsonb,
    classifier_version TEXT,
    exclusion_reason TEXT,
    distance_from_florianopolis_km DOUBLE PRECISION,
    within_200km BOOLEAN NOT NULL DEFAULT FALSE,
    geographic_priority TEXT,
    location_confidence TEXT,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    content_hash TEXT
);

CREATE INDEX IF NOT EXISTS idx_eng_op_is_engineering ON public.engineering_opportunities (is_engineering);
CREATE INDEX IF NOT EXISTS idx_eng_op_engineering_score ON public.engineering_opportunities (engineering_score DESC);
CREATE INDEX IF NOT EXISTS idx_eng_op_within_200km ON public.engineering_opportunities (within_200km);
CREATE INDEX IF NOT EXISTS idx_eng_op_ibge ON public.engineering_opportunities (codigo_municipio_ibge);
CREATE INDEX IF NOT EXISTS idx_eng_op_orgao_cnpj ON public.engineering_opportunities (orgao_cnpj);
CREATE INDEX IF NOT EXISTS idx_eng_op_data_publicacao ON public.engineering_opportunities (data_publicacao DESC);
CREATE INDEX IF NOT EXISTS idx_eng_op_data_encerramento ON public.engineering_opportunities (data_encerramento DESC);
CREATE INDEX IF NOT EXISTS idx_eng_op_modalidade_id ON public.engineering_opportunities (modalidade_id);

COMMENT ON TABLE public.sc_municipalities IS
    'Referencia municipal usada na geolocalizacao do pipeline PNCP. Origem inicial: distinct de sc_public_entities seed.';

COMMENT ON TABLE public.engineering_opportunities IS
    'Camada derivada com classificacao de engenharia civil, geografia SC e links separados do PNCP.';

-- B2G-FIX-04: DROP old signature (006 returns TABLE(action,pncp_id,content_hash);
-- 023 returns TABLE(inserted,updated,unchanged)). CREATE OR REPLACE cannot change return type.
DROP FUNCTION IF EXISTS public.upsert_pncp_raw_bids(JSONB);
CREATE OR REPLACE FUNCTION public.upsert_pncp_raw_bids(p_records JSONB)
RETURNS TABLE (inserted INTEGER, updated INTEGER, unchanged INTEGER)
LANGUAGE plpgsql
SET search_path TO public
AS $$
DECLARE
    v_total     INT;
    v_inserted  INT;
    v_updated   INT;
BEGIN
    IF p_records IS NULL OR jsonb_array_length(p_records) = 0 THEN
        RETURN QUERY SELECT 0, 0, 0;
        RETURN;
    END IF;

    v_total := jsonb_array_length(p_records);

    WITH src AS (
        SELECT
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
            COALESCE(NULLIF(rec->>'is_active', '')::BOOLEAN, TRUE) AS is_active
        FROM jsonb_array_elements(p_records) AS rec
    ),
    upserted AS (
        INSERT INTO public.pncp_raw_bids (
            pncp_id, numero_controle_pncp, objeto_compra, informacao_complementar,
            valor_total_estimado, modalidade_id, modalidade_nome, situacao_compra,
            esfera_id, uf, municipio, codigo_municipio_ibge, orgao_razao_social,
            orgao_cnpj, unidade_nome, data_publicacao, data_abertura, data_encerramento,
            link_sistema_origem, link_pncp, content_hash, source, source_id,
            crawl_batch_id, ano_compra, sequencial_compra, synthetic_id,
            synthetic_id_reason, is_active
        )
        SELECT
            pncp_id, numero_controle_pncp, objeto_compra, informacao_complementar,
            valor_total_estimado, modalidade_id, modalidade_nome, situacao_compra,
            esfera_id, uf, municipio, codigo_municipio_ibge, orgao_razao_social,
            orgao_cnpj, unidade_nome, data_publicacao, data_abertura, data_encerramento,
            link_sistema_origem, link_pncp, content_hash, source, source_id,
            crawl_batch_id, ano_compra, sequencial_compra, synthetic_id,
            synthetic_id_reason, is_active
        FROM src
        ON CONFLICT (pncp_id) DO UPDATE
        SET
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
            is_active = EXCLUDED.is_active,
            updated_at = NOW()
        RETURNING (xmax = 0) AS was_inserted
    )
    SELECT
        COALESCE(SUM(CASE WHEN was_inserted THEN 1 ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN NOT was_inserted THEN 1 ELSE 0 END), 0)
    INTO v_inserted, v_updated
    FROM upserted;

    RETURN QUERY
    SELECT v_inserted, v_updated, GREATEST(0, v_total - v_inserted - v_updated);
END;
$$;

COMMIT;
