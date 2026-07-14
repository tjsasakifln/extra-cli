--
-- PostgreSQL database dump — schema-only baseline
-- Extracted from local pncp_datalake on 2026-07-11
-- Database version: PostgreSQL 18.4 (Ubuntu 18.4-1.pgdg24.04+1)
--
-- Uso: pg_dump --schema-only --no-owner --no-privileges pncp_datalake
--
-- ATENCAO: Este arquivo e a representacao fiel do schema REAL do banco
-- no momento da extracao. Nao modificar manualmente. Para regenerar:
--   sudo -u postgres pg_dump --schema-only --no-owner --no-privileges pncp_datalake > supabase/current-schema.sql
-- Ou via script:
--   bash scripts/verify-schema-divergence.sh --refresh
--

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Extensions
--

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;

COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;

COMMENT ON EXTENSION "uuid-ossp" IS 'generate universally unique identifiers (UUIDs)';

--
-- Functions
--

CREATE FUNCTION public.generate_coverage_snapshot(snap_date date DEFAULT CURRENT_DATE) RETURNS integer
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

COMMENT ON FUNCTION public.generate_coverage_snapshot(snap_date date) IS 'Gera snapshot de cobertura para todos as fontes — chamado pelo timer semanal (Story 001.7)';

CREATE FUNCTION public.purge_old_bids(p_retention_days integer DEFAULT 400) RETURNS TABLE(purged_count integer, remaining_count integer)
    LANGUAGE plpgsql
    AS $$
DECLARE
    cutoff_date DATE;
    v_purged INT;
BEGIN
    cutoff_date := CURRENT_DATE - p_retention_days;

    -- Soft-delete old inactive records
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

