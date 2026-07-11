-- ============================================================================
-- 001-v2_initial_schema.sql — Baseline Migration v2
-- ============================================================================
-- Story TD-2.1: Reconstruir Migrations do Zero
-- Debito: TD-DB-01 (CRITICAL) — Migrations totalmente divergentes do schema real
--
-- Esta migration substitui as 14 migrations antigas (001-014 em db/migrations/)
-- por uma unica migration baseline que reproduz FIELMENTE o schema real do
-- banco em producao (extraido via pg_dump --schema-only em 2026-07-11).
--
-- ATENCAO: Nao e possivel simplesmente DROP/CREATE em producao.
-- Este arquivo e o baseline para:
--   a) Recriar o banco do zero (dev/test)
--   b) Verificar que o schema atual corresponde ao esperado
--   c) Servir como ponto de partida para migrations incrementais (002-v2+)
--
-- Principios:
--   - Reexecutavel: todos os comandos usam IF NOT EXISTS / OR REPLACE
--   - Fiel ao schema real: zero divergencias com o banco em producao
--   - Ordem correta de dependencias: extensions → sequences → tables
--     → functions → views → indexes → triggers → foreign keys
--
-- Divergencias conhecidas vs db/migrations/ antigas:
--   - Migration 014 (TD-1.1 fix_hnsw_expression) NAO reflete o schema real
--     atual — as colunas situacao_compra, unidade_nome, link_sistema_origem,
--     embedding, vec NAO existem no banco. A funcao search_datalake na v2
--     mantem a assinatura original de 10 parametros.
--   - A extensao pgvector NAO esta instalada no schema real.
--   - Documentacao completa: docs/td-001/migration-rebuild.md
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. Extensions
-- ============================================================================
CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;

-- ============================================================================
-- 2. Tables & Sequences
-- ============================================================================
-- Ordem: tabelas sem FK primeiro, depois tabelas com dependencias

-- --------------------------------------------------------------------------
-- 2.1 sc_public_entities (dependentes: entity_coverage, pncp_raw_bids)
-- --------------------------------------------------------------------------
CREATE SEQUENCE IF NOT EXISTS public.sc_public_entities_id_seq
    AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;

CREATE TABLE IF NOT EXISTS public.sc_public_entities (
    id              INTEGER NOT NULL,
    razao_social    TEXT NOT NULL,
    cnpj_8          TEXT NOT NULL,
    municipio       TEXT,
    codigo_ibge     TEXT,
    natureza_juridica TEXT,
    cod_natureza    TEXT,
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION,
    distancia_fk    DOUBLE PRECISION,
    raio_200km      BOOLEAN NOT NULL DEFAULT FALSE,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER SEQUENCE public.sc_public_entities_id_seq OWNED BY public.sc_public_entities.id;
ALTER TABLE ONLY public.sc_public_entities ALTER COLUMN id SET DEFAULT nextval('public.sc_public_entities_id_seq'::regclass);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'sc_public_entities_pkey') THEN
        ALTER TABLE ONLY public.sc_public_entities
            ADD CONSTRAINT sc_public_entities_pkey PRIMARY KEY (id);
    END IF;
END $$;

-- --------------------------------------------------------------------------
-- 2.2 enriched_entities (sem dependencias de FK)
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.enriched_entities (
    cnpj              TEXT NOT NULL,
    razao_social      TEXT,
    nome_fantasia     TEXT,
    cnae_principal    TEXT,
    cnae_secundarios  TEXT[],
    municipio         TEXT,
    uf                TEXT,
    codigo_ibge       TEXT,
    natureza_juridica TEXT,
    logradouro        TEXT,
    bairro            TEXT,
    cep               TEXT,
    telefone          TEXT,
    email             TEXT,
    situacao          TEXT,
    enriched_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    enriched_source   TEXT NOT NULL DEFAULT 'brasilapi'
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'enriched_entities_pkey') THEN
        ALTER TABLE ONLY public.enriched_entities
            ADD CONSTRAINT enriched_entities_pkey PRIMARY KEY (cnpj);
    END IF;
END $$;

