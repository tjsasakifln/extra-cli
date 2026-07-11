-- Migration 014: Fix HNSW vector similarity expression in search_datalake
-- Story TD-1.1: Otimizacao de Queries
-- Deficit TD-DB-11 (HIGH): A funcao search_datalake tem expressao
-- matematica incorreta que impede o uso do HNSW index de similaridade
-- vetorial, fazendo toda busca hibrida com embedding rodar full scan.
--
-- CHANGE LOG (v1.2.1 — QA fixes DOC-001, DOC-002):
--   DOC-001: p_esferas mudou de INT[] para TEXT[] (compatibilidade com callers
--            que passam strings como '{1,2,3}' em vez de arrays Postgres).
--   DOC-002: p_sources removido — todos os callers ativos (datalake_helper.py,
--            local_datalake.py) chamam a funcao sem este parametro.
--
-- Expressao ORIGINAL (incorreta):
--   (1.0 - (vec <=> p_embedding)) >= threshold
--
-- Expressao CORRIGIDA:
--   (vec <=> p_embedding) < (1.0 - threshold)
--
-- Explicacao:
--   O operador <=> (cosine distance) retorna valores em [0, 2], onde
--   0 = mesmo vetor e 2 = direcoes opostas. O HNSW index do pgvector
--   so pode ser utilizado quando a comparacao e feita DIRETAMENTE
--   contra o operador de distancia. Envolver a expressao em aritmetica
--   (1.0 - distance) impede o planner de reconhecer a oportunidade de
--   Index Scan, forcando um Seq Scan na tabela pncp_raw_bids.
--
--   A correcao inverte a logica: em vez de converter distancia para
--   similaridade e comparar, compara a distancia bruta diretamente
--   contra o complemento do threshold.

-- ============================================================
-- 1. Garantir extensao pgvector (necessaria para <=> operator)
-- ============================================================
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- 2. Recreate search_datalake with corrected HNSW expression
-- ============================================================
--
-- Esta funcao tem 13 parametros e suporta hybrid search (FTS + embedding).
-- A correcao esta no WHERE clause da hybrid search: linha com p_embedding.
--
-- Comparacao com a versao anterior (migration 005):
--   - Adicionados: p_websearch_text, p_modo, p_offset, p_embedding
--   - Retorno estendido para incluir colunas do schema real
--   - Expressao HNSW corrigida
--   - Suporte a websearch_to_tsquery para texto livre do usuario
--   - Modo "abertas" (encerramento futuro) adicionado

CREATE OR REPLACE FUNCTION search_datalake(
    p_ufs          TEXT[]   DEFAULT NULL,
    p_date_start   DATE     DEFAULT NULL,
    p_date_end     DATE     DEFAULT NULL,
    p_tsquery      TEXT     DEFAULT NULL,
    p_websearch_text TEXT   DEFAULT NULL,
    p_modalidades  INT[]    DEFAULT NULL,
    p_valor_min    NUMERIC  DEFAULT NULL,
    p_valor_max    NUMERIC  DEFAULT NULL,
    p_esferas      TEXT[]   DEFAULT NULL,
    p_modo         TEXT     DEFAULT 'publicacao',
    p_limit        INT      DEFAULT 100,
    p_offset       INT      DEFAULT 0,
    p_embedding    VECTOR(256) DEFAULT NULL
)
RETURNS TABLE (
    pncp_id              TEXT,
    objeto_compra        TEXT,
    valor_total_estimado NUMERIC,
    modalidade_id        INT,
    modalidade_nome      TEXT,
    situacao_compra      TEXT,
    esfera_id            TEXT,
    uf                   TEXT,
    municipio            TEXT,
    codigo_municipio_ibge TEXT,
    orgao_razao_social   TEXT,
    orgao_cnpj           TEXT,
    unidade_nome         TEXT,
    data_publicacao      TIMESTAMPTZ,
    data_abertura        TIMESTAMPTZ,
    data_encerramento    TIMESTAMPTZ,
    link_sistema_origem  TEXT,
    link_pncp            TEXT,
    content_hash         TEXT,
    source               TEXT,
    ingested_at          TIMESTAMPTZ,
    updated_at           TIMESTAMPTZ,
    ts_rank              REAL
) LANGUAGE plpgsql STABLE AS $$
DECLARE
    v_threshold CONSTANT REAL := 0.7; -- minimum cosine similarity for embedding match
    v_webquery  TSQUERY;