CREATE FUNCTION public.search_datalake(
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
) RETURNS TABLE(
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

CREATE FUNCTION public.set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE FUNCTION public.update_entity_coverage() RETURNS trigger
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

CREATE FUNCTION public.update_entity_coverage_on_update() RETURNS trigger
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

CREATE FUNCTION public.upsert_pncp_raw_bids(p_records jsonb) RETURNS TABLE(action text, pncp_id text, content_hash text)
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

CREATE FUNCTION public.upsert_pncp_supplier_contracts(p_records jsonb) RETURNS TABLE(result text, id text)
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

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Sequences
--

CREATE SEQUENCE public.coverage_snapshots_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.coverage_snapshots_id_seq OWNED BY public.coverage_snapshots.id;

CREATE SEQUENCE public.ingestion_runs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.ingestion_runs_id_seq OWNED BY public.ingestion_runs.id;

CREATE SEQUENCE public.pncp_supplier_contracts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.pncp_supplier_contracts_id_seq OWNED BY public.pncp_supplier_contracts.id;

CREATE SEQUENCE public.sc_public_entities_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.sc_public_entities_id_seq OWNED BY public.sc_public_entities.id;

--
-- Tables (in dependency order)
--

CREATE TABLE public.coverage_snapshots (
    id integer NOT NULL,
    snapshot_date date DEFAULT CURRENT_DATE NOT NULL,
    source text NOT NULL,
    total_entities integer NOT NULL,
    covered_entities integer NOT NULL,
    pct_covered numeric(5,2) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

COMMENT ON TABLE public.coverage_snapshots IS 'Snapshots semanais de cobertura por fonte — usado para tendencia no relatorio semanal (Story 001.7)';

CREATE TABLE public.enriched_entities (
    cnpj text NOT NULL,
    razao_social text,
    nome_fantasia text,
    cnae_principal text,
    cnae_secundarios text[],
    municipio text,
    uf text,
    codigo_ibge text,
    natureza_juridica text,
    logradouro text,
    bairro text,
    cep text,
    telefone text,
    email text,
    situacao text,
    enriched_at timestamp with time zone DEFAULT now() NOT NULL,
    enriched_source text DEFAULT 'brasilapi'::text NOT NULL
);

CREATE TABLE public.entity_coverage (
    entity_id integer NOT NULL,
    source text NOT NULL,
    last_seen_at timestamp with time zone,
    total_bids integer DEFAULT 0 NOT NULL,
    is_covered boolean DEFAULT false NOT NULL,
    within_200km boolean DEFAULT false NOT NULL
);

CREATE TABLE public.ingestion_checkpoints (
    source text DEFAULT 'pncp'::text NOT NULL,
    scope_key text NOT NULL,
    last_page integer DEFAULT 0 NOT NULL,
    last_date date,
    last_id text,
    records_fetched integer DEFAULT 0 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE public.ingestion_runs (
    id integer NOT NULL,
    source text NOT NULL,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    finished_at timestamp with time zone,
    records_fetched integer DEFAULT 0 NOT NULL,
    records_upserted integer DEFAULT 0 NOT NULL,
    entities_covered integer DEFAULT 0 NOT NULL,
    status text DEFAULT 'running'::text NOT NULL,
    error_message text,
    metadata jsonb
);

CREATE TABLE public.pncp_raw_bids (
    pncp_id text NOT NULL,
    objeto_compra text,
    valor_total_estimado numeric(18,2),
    modalidade_id integer,
    modalidade_nome text,
    esfera_id integer,
    uf text,
    municipio text,
    codigo_municipio_ibge text,
    orgao_razao_social text,
    orgao_cnpj text,
    data_publicacao date,
    data_abertura date,
    data_encerramento date,
    link_pncp text,
    content_hash text,
    tsv tsvector,
    source text DEFAULT 'pncp'::text NOT NULL,
    source_id text,
    matched_entity_id integer,
    ingested_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    is_active boolean DEFAULT true NOT NULL
);

CREATE TABLE public.pncp_supplier_contracts (
    id integer NOT NULL,
    contrato_id text,
    orgao_cnpj text,
    orgao_nome text,
    fornecedor_cnpj text,
    fornecedor_nome text,
    objeto_contrato text,
    valor_total numeric(18,2),
    data_inicio date,
    data_fim date,
    data_publicacao date,
    uf text,
    municipio text,
    source text DEFAULT 'pncp'::text NOT NULL,
    source_id text,
    ingested_at timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE public.sc_public_entities (
    id integer NOT NULL,
    razao_social text NOT NULL,
    cnpj_8 text NOT NULL,
    municipio text,
    codigo_ibge text,
    natureza_juridica text,
    cod_natureza text,
    latitude double precision,
    longitude double precision,
    distancia_fk double precision,
    raio_200km boolean DEFAULT false NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

--
-- Table defaults (serial/sequence columns)
--

ALTER TABLE ONLY public.coverage_snapshots ALTER COLUMN id SET DEFAULT nextval('public.coverage_snapshots_id_seq'::regclass);
ALTER TABLE ONLY public.ingestion_runs ALTER COLUMN id SET DEFAULT nextval('public.ingestion_runs_id_seq'::regclass);
ALTER TABLE ONLY public.pncp_supplier_contracts ALTER COLUMN id SET DEFAULT nextval('public.pncp_supplier_contracts_id_seq'::regclass);
ALTER TABLE ONLY public.sc_public_entities ALTER COLUMN id SET DEFAULT nextval('public.sc_public_entities_id_seq'::regclass);

--
-- Primary keys
--

ALTER TABLE ONLY public.coverage_snapshots
    ADD CONSTRAINT coverage_snapshots_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.enriched_entities
    ADD CONSTRAINT enriched_entities_pkey PRIMARY KEY (cnpj);
ALTER TABLE ONLY public.entity_coverage
    ADD CONSTRAINT entity_coverage_pkey PRIMARY KEY (entity_id, source);
ALTER TABLE ONLY public.ingestion_checkpoints
    ADD CONSTRAINT ingestion_checkpoints_pkey PRIMARY KEY (source, scope_key);
ALTER TABLE ONLY public.ingestion_runs
    ADD CONSTRAINT ingestion_runs_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.pncp_raw_bids
    ADD CONSTRAINT pncp_raw_bids_pkey PRIMARY KEY (pncp_id);
ALTER TABLE ONLY public.pncp_raw_bids
    ADD CONSTRAINT pncp_raw_bids_content_hash_key UNIQUE (content_hash);
ALTER TABLE ONLY public.pncp_supplier_contracts
    ADD CONSTRAINT pncp_supplier_contracts_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.pncp_supplier_contracts
    ADD CONSTRAINT pncp_supplier_contracts_contrato_id_key UNIQUE (contrato_id);
ALTER TABLE ONLY public.sc_public_entities
    ADD CONSTRAINT sc_public_entities_pkey PRIMARY KEY (id);

--
-- Views
--

CREATE VIEW public.v_coverage_gaps AS
 SELECT id,
    razao_social,
    cnpj_8,
    municipio,
    natureza_juridica,
    raio_200km,
    distancia_fk,
    ARRAY( SELECT ec.source
           FROM public.entity_coverage ec
          WHERE ((ec.entity_id = e.id) AND (ec.is_covered = true))) AS fontes_ativas,
    (( SELECT count(DISTINCT ec2.source) AS count
           FROM public.entity_coverage ec2
          WHERE ((ec2.entity_id = e.id) AND (ec2.is_covered = true))) = 0) AS gap_total
   FROM public.sc_public_entities e
  WHERE ((is_active = true) AND (NOT (EXISTS ( SELECT 1
           FROM public.entity_coverage ec
          WHERE ((ec.entity_id = e.id) AND (ec.is_covered = true))))))
  ORDER BY municipio, razao_social;

COMMENT ON VIEW public.v_coverage_gaps IS 'Entes publicos com gap TOTAL de cobertura (is_covered = FALSE em todas as fontes) — Story 001.5/001.7';

CREATE VIEW public.v_coverage_gaps_by_municipio AS
 SELECT municipio,
    count(*) AS total_entes,
    count(*) FILTER (WHERE (NOT (EXISTS ( SELECT 1
           FROM public.entity_coverage ec
          WHERE ((ec.entity_id = e.id) AND (ec.is_covered = true)))))) AS entes_descobertos,
    round(((100.0 * (count(*) FILTER (WHERE (NOT (EXISTS ( SELECT 1
           FROM public.entity_coverage ec
          WHERE ((ec.entity_id = e.id) AND (ec.is_covered = true)))))))::numeric) / (NULLIF(count(*), 0))::numeric), 1) AS pct_gap,
    round(((100.0 * (count(*) FILTER (WHERE (EXISTS ( SELECT 1
           FROM public.entity_coverage ec
          WHERE ((ec.entity_id = e.id) AND (ec.is_covered = true))))))::numeric) / (NULLIF(count(*), 0))::numeric), 1) AS pct_coberto
   FROM public.sc_public_entities e
  WHERE (is_active = true)
  GROUP BY municipio
  ORDER BY (count(*) FILTER (WHERE (NOT (EXISTS ( SELECT 1
           FROM public.entity_coverage ec
          WHERE ((ec.entity_id = e.id) AND (ec.is_covered = true))))))) DESC, (round(((100.0 * (count(*) FILTER (WHERE (NOT (EXISTS ( SELECT 1
           FROM public.entity_coverage ec
          WHERE ((ec.entity_id = e.id) (ec.is_covered = true)))))))::numeric) / (NULLIF(count(*), 0))::numeric), 1)) DESC;

COMMENT ON VIEW public.v_coverage_gaps_by_municipio IS 'Agregacao de gaps de cobertura por municipio — Story 001.5/001.7';

CREATE VIEW public.v_coverage_summary AS
 SELECT source,
    within_200km,
    is_covered,
    count(*) AS entity_count,
    round((((count(*))::numeric * 100.0) / sum(count(*)) OVER (PARTITION BY within_200km)), 1) AS pct
   FROM public.entity_coverage ec
  WHERE (EXISTS ( SELECT 1
           FROM public.sc_public_entities e
          WHERE ((e.id = ec.entity_id) AND (e.is_active = true))))
  GROUP BY source, within_200km, is_covered
  ORDER BY source, within_200km, is_covered;

CREATE VIEW public.v_coverage_trend AS
 SELECT snapshot_date,
    source,
    total_entities,
    covered_entities,
    pct_covered,
    (pct_covered - lag(pct_covered) OVER (PARTITION BY source ORDER BY snapshot_date)) AS variacao_pct,
    row_number() OVER (PARTITION BY source ORDER BY snapshot_date DESC) AS rn_desc
   FROM public.coverage_snapshots
  ORDER BY snapshot_date DESC, source;

COMMENT ON VIEW public.v_coverage_trend IS 'Evolucao semanal da cobertura com calculo de variacao — Story 001.5/001.7';

--
-- Indexes
--

-- pncp_raw_bids indexes
CREATE INDEX idx_bids_active ON public.pncp_raw_bids USING btree (is_active, data_publicacao DESC) WHERE (is_active = true);
CREATE INDEX idx_bids_encerramento ON public.pncp_raw_bids USING btree (data_encerramento) WHERE (data_encerramento IS NOT NULL);
CREATE INDEX idx_bids_esfera ON public.pncp_raw_bids USING btree (esfera_id);
CREATE INDEX idx_bids_ingested ON public.pncp_raw_bids USING btree (ingested_at DESC);
CREATE INDEX idx_bids_matched_entity ON public.pncp_raw_bids USING btree (matched_entity_id) WHERE (matched_entity_id IS NOT NULL);
CREATE INDEX idx_bids_modalidade ON public.pncp_raw_bids USING btree (modalidade_id, data_publicacao DESC);
CREATE INDEX idx_bids_orgao_cnpj ON public.pncp_raw_bids USING btree (orgao_cnpj);
CREATE INDEX idx_bids_orgao_hash ON public.pncp_raw_bids USING btree (orgao_cnpj, content_hash);
CREATE INDEX idx_bids_source ON public.pncp_raw_bids USING btree (source);
CREATE INDEX idx_bids_tsv ON public.pncp_raw_bids USING gin (tsv);
CREATE INDEX idx_bids_uf_data ON public.pncp_raw_bids USING btree (uf, data_publicacao DESC);
CREATE INDEX idx_bids_uf_source ON public.pncp_raw_bids USING btree (uf, source, data_publicacao DESC);
CREATE INDEX idx_bids_valor ON public.pncp_raw_bids USING btree (valor_total_estimado);

-- entity_coverage indexes
CREATE INDEX idx_cov_covered ON public.entity_coverage USING btree (is_covered, within_200km);
CREATE INDEX idx_cov_last_seen ON public.entity_coverage USING btree (last_seen_at);
CREATE INDEX idx_cov_source ON public.entity_coverage USING btree (source, is_covered);

-- coverage_snapshots indexes
CREATE INDEX idx_cov_snap_date ON public.coverage_snapshots USING btree (snapshot_date);
CREATE INDEX idx_cov_snap_source ON public.coverage_snapshots USING btree (source, snapshot_date);

-- enriched_entities indexes
CREATE INDEX idx_ee_enriched_at ON public.enriched_entities USING btree (enriched_at);
CREATE INDEX idx_ee_uf ON public.enriched_entities USING btree (uf);

-- ingestion_runs indexes
CREATE INDEX idx_ir_source_status ON public.ingestion_runs USING btree (source, status);
CREATE INDEX idx_ir_started ON public.ingestion_runs USING btree (started_at DESC);

-- pncp_supplier_contracts indexes
CREATE INDEX idx_psc_data ON public.pncp_supplier_contracts USING btree (data_publicacao DESC);
CREATE INDEX idx_psc_fornecedor ON public.pncp_supplier_contracts USING btree (fornecedor_cnpj, data_publicacao DESC);
CREATE INDEX idx_psc_objeto_trgm ON public.pncp_supplier_contracts USING gin (objeto_contrato public.gin_trgm_ops);
CREATE INDEX idx_psc_orgao ON public.pncp_supplier_contracts USING btree (orgao_cnpj);
CREATE INDEX idx_psc_uf ON public.pncp_supplier_contracts USING btree (uf, data_publicacao DESC);
CREATE INDEX idx_psc_valor ON public.pncp_supplier_contracts USING btree (valor_total);

-- sc_public_entities indexes
CREATE INDEX idx_spe_cnpj ON public.sc_public_entities USING btree (cnpj_8);
CREATE INDEX idx_spe_ibge ON public.sc_public_entities USING btree (codigo_ibge);
CREATE INDEX idx_spe_municipio ON public.sc_public_entities USING btree (municipio);
CREATE INDEX idx_spe_natureza ON public.sc_public_entities USING btree (cod_natureza);
CREATE INDEX idx_spe_raio ON public.sc_public_entities USING btree (raio_200km, is_active);

--
-- Triggers
--

CREATE TRIGGER trg_bids_coverage AFTER INSERT ON public.pncp_raw_bids FOR EACH ROW EXECUTE FUNCTION public.update_entity_coverage();

CREATE TRIGGER trg_bids_coverage_update AFTER UPDATE ON public.pncp_raw_bids FOR EACH ROW EXECUTE FUNCTION public.update_entity_coverage_on_update();

CREATE TRIGGER trg_bids_updated_at BEFORE UPDATE ON public.pncp_raw_bids FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

--
-- Foreign keys
--

ALTER TABLE ONLY public.entity_coverage
    ADD CONSTRAINT entity_coverage_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES public.sc_public_entities(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.pncp_raw_bids
    ADD CONSTRAINT fk_bids_matched_entity FOREIGN KEY (matched_entity_id) REFERENCES public.sc_public_entities(id) ON DELETE SET NULL;