-- --------------------------------------------------------------------------
-- 2.3 entity_coverage (FK → sc_public_entities)
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.entity_coverage (
    entity_id    INTEGER NOT NULL,
    source       TEXT NOT NULL,
    last_seen_at TIMESTAMPTZ,
    total_bids   INTEGER NOT NULL DEFAULT 0,
    is_covered   BOOLEAN NOT NULL DEFAULT FALSE,
    within_200km BOOLEAN NOT NULL DEFAULT FALSE
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'entity_coverage_pkey') THEN
        ALTER TABLE ONLY public.entity_coverage
            ADD CONSTRAINT entity_coverage_pkey PRIMARY KEY (entity_id, source);
    END IF;
END $$;

-- --------------------------------------------------------------------------
-- 2.4 pncp_raw_bids (FK → sc_public_entities via matched_entity_id)
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.pncp_raw_bids (
    pncp_id               TEXT NOT NULL,
    objeto_compra         TEXT,
    valor_total_estimado  NUMERIC(18,2),
    modalidade_id         INTEGER,
    modalidade_nome       TEXT,
    esfera_id             INTEGER,
    uf                    TEXT,
    municipio             TEXT,
    codigo_municipio_ibge TEXT,
    orgao_razao_social    TEXT,
    orgao_cnpj            TEXT,
    data_publicacao       DATE,
    data_abertura         DATE,
    data_encerramento     DATE,
    link_pncp             TEXT,
    content_hash          TEXT,
    tsv                   TSVECTOR,
    source                TEXT NOT NULL DEFAULT 'pncp',
    source_id             TEXT,
    matched_entity_id     INTEGER,
    ingested_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active             BOOLEAN NOT NULL DEFAULT TRUE
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'pncp_raw_bids_pkey') THEN
        ALTER TABLE ONLY public.pncp_raw_bids
            ADD CONSTRAINT pncp_raw_bids_pkey PRIMARY KEY (pncp_id);
    END IF;
END $$;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'pncp_raw_bids_content_hash_key') THEN
        ALTER TABLE ONLY public.pncp_raw_bids
            ADD CONSTRAINT pncp_raw_bids_content_hash_key UNIQUE (content_hash);
    END IF;
END $$;

-- --------------------------------------------------------------------------
-- 2.5 pncp_supplier_contracts (sem FK)
-- --------------------------------------------------------------------------
CREATE SEQUENCE IF NOT EXISTS public.pncp_supplier_contracts_id_seq
    AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;

CREATE TABLE IF NOT EXISTS public.pncp_supplier_contracts (
    id              INTEGER NOT NULL,
    contrato_id     TEXT,
    orgao_cnpj      TEXT,
    orgao_nome      TEXT,
    fornecedor_cnpj TEXT,
    fornecedor_nome TEXT,
    objeto_contrato TEXT,
    valor_total     NUMERIC(18,2),
    data_inicio     DATE,
    data_fim        DATE,
    data_publicacao DATE,
    uf              TEXT,
    municipio       TEXT,
    source          TEXT NOT NULL DEFAULT 'pncp',
    source_id       TEXT,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER SEQUENCE public.pncp_supplier_contracts_id_seq OWNED BY public.pncp_supplier_contracts.id;
ALTER TABLE ONLY public.pncp_supplier_contracts ALTER COLUMN id SET DEFAULT nextval('public.pncp_supplier_contracts_id_seq'::regclass);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'pncp_supplier_contracts_pkey') THEN
        ALTER TABLE ONLY public.pncp_supplier_contracts
            ADD CONSTRAINT pncp_supplier_contracts_pkey PRIMARY KEY (id);
    END IF;
END $$;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'pncp_supplier_contracts_contrato_id_key') THEN
        ALTER TABLE ONLY public.pncp_supplier_contracts
            ADD CONSTRAINT pncp_supplier_contracts_contrato_id_key UNIQUE (contrato_id);
    END IF;
END $$;

-- --------------------------------------------------------------------------
-- 2.6 coverage_snapshots (sem FK)
-- --------------------------------------------------------------------------
CREATE SEQUENCE IF NOT EXISTS public.coverage_snapshots_id_seq
    AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;