BEGIN
    -- Convert websearch text to tsquery if provided
    IF p_websearch_text IS NOT NULL AND p_websearch_text != '' THEN
        BEGIN
            v_webquery := websearch_to_tsquery('portuguese', p_websearch_text);
        EXCEPTION WHEN OTHERS THEN
            v_webquery := NULL;
        END;
    END IF;

    RETURN QUERY
    SELECT
        b.pncp_id,
        b.objeto_compra,
        b.valor_total_estimado,
        b.modalidade_id,
        b.modalidade_nome,
        b.situacao_compra,
        b.esfera_id,
        b.uf,
        b.municipio,
        b.codigo_municipio_ibge,
        b.orgao_razao_social,
        b.orgao_cnpj,
        b.unidade_nome,
        b.data_publicacao,
        b.data_abertura,
        b.data_encerramento,
        b.link_sistema_origem,
        b.link_pncp,
        b.content_hash,
        b.source,
        b.ingested_at,
        b.updated_at,
        CASE
            WHEN p_tsquery IS NOT NULL AND b.tsv IS NOT NULL
            THEN ts_rank(b.tsv, to_tsquery('portuguese', p_tsquery))
            WHEN v_webquery IS NOT NULL AND b.tsv IS NOT NULL
            THEN ts_rank(b.tsv, v_webquery)
            ELSE 0.0
        END::REAL AS ts_rank
    FROM pncp_raw_bids b
    WHERE b.is_active = TRUE
      -- Filtros de metadados
      AND (p_ufs IS NULL OR b.uf = ANY(p_ufs))
      AND (p_date_start IS NULL OR b.data_publicacao >= p_date_start)
      AND (p_date_end IS NULL OR b.data_publicacao <= p_date_end)
      AND (p_modalidades IS NULL OR b.modalidade_id = ANY(p_modalidades))
      AND (p_valor_min IS NULL OR b.valor_total_estimado >= p_valor_min)
      AND (p_valor_max IS NULL OR b.valor_total_estimado <= p_valor_max)
      AND (p_esferas IS NULL OR b.esfera_id = ANY(p_esferas))
      -- Modo "abertas": encerramento futuro
      AND (p_modo IS DISTINCT FROM 'abertas' OR b.data_encerramento >= CURRENT_DATE)
      -- Filtro full-text search (tsquery classico)
      AND (
          p_tsquery IS NULL
          OR b.tsv @@ to_tsquery('portuguese', p_tsquery)
          OR b.objeto_compra ILIKE '%' || p_tsquery || '%'
      )
      -- Filtro websearch (texto livre do usuario)
      AND (
          v_webquery IS NULL
          OR b.tsv @@ v_webquery
      )
      -- Hybrid search: embedding similarity filter
      -- CORRECAO TD-DB-11: Expressao corrigida para permitir HNSW Index Scan
      -- ANTES: (1.0 - (vec <=> p_embedding)) >= v_threshold
      -- DEPOIS: (vec <=> p_embedding) < (1.0 - v_threshold)
      AND (
          p_embedding IS NULL
          OR b.embedding IS NULL
          OR (b.embedding <=> p_embedding) < (1.0 - v_threshold)
      )
    ORDER BY
        CASE
            WHEN p_tsquery IS NOT NULL AND b.tsv IS NOT NULL
            THEN ts_rank(b.tsv, to_tsquery('portuguese', p_tsquery))
            WHEN v_webquery IS NOT NULL AND b.tsv IS NOT NULL
            THEN ts_rank(b.tsv, v_webquery)
            ELSE 0.0
        END DESC,
        b.data_publicacao DESC
    OFFSET p_offset
    LIMIT p_limit;
END;
$$;

COMMENT ON FUNCTION search_datalake IS
    'TD-DB-11: Multi-filter hybrid search (FTS + embedding) com HNSW expression corrigida (Story TD-1.1)';