CREATE TABLE IF NOT EXISTS public.coverage_snapshots (
    id               INTEGER NOT NULL,
    snapshot_date    DATE NOT NULL DEFAULT CURRENT_DATE,
    source           TEXT NOT NULL,
    total_entities   INTEGER NOT NULL,
    covered_entities INTEGER NOT NULL,
    pct_covered      NUMERIC(5,2) NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER SEQUENCE public.coverage_snapshots_id_seq OWNED BY public.coverage_snapshots.id;
ALTER TABLE ONLY public.coverage_snapshots ALTER COLUMN id SET DEFAULT nextval('public.coverage_snapshots_id_seq'::regclass);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'coverage_snapshots_pkey') THEN
        ALTER TABLE ONLY public.coverage_snapshots
            ADD CONSTRAINT coverage_snapshots_pkey PRIMARY KEY (id);
    END IF;
END $$;

-- --------------------------------------------------------------------------
-- 2.7 ingestion_checkpoints (sem FK)
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.ingestion_checkpoints (
    source           TEXT NOT NULL DEFAULT 'pncp',
    scope_key        TEXT NOT NULL,
    last_page        INTEGER NOT NULL DEFAULT 0,
    last_date        DATE,
    last_id          TEXT,
    records_fetched  INTEGER NOT NULL DEFAULT 0,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ingestion_checkpoints_pkey') THEN
        ALTER TABLE ONLY public.ingestion_checkpoints
            ADD CONSTRAINT ingestion_checkpoints_pkey PRIMARY KEY (source, scope_key);
    END IF;
END $$;

-- --------------------------------------------------------------------------
-- 2.8 ingestion_runs (sem FK)
-- --------------------------------------------------------------------------
CREATE SEQUENCE IF NOT EXISTS public.ingestion_runs_id_seq
    AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;

CREATE TABLE IF NOT EXISTS public.ingestion_runs (
    id                INTEGER NOT NULL,
    source            TEXT NOT NULL,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at       TIMESTAMPTZ,
    records_fetched   INTEGER NOT NULL DEFAULT 0,
    records_upserted  INTEGER NOT NULL DEFAULT 0,
    entities_covered  INTEGER NOT NULL DEFAULT 0,
    status            TEXT NOT NULL DEFAULT 'running',
    error_message     TEXT,
    metadata          JSONB
);

ALTER SEQUENCE public.ingestion_runs_id_seq OWNED BY public.ingestion_runs.id;
ALTER TABLE ONLY public.ingestion_runs ALTER COLUMN id SET DEFAULT nextval('public.ingestion_runs_id_seq'::regclass);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ingestion_runs_pkey') THEN
        ALTER TABLE ONLY public.ingestion_runs
            ADD CONSTRAINT ingestion_runs_pkey PRIMARY KEY (id);
    END IF;
END $$;

-- ============================================================================
-- 3. Functions
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 3.1 set_updated_at — Trigger function for updated_at auto-update
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

-- ----------------------------------------------------------------------------
-- 3.2 upsert_pncp_raw_bids — Insert or skip bids by content_hash
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.upsert_pncp_raw_bids(p_records JSONB)
RETURNS TABLE(action TEXT, pncp_id TEXT, content_hash TEXT)
LANGUAGE plpgsql
AS $$
DECLARE
    rec JSONB;
BEGIN
    FOR rec IN SELECT * FROM jsonb_array_elements(p_records)
    LOOP
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
        ON CONFLICT ON CONSTRAINT pncp_raw_bids_content_hash_key DO NOTHING;

        IF FOUND THEN
            RETURN QUERY SELECT 'inserted'::TEXT, rec->>'pncp_id', rec->>'content_hash'::TEXT;
        ELSE
            RETURN QUERY SELECT 'skipped'::TEXT, rec->>'pncp_id', rec->>'content_hash'::TEXT;
        END IF;
    END LOOP;
END;
$$;

-- ----------------------------------------------------------------------------
-- 3.3 upsert_pncp_supplier_contracts — Insert or skip contracts by contrato_id
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.upsert_pncp_supplier_contracts(p_records JSONB)
RETURNS TABLE(result TEXT, id TEXT)
LANGUAGE plpgsql
AS $$
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
        ON CONFLICT ON CONSTRAINT pncp_supplier_contracts_contrato_id_key DO NOTHING;

        IF FOUND THEN
            RETURN QUERY SELECT 'inserted'::TEXT, rec->>'contrato_id';
        ELSE
            RETURN QUERY SELECT 'skipped'::TEXT, rec->>'contrato_id';
        END IF;
    END LOOP;
END;
$$;

-- ----------------------------------------------------------------------------
-- 3.4 search_datalake — Multi-filter FTS search (v1 signature, 10 params)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.search_datalake(
    p_ufs          TEXT[]   DEFAULT NULL,
    p_date_start   DATE     DEFAULT NULL,
    p_date_end     DATE     DEFAULT NULL,
    p_tsquery      TEXT     DEFAULT NULL,
    p_modalidades  INT[]    DEFAULT NULL,
    p_valor_min    NUMERIC  DEFAULT NULL,
    p_valor_max    NUMERIC  DEFAULT NULL,
    p_esferas      INT[]    DEFAULT NULL,
    p_sources      TEXT[]   DEFAULT NULL,
    p_limit        INT      DEFAULT 100
)
RETURNS TABLE(
    pncp_id              TEXT,
    objeto_compra        TEXT,
    valor_total_estimado NUMERIC,
    modalidade_nome      TEXT,
    uf                   TEXT,
    municipio            TEXT,
    orgao_razao_social   TEXT,
    orgao_cnpj           TEXT,
    data_publicacao      DATE,
    data_encerramento    DATE,
    link_pncp            TEXT,
    source               TEXT,
    rank                 REAL
)
LANGUAGE plpgsql STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT
        b.pncp_id,
        b.objeto_compra,
        b.valor_total_estimado,
        b.modalidade_nome,
        b.uf,
        b.municipio,
        b.orgao_razao_social,
        b.orgao_cnpj,
        b.data_publicacao,
        b.data_encerramento,
        b.link_pncp,
        b.source,
        CASE
            WHEN p_tsquery IS NOT NULL AND b.tsv IS NOT NULL
            THEN ts_rank(b.tsv, to_tsquery('portuguese', p_tsquery))
            ELSE 0.0
        END AS rank
    FROM pncp_raw_bids b
    WHERE b.is_active = TRUE
      AND (p_ufs IS NULL OR b.uf = ANY(p_ufs))
      AND (p_date_start IS NULL OR b.data_publicacao >= p_date_start)
      AND (p_date_end IS NULL OR b.data_publicacao <= p_date_end)
      AND (p_modalidades IS NULL OR b.modalidade_id = ANY(p_modalidades))
      AND (p_valor_min IS NULL OR b.valor_total_estimado >= p_valor_min)
      AND (p_valor_max IS NULL OR b.valor_total_estimado <= p_valor_max)
      AND (p_esferas IS NULL OR b.esfera_id = ANY(p_esferas))
      AND (p_sources IS NULL OR b.source = ANY(p_sources))
      AND (
          p_tsquery IS NULL
          OR b.tsv @@ to_tsquery('portuguese', p_tsquery)
          OR b.objeto_compra ILIKE '%' || p_tsquery || '%'
      )
    ORDER BY
        CASE WHEN p_tsquery IS NOT NULL
             THEN ts_rank(b.tsv, to_tsquery('portuguese', p_tsquery))
             ELSE 0.0
        END DESC,
        b.data_publicacao DESC
    LIMIT p_limit;
END;
$$;

-- ----------------------------------------------------------------------------
-- 3.5 update_entity_coverage — Trigger: AFTER INSERT on pncp_raw_bids
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.update_entity_coverage()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.matched_entity_id IS NOT NULL THEN
        INSERT INTO entity_coverage (entity_id, source, last_seen_at, total_bids, is_covered, within_200km)
        VALUES (
            NEW.matched_entity_id,
            NEW.source,
            NEW.data_publicacao,
            1,
            COALESCE(NEW.data_publicacao >= CURRENT_DATE - 90, FALSE),
            COALESCE((SELECT raio_200km FROM sc_public_entities WHERE id = NEW.matched_entity_id), FALSE)
        )
        ON CONFLICT (entity_id, source) DO UPDATE
        SET
            last_seen_at = GREATEST(COALESCE(entity_coverage.last_seen_at, '1970-01-01'::date), COALESCE(NEW.data_publicacao, '1970-01-01'::date)),
            total_bids = entity_coverage.total_bids + 1,
            is_covered = GREATEST(COALESCE(entity_coverage.last_seen_at, '1970-01-01'::date), COALESCE(NEW.data_publicacao, '1970-01-01'::date)) >= CURRENT_DATE - 90;
    END IF;
    RETURN NEW;
END;
$$;

-- ----------------------------------------------------------------------------
-- 3.6 update_entity_coverage_on_update — Trigger: AFTER UPDATE on pncp_raw_bids
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.update_entity_coverage_on_update()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.matched_entity_id IS NOT NULL AND (OLD.matched_entity_id IS NULL OR OLD.matched_entity_id <> NEW.matched_entity_id) THEN
        INSERT INTO entity_coverage (entity_id, source, last_seen_at, total_bids, is_covered, within_200km)
        VALUES (
            NEW.matched_entity_id,
            NEW.source,
            NEW.data_publicacao,
            1,
            COALESCE(NEW.data_publicacao >= CURRENT_DATE - 90, FALSE),
            COALESCE((SELECT raio_200km FROM sc_public_entities WHERE id = NEW.matched_entity_id), FALSE)
        )
        ON CONFLICT (entity_id, source) DO UPDATE
        SET
            last_seen_at = GREATEST(COALESCE(entity_coverage.last_seen_at, '1970-01-01'::date), COALESCE(NEW.data_publicacao, '1970-01-01'::date)),
            total_bids = entity_coverage.total_bids + 1,
            is_covered = GREATEST(COALESCE(entity_coverage.last_seen_at, '1970-01-01'::date), COALESCE(NEW.data_publicacao, '1970-01-01'::date)) >= CURRENT_DATE - 90;
    END IF;
    RETURN NEW;
END;
$$;

-- ----------------------------------------------------------------------------
-- 3.7 generate_coverage_snapshot — Weekly coverage snapshot generator
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.generate_coverage_snapshot(snap_date DATE DEFAULT CURRENT_DATE)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    inserted INT := 0;
    rec RECORD;
BEGIN
    FOR rec IN
        SELECT
            ec.source,
            COUNT(*) AS total_entities,
            SUM(CASE WHEN ec.is_covered THEN 1 ELSE 0 END) AS covered_entities
        FROM entity_coverage ec
        WHERE EXISTS (
            SELECT 1 FROM sc_public_entities e
            WHERE e.id = ec.entity_id AND e.is_active = TRUE
        )
        GROUP BY ec.source
    LOOP
        INSERT INTO coverage_snapshots (snapshot_date, source, total_entities, covered_entities, pct_covered)
        VALUES (
            snap_date,
            rec.source,
            rec.total_entities,
            rec.covered_entities,
            ROUND(100.0 * rec.covered_entities / NULLIF(rec.total_entities, 0), 2)
        )
        ON CONFLICT DO NOTHING;
        inserted := inserted + 1;
    END LOOP;

    RETURN inserted;
END;
$$;

-- ----------------------------------------------------------------------------
-- 3.8 purge_old_bids — Soft-delete old inactive records
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.purge_old_bids(p_retention_days INTEGER DEFAULT 400)
RETURNS TABLE(purged_count INTEGER, remaining_count INTEGER)
LANGUAGE plpgsql
AS $$
DECLARE
    cutoff_date DATE;
    v_purged INT;
BEGIN
    cutoff_date := CURRENT_DATE - p_retention_days;

    UPDATE pncp_raw_bids
    SET is_active = FALSE
    WHERE is_active = TRUE
      AND data_publicacao < cutoff_date;

    GET DIAGNOSTICS v_purged = ROW_COUNT;

    RETURN QUERY
    SELECT
        v_purged,
        COUNT(*)::INT
    FROM pncp_raw_bids
    WHERE is_active = TRUE;
END;
$$;

-- ============================================================================
-- 4. Views
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 4.1 v_coverage_gaps — Public entities with TOTAL coverage gap (all sources)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.v_coverage_gaps AS
SELECT
    e.id,
    e.razao_social,
    e.cnpj_8,
    e.municipio,
    e.natureza_juridica,
    e.raio_200km,
    e.distancia_fk,
    ARRAY(
        SELECT ec.source
        FROM public.entity_coverage ec
        WHERE ec.entity_id = e.id AND ec.is_covered = TRUE
    ) AS fontes_ativas,
    (
        SELECT COUNT(DISTINCT ec2.source)
        FROM public.entity_coverage ec2
        WHERE ec2.entity_id = e.id AND ec2.is_covered = TRUE
    ) = 0 AS gap_total
FROM public.sc_public_entities e
WHERE e.is_active = TRUE
  AND NOT EXISTS (
    SELECT 1 FROM public.entity_coverage ec
    WHERE ec.entity_id = e.id AND ec.is_covered = TRUE
  )
ORDER BY e.municipio, e.razao_social;

-- ----------------------------------------------------------------------------
-- 4.2 v_coverage_gaps_by_municipio — Aggregated coverage gaps by municipality
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.v_coverage_gaps_by_municipio AS
SELECT
    e.municipio,
    COUNT(*) AS total_entes,
    COUNT(*) FILTER (WHERE NOT EXISTS (
        SELECT 1 FROM public.entity_coverage ec
        WHERE ec.entity_id = e.id AND ec.is_covered = TRUE
    )) AS entes_descobertos,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE NOT EXISTS (
            SELECT 1 FROM public.entity_coverage ec
            WHERE ec.entity_id = e.id AND ec.is_covered = TRUE
        )) / NULLIF(COUNT(*), 0), 1
    ) AS pct_gap,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE EXISTS (
            SELECT 1 FROM public.entity_coverage ec
            WHERE ec.entity_id = e.id AND ec.is_covered = TRUE
        )) / NULLIF(COUNT(*), 0), 1
    ) AS pct_coberto
FROM public.sc_public_entities e
WHERE e.is_active = TRUE
GROUP BY e.municipio
ORDER BY entes_descobertos DESC, pct_gap DESC;

-- ----------------------------------------------------------------------------
-- 4.3 v_coverage_summary — Coverage summary per source
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.v_coverage_summary AS
SELECT
    ec.source,
    ec.within_200km,
    ec.is_covered,
    COUNT(*) AS entity_count,
    ROUND(
        (COUNT(*)::NUMERIC * 100.0) / SUM(COUNT(*)) OVER (PARTITION BY ec.within_200km), 1
    ) AS pct
FROM public.entity_coverage ec
WHERE EXISTS (
    SELECT 1 FROM public.sc_public_entities e
    WHERE e.id = ec.entity_id AND e.is_active = TRUE
)
GROUP BY ec.source, ec.within_200km, ec.is_covered
ORDER BY ec.source, ec.within_200km, ec.is_covered;

-- ----------------------------------------------------------------------------
-- 4.4 v_coverage_trend — Weekly coverage evolution with variation
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.v_coverage_trend AS
SELECT
    cs.snapshot_date,
    cs.source,
    cs.total_entities,
    cs.covered_entities,
    cs.pct_covered,
    cs.pct_covered - LAG(cs.pct_covered) OVER (
        PARTITION BY cs.source ORDER BY cs.snapshot_date
    ) AS variacao_pct,
    ROW_NUMBER() OVER (
        PARTITION BY cs.source ORDER BY cs.snapshot_date DESC
    ) AS rn_desc
FROM public.coverage_snapshots cs
ORDER BY cs.snapshot_date DESC, cs.source;

-- ============================================================================
-- 5. Indexes
-- ============================================================================

-- pncp_raw_bids
CREATE INDEX IF NOT EXISTS idx_bids_active ON public.pncp_raw_bids USING btree (is_active, data_publicacao DESC) WHERE (is_active = TRUE);
CREATE INDEX IF NOT EXISTS idx_bids_encerramento ON public.pncp_raw_bids USING btree (data_encerramento) WHERE (data_encerramento IS NOT NULL);
CREATE INDEX IF NOT EXISTS idx_bids_esfera ON public.pncp_raw_bids USING btree (esfera_id);
CREATE INDEX IF NOT EXISTS idx_bids_ingested ON public.pncp_raw_bids USING btree (ingested_at DESC);
CREATE INDEX IF NOT EXISTS idx_bids_matched_entity ON public.pncp_raw_bids USING btree (matched_entity_id) WHERE (matched_entity_id IS NOT NULL);
CREATE INDEX IF NOT EXISTS idx_bids_modalidade ON public.pncp_raw_bids USING btree (modalidade_id, data_publicacao DESC);
CREATE INDEX IF NOT EXISTS idx_bids_orgao_cnpj ON public.pncp_raw_bids USING btree (orgao_cnpj);
CREATE INDEX IF NOT EXISTS idx_bids_orgao_hash ON public.pncp_raw_bids USING btree (orgao_cnpj, content_hash);
CREATE INDEX IF NOT EXISTS idx_bids_source ON public.pncp_raw_bids USING btree (source);
CREATE INDEX IF NOT EXISTS idx_bids_tsv ON public.pncp_raw_bids USING gin (tsv);
CREATE INDEX IF NOT EXISTS idx_bids_uf_data ON public.pncp_raw_bids USING btree (uf, data_publicacao DESC);
CREATE INDEX IF NOT EXISTS idx_bids_uf_source ON public.pncp_raw_bids USING btree (uf, source, data_publicacao DESC);
CREATE INDEX IF NOT EXISTS idx_bids_valor ON public.pncp_raw_bids USING btree (valor_total_estimado);

-- entity_coverage
CREATE INDEX IF NOT EXISTS idx_cov_covered ON public.entity_coverage USING btree (is_covered, within_200km);
CREATE INDEX IF NOT EXISTS idx_cov_last_seen ON public.entity_coverage USING btree (last_seen_at);
CREATE INDEX IF NOT EXISTS idx_cov_source ON public.entity_coverage USING btree (source, is_covered);

-- coverage_snapshots
CREATE INDEX IF NOT EXISTS idx_cov_snap_date ON public.coverage_snapshots USING btree (snapshot_date);
CREATE INDEX IF NOT EXISTS idx_cov_snap_source ON public.coverage_snapshots USING btree (source, snapshot_date);

-- enriched_entities
CREATE INDEX IF NOT EXISTS idx_ee_enriched_at ON public.enriched_entities USING btree (enriched_at);
CREATE INDEX IF NOT EXISTS idx_ee_uf ON public.enriched_entities USING btree (uf);

-- ingestion_runs
CREATE INDEX IF NOT EXISTS idx_ir_source_status ON public.ingestion_runs USING btree (source, status);
CREATE INDEX IF NOT EXISTS idx_ir_started ON public.ingestion_runs USING btree (started_at DESC);

-- pncp_supplier_contracts
CREATE INDEX IF NOT EXISTS idx_psc_data ON public.pncp_supplier_contracts USING btree (data_publicacao DESC);
CREATE INDEX IF NOT EXISTS idx_psc_fornecedor ON public.pncp_supplier_contracts USING btree (fornecedor_cnpj, data_publicacao DESC);
CREATE INDEX IF NOT EXISTS idx_psc_objeto_trgm ON public.pncp_supplier_contracts USING gin (objeto_contrato public.gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_psc_orgao ON public.pncp_supplier_contracts USING btree (orgao_cnpj);
CREATE INDEX IF NOT EXISTS idx_psc_uf ON public.pncp_supplier_contracts USING btree (uf, data_publicacao DESC);
CREATE INDEX IF NOT EXISTS idx_psc_valor ON public.pncp_supplier_contracts USING btree (valor_total);

-- sc_public_entities
CREATE INDEX IF NOT EXISTS idx_spe_cnpj ON public.sc_public_entities USING btree (cnpj_8);
CREATE INDEX IF NOT EXISTS idx_spe_ibge ON public.sc_public_entities USING btree (codigo_ibge);
CREATE INDEX IF NOT EXISTS idx_spe_municipio ON public.sc_public_entities USING btree (municipio);
CREATE INDEX IF NOT EXISTS idx_spe_natureza ON public.sc_public_entities USING btree (cod_natureza);
CREATE INDEX IF NOT EXISTS idx_spe_raio ON public.sc_public_entities USING btree (raio_200km, is_active);

-- ============================================================================
-- 6. Triggers
-- ============================================================================

DROP TRIGGER IF EXISTS trg_bids_updated_at ON public.pncp_raw_bids;
CREATE TRIGGER trg_bids_updated_at
    BEFORE UPDATE ON public.pncp_raw_bids
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS trg_bids_coverage ON public.pncp_raw_bids;
CREATE TRIGGER trg_bids_coverage
    AFTER INSERT ON public.pncp_raw_bids
    FOR EACH ROW EXECUTE FUNCTION public.update_entity_coverage();

DROP TRIGGER IF EXISTS trg_bids_coverage_update ON public.pncp_raw_bids;
CREATE TRIGGER trg_bids_coverage_update
    AFTER UPDATE ON public.pncp_raw_bids
    FOR EACH ROW EXECUTE FUNCTION public.update_entity_coverage_on_update();

-- ============================================================================
-- 7. Foreign Keys
-- ============================================================================

-- FK: entity_coverage.entity_id → sc_public_entities.id
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'entity_coverage_entity_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.entity_coverage
            ADD CONSTRAINT entity_coverage_entity_id_fkey
            FOREIGN KEY (entity_id) REFERENCES public.sc_public_entities(id)
            ON DELETE CASCADE;
    END IF;
END $$;

-- FK: pncp_raw_bids.matched_entity_id → sc_public_entities.id
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_bids_matched_entity'
    ) THEN
        ALTER TABLE ONLY public.pncp_raw_bids
            ADD CONSTRAINT fk_bids_matched_entity
            FOREIGN KEY (matched_entity_id) REFERENCES public.sc_public_entities(id)
            ON DELETE SET NULL;
    END IF;
END $$;

-- ============================================================================
-- 8. Comments
-- ============================================================================

COMMENT ON TABLE public.coverage_snapshots IS 'Snapshots semanais de cobertura por fonte — usado para tendencia no relatorio semanal (Story 001.7)';
COMMENT ON VIEW public.v_coverage_gaps IS 'Entes publicos com gap TOTAL de cobertura (is_covered = FALSE em todas as fontes) — Story 001.5/001.7';
COMMENT ON VIEW public.v_coverage_gaps_by_municipio IS 'Agregacao de gaps de cobertura por municipio — Story 001.5/001.7';
COMMENT ON VIEW public.v_coverage_trend IS 'Evolucao semanal da cobertura com calculo de variacao — Story 001.5/001.7';
COMMENT ON FUNCTION public.generate_coverage_snapshot IS 'Gera snapshot de cobertura para todos as fontes — chamado pelo timer semanal (Story 001.7)';
COMMENT ON FUNCTION public.search_datalake IS 'Multi-filter search: FTS com tsquery, filtros por uf/data/modalidade/valor/esfera/source — Story TD-2.1 baseline';
COMMENT ON FUNCTION public.upsert_pncp_raw_bids IS 'Insere ou ignora bids por content_hash — usado pelos crawlers (pncp, dom_sc)';
COMMENT ON FUNCTION public.upsert_pncp_supplier_contracts IS 'Insere ou ignora contratos por contrato_id';

-- ============================================================================
-- 9. Register in _migrations tracking table
-- ============================================================================
-- Garante que a tabela de tracking existe (pode vir do _migrations.sql ou ser
-- criada aqui diretamente, garantindo que 001-v2 e auto-suiciente)
CREATE TABLE IF NOT EXISTS public._migrations (
    version      TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    applied_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    checksum     TEXT,
    rollback_sql TEXT
);

INSERT INTO public._migrations (version, name, applied_at, checksum, rollback_sql)
VALUES (
    '001-v2',
    'initial_schema',
    NOW(),
    'manual-verify',
    NULL
)
ON CONFLICT (version) DO NOTHING;

COMMIT;
