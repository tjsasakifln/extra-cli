--
-- PostgreSQL database dump
--

\restrict ZcqeckEqSZvl3lvkBJJHRzPkvrauAIuAa5VuBDWa0h8KeWIBu6CeFMmQeqk2axE

-- Dumped from database version 16.4 (Debian 16.4-1.pgdg110+2)
-- Dumped by pg_dump version 18.4 (Ubuntu 18.4-1.pgdg24.04+1)

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
-- Name: pg_trgm; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;


--
-- Name: EXTENSION pg_trgm; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';


--
-- Name: uuid-ossp; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;


--
-- Name: EXTENSION "uuid-ossp"; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION "uuid-ossp" IS 'generate universally unique identifiers (UUIDs)';


--
-- Name: generate_coverage_snapshot(date); Type: FUNCTION; Schema: public; Owner: test
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


ALTER FUNCTION public.generate_coverage_snapshot(snap_date date) OWNER TO test;

--
-- Name: FUNCTION generate_coverage_snapshot(snap_date date); Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON FUNCTION public.generate_coverage_snapshot(snap_date date) IS 'Gera snapshot de cobertura para todos as fontes — chamado pelo timer semanal (Story 001.7)';


--
-- Name: purge_old_bids(integer); Type: FUNCTION; Schema: public; Owner: test
--

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


ALTER FUNCTION public.purge_old_bids(p_retention_days integer) OWNER TO test;

--
-- Name: search_datalake(text[], date, date, text, integer[], numeric, numeric, integer[], text[], integer); Type: FUNCTION; Schema: public; Owner: test
--

CREATE FUNCTION public.search_datalake(p_ufs text[] DEFAULT NULL::text[], p_date_start date DEFAULT NULL::date, p_date_end date DEFAULT NULL::date, p_tsquery text DEFAULT NULL::text, p_modalidades integer[] DEFAULT NULL::integer[], p_valor_min numeric DEFAULT NULL::numeric, p_valor_max numeric DEFAULT NULL::numeric, p_esferas integer[] DEFAULT NULL::integer[], p_sources text[] DEFAULT NULL::text[], p_limit integer DEFAULT 100) RETURNS TABLE(pncp_id text, objeto_compra text, valor_total_estimado numeric, modalidade_nome text, uf text, municipio text, orgao_razao_social text, orgao_cnpj text, data_publicacao date, data_encerramento date, link_pncp text, source text, rank real)
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


ALTER FUNCTION public.search_datalake(p_ufs text[], p_date_start date, p_date_end date, p_tsquery text, p_modalidades integer[], p_valor_min numeric, p_valor_max numeric, p_esferas integer[], p_sources text[], p_limit integer) OWNER TO test;

--
-- Name: set_updated_at(); Type: FUNCTION; Schema: public; Owner: test
--

CREATE FUNCTION public.set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.set_updated_at() OWNER TO test;

--
-- Name: ttl_cleanup_enriched_entities(integer); Type: FUNCTION; Schema: public; Owner: test
--

CREATE FUNCTION public.ttl_cleanup_enriched_entities(p_ttl_days integer DEFAULT 90) RETURNS integer
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_deleted INT;
BEGIN
    -- Validacao do parametro (COALESCE para tratar NULL)
    IF COALESCE(p_ttl_days, 0) < 1 THEN
        RAISE EXCEPTION 'p_ttl_days must be >= 1, got %', p_ttl_days;
    END IF;

    DELETE FROM enriched_entities
    WHERE enriched_at < CURRENT_DATE - p_ttl_days;

    GET DIAGNOSTICS v_deleted = ROW_COUNT;

    -- Log da operacao (via RAISE NOTICE para visibilidade em logs do cron)
    RAISE NOTICE 'TTL cleanup: removed % expired records from enriched_entities (TTL=% days)',
        v_deleted, p_ttl_days;

    RETURN v_deleted;
END;
$$;


ALTER FUNCTION public.ttl_cleanup_enriched_entities(p_ttl_days integer) OWNER TO test;

--
-- Name: FUNCTION ttl_cleanup_enriched_entities(p_ttl_days integer); Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON FUNCTION public.ttl_cleanup_enriched_entities(p_ttl_days integer) IS 'TD-DB-03: Remove registros expirados de enriched_entities baseado em enriched_at + TTL configurado (default 90 dias)';


--
-- Name: update_entity_coverage(); Type: FUNCTION; Schema: public; Owner: test
--

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
            last_seen_at = GREATEST(
                COALESCE(entity_coverage.last_seen_at, '1970-01-01'::date),
                COALESCE(NEW.data_publicacao, '1970-01-01'::date)
            ),
            total_bids = entity_coverage.total_bids + 1,
            is_covered = (
                GREATEST(
                    COALESCE(entity_coverage.last_seen_at, '1970-01-01'::date),
                    COALESCE(NEW.data_publicacao, '1970-01-01'::date)
                ) >= CURRENT_DATE - 90
            );
    END IF;
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.update_entity_coverage() OWNER TO test;

--
-- Name: update_entity_coverage_on_update(); Type: FUNCTION; Schema: public; Owner: test
--

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
            last_seen_at = GREATEST(
                COALESCE(entity_coverage.last_seen_at, '1970-01-01'::date),
                COALESCE(NEW.data_publicacao, '1970-01-01'::date)
            ),
            total_bids = entity_coverage.total_bids + 1,
            is_covered = (
                GREATEST(
                    COALESCE(entity_coverage.last_seen_at, '1970-01-01'::date),
                    COALESCE(NEW.data_publicacao, '1970-01-01'::date)
                ) >= CURRENT_DATE - 90
            );
    END IF;
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.update_entity_coverage_on_update() OWNER TO test;

--
-- Name: upsert_pncp_raw_bids(jsonb); Type: FUNCTION; Schema: public; Owner: test
--

CREATE FUNCTION public.upsert_pncp_raw_bids(p_records jsonb) RETURNS TABLE(action text, pncp_id text, content_hash text)
    LANGUAGE plpgsql
    AS $$
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


ALTER FUNCTION public.upsert_pncp_raw_bids(p_records jsonb) OWNER TO test;

--
-- Name: upsert_pncp_supplier_contracts(jsonb); Type: FUNCTION; Schema: public; Owner: test
--

CREATE FUNCTION public.upsert_pncp_supplier_contracts(p_records jsonb) RETURNS TABLE(action text, contrato_id text)
    LANGUAGE plpgsql
    AS $$
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


ALTER FUNCTION public.upsert_pncp_supplier_contracts(p_records jsonb) OWNER TO test;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: _migrations; Type: TABLE; Schema: public; Owner: test
--

CREATE TABLE public._migrations (
    version text NOT NULL,
    name text NOT NULL,
    checksum text NOT NULL,
    applied_at timestamp with time zone DEFAULT now() NOT NULL,
    status text DEFAULT 'applied'::text NOT NULL,
    error_msg text,
    rollback_sql text
);


ALTER TABLE public._migrations OWNER TO test;

--
-- Name: TABLE _migrations; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON TABLE public._migrations IS 'Migration ledger — tracks every applied migration with checksums';


--
-- Name: coverage_snapshots; Type: TABLE; Schema: public; Owner: test
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


ALTER TABLE public.coverage_snapshots OWNER TO test;

--
-- Name: TABLE coverage_snapshots; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON TABLE public.coverage_snapshots IS 'Snapshots semanais de cobertura por fonte — usado para tendencia no relatorio semanal (Story 001.7)';


--
-- Name: coverage_snapshots_id_seq; Type: SEQUENCE; Schema: public; Owner: test
--

CREATE SEQUENCE public.coverage_snapshots_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.coverage_snapshots_id_seq OWNER TO test;

--
-- Name: coverage_snapshots_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: test
--

ALTER SEQUENCE public.coverage_snapshots_id_seq OWNED BY public.coverage_snapshots.id;


--
-- Name: enriched_entities; Type: TABLE; Schema: public; Owner: test
--

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


ALTER TABLE public.enriched_entities OWNER TO test;

--
-- Name: entity_coverage; Type: TABLE; Schema: public; Owner: test
--

CREATE TABLE public.entity_coverage (
    entity_id integer NOT NULL,
    source text NOT NULL,
    last_seen_at timestamp with time zone,
    total_bids integer DEFAULT 0 NOT NULL,
    is_covered boolean DEFAULT false NOT NULL,
    within_200km boolean DEFAULT false NOT NULL
);


ALTER TABLE public.entity_coverage OWNER TO test;

--
-- Name: ingestion_checkpoints; Type: TABLE; Schema: public; Owner: test
--

CREATE TABLE public.ingestion_checkpoints (
    source text DEFAULT 'pncp'::text NOT NULL,
    scope_key text NOT NULL,
    last_page integer DEFAULT 0 NOT NULL,
    last_date date,
    last_id text,
    records_fetched integer DEFAULT 0 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.ingestion_checkpoints OWNER TO test;

--
-- Name: ingestion_runs; Type: TABLE; Schema: public; Owner: test
--

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


ALTER TABLE public.ingestion_runs OWNER TO test;

--
-- Name: ingestion_runs_id_seq; Type: SEQUENCE; Schema: public; Owner: test
--

CREATE SEQUENCE public.ingestion_runs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.ingestion_runs_id_seq OWNER TO test;

--
-- Name: ingestion_runs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: test
--

ALTER SEQUENCE public.ingestion_runs_id_seq OWNED BY public.ingestion_runs.id;


--
-- Name: opportunity_checkpoints; Type: TABLE; Schema: public; Owner: test
--

CREATE TABLE public.opportunity_checkpoints (
    id bigint NOT NULL,
    source text NOT NULL,
    scope_key text NOT NULL,
    last_page integer DEFAULT 0,
    records_fetched integer DEFAULT 0,
    pages_expected integer,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    scope_complete boolean DEFAULT false,
    completion_reason text
);


ALTER TABLE public.opportunity_checkpoints OWNER TO test;

--
-- Name: opportunity_checkpoints_id_seq; Type: SEQUENCE; Schema: public; Owner: test
--

CREATE SEQUENCE public.opportunity_checkpoints_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.opportunity_checkpoints_id_seq OWNER TO test;

--
-- Name: opportunity_checkpoints_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: test
--

ALTER SEQUENCE public.opportunity_checkpoints_id_seq OWNED BY public.opportunity_checkpoints.id;


--
-- Name: opportunity_intel; Type: TABLE; Schema: public; Owner: test
--

CREATE TABLE public.opportunity_intel (
    id bigint NOT NULL,
    source text NOT NULL,
    source_id text NOT NULL,
    source_url text,
    content_hash text NOT NULL,
    numero_controle_pncp text,
    crawl_batch_id text,
    run_id bigint,
    ingested_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    first_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    last_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    orgao_cnpj text,
    orgao_nome text,
    ente_federativo text,
    uf text NOT NULL,
    municipio text,
    codigo_ibge text,
    numero_processo text,
    numero_edital text,
    modalidade text,
    modalidade_id integer,
    objeto text NOT NULL,
    categoria text,
    valor_estimado numeric(18,2),
    valor_homologado numeric(18,2),
    valor_semantica text,
    data_publicacao timestamp with time zone,
    data_abertura timestamp with time zone,
    data_encerramento timestamp with time zone,
    data_homologacao timestamp with time zone,
    status_fonte text,
    status_canonico text DEFAULT 'unknown'::text NOT NULL,
    status_motivo text,
    status_data timestamp with time zone,
    link_edital text,
    link_anexos text[],
    qualidade_score integer DEFAULT 0,
    qualidade_fatores jsonb DEFAULT '{}'::jsonb,
    dados_ausentes text[],
    ranking text DEFAULT 'REVIEW'::text,
    ranking_score integer DEFAULT 0,
    ranking_fatores jsonb DEFAULT '{}'::jsonb,
    ranking_regras text[],
    ranking_confianca text DEFAULT 'MEDIUM'::text,
    proveniencia jsonb DEFAULT '{}'::jsonb,
    is_active boolean DEFAULT true NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb,
    source_active boolean DEFAULT true NOT NULL,
    source_inactive_at timestamp with time zone,
    source_inactive_reason text,
    last_seen_source_run_id bigint,
    last_status_verified_at timestamp with time zone,
    last_status_verified_by text,
    source_active_changes jsonb DEFAULT '[]'::jsonb NOT NULL,
    CONSTRAINT ck_oi_qualidade_score CHECK (((qualidade_score >= 0) AND (qualidade_score <= 100))),
    CONSTRAINT ck_oi_ranking CHECK ((ranking = ANY (ARRAY['GO'::text, 'REVIEW'::text, 'NO_GO'::text]))),
    CONSTRAINT ck_oi_ranking_confianca CHECK ((ranking_confianca = ANY (ARRAY['HIGH'::text, 'MEDIUM'::text, 'LOW'::text]))),
    CONSTRAINT ck_oi_ranking_score CHECK (((ranking_score >= 0) AND (ranking_score <= 100))),
    CONSTRAINT ck_oi_status_canonico CHECK ((status_canonico = ANY (ARRAY['open'::text, 'upcoming'::text, 'closed'::text, 'suspended'::text, 'revoked'::text, 'annulled'::text, 'failed'::text, 'unknown'::text])))
);


ALTER TABLE public.opportunity_intel OWNER TO test;

--
-- Name: opportunity_intel_id_seq; Type: SEQUENCE; Schema: public; Owner: test
--

CREATE SEQUENCE public.opportunity_intel_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.opportunity_intel_id_seq OWNER TO test;

--
-- Name: opportunity_intel_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: test
--

ALTER SEQUENCE public.opportunity_intel_id_seq OWNED BY public.opportunity_intel.id;


--
-- Name: opportunity_runs; Type: TABLE; Schema: public; Owner: test
--

CREATE TABLE public.opportunity_runs (
    id bigint NOT NULL,
    source text NOT NULL,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    finished_at timestamp with time zone,
    status text DEFAULT 'running'::text NOT NULL,
    mode text DEFAULT 'incremental'::text NOT NULL,
    date_from date,
    date_to date,
    records_fetched integer DEFAULT 0,
    records_new integer DEFAULT 0,
    records_updated integer DEFAULT 0,
    records_skipped integer DEFAULT 0,
    error text,
    metadata jsonb DEFAULT '{}'::jsonb,
    error_message text,
    checkpoint_id bigint,
    pages_fetched integer DEFAULT 0,
    scope text DEFAULT 'incremental'::text,
    scope_key text,
    pages_processed integer DEFAULT 0,
    pages_expected integer,
    records_expected integer,
    scope_complete boolean DEFAULT false,
    completion_reason text
);


ALTER TABLE public.opportunity_runs OWNER TO test;

--
-- Name: opportunity_runs_id_seq; Type: SEQUENCE; Schema: public; Owner: test
--

CREATE SEQUENCE public.opportunity_runs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.opportunity_runs_id_seq OWNER TO test;

--
-- Name: opportunity_runs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: test
--

ALTER SEQUENCE public.opportunity_runs_id_seq OWNED BY public.opportunity_runs.id;


--
-- Name: pncp_raw_bids; Type: TABLE; Schema: public; Owner: test
--

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
    is_active boolean DEFAULT true NOT NULL,
    match_method text,
    match_score numeric(4,3),
    match_confidence text
);


ALTER TABLE public.pncp_raw_bids OWNER TO test;

--
-- Name: COLUMN pncp_raw_bids.match_method; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON COLUMN public.pncp_raw_bids.match_method IS 'Estrategia de matching: cnpj | name_normalized | fuzzy | unmatched';


--
-- Name: COLUMN pncp_raw_bids.match_score; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON COLUMN public.pncp_raw_bids.match_score IS 'Score do match (0.000-1.000). 1.000 = exact match.';


--
-- Name: COLUMN pncp_raw_bids.match_confidence; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON COLUMN public.pncp_raw_bids.match_confidence IS 'Confianca: high (>=0.95) | medium (>=threshold) | low (<threshold)';


--
-- Name: pncp_supplier_contracts; Type: TABLE; Schema: public; Owner: test
--

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
    ingested_at timestamp with time zone DEFAULT now() NOT NULL,
    is_active boolean DEFAULT true NOT NULL
);


ALTER TABLE public.pncp_supplier_contracts OWNER TO test;

--
-- Name: pncp_supplier_contracts_id_seq; Type: SEQUENCE; Schema: public; Owner: test
--

CREATE SEQUENCE public.pncp_supplier_contracts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.pncp_supplier_contracts_id_seq OWNER TO test;

--
-- Name: pncp_supplier_contracts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: test
--

ALTER SEQUENCE public.pncp_supplier_contracts_id_seq OWNED BY public.pncp_supplier_contracts.id;


--
-- Name: sc_public_entities; Type: TABLE; Schema: public; Owner: test
--

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


ALTER TABLE public.sc_public_entities OWNER TO test;

--
-- Name: sc_public_entities_id_seq; Type: SEQUENCE; Schema: public; Owner: test
--

CREATE SEQUENCE public.sc_public_entities_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sc_public_entities_id_seq OWNER TO test;

--
-- Name: sc_public_entities_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: test
--

ALTER SEQUENCE public.sc_public_entities_id_seq OWNED BY public.sc_public_entities.id;


--
-- Name: v_coverage_gaps; Type: VIEW; Schema: public; Owner: test
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


ALTER VIEW public.v_coverage_gaps OWNER TO test;

--
-- Name: VIEW v_coverage_gaps; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON VIEW public.v_coverage_gaps IS 'Entes publicos com gap TOTAL de cobertura (is_covered = FALSE em todas as fontes) — Story 001.5/001.7';


--
-- Name: v_coverage_gaps_by_municipio; Type: VIEW; Schema: public; Owner: test
--

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
          WHERE ((ec.entity_id = e.id) AND (ec.is_covered = true)))))))::numeric) / (NULLIF(count(*), 0))::numeric), 1)) DESC;


ALTER VIEW public.v_coverage_gaps_by_municipio OWNER TO test;

--
-- Name: VIEW v_coverage_gaps_by_municipio; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON VIEW public.v_coverage_gaps_by_municipio IS 'Agregacao de gaps de cobertura por municipio — Story 001.5/001.7';


--
-- Name: v_coverage_summary; Type: VIEW; Schema: public; Owner: test
--

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


ALTER VIEW public.v_coverage_summary OWNER TO test;

--
-- Name: v_coverage_trend; Type: VIEW; Schema: public; Owner: test
--

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


ALTER VIEW public.v_coverage_trend OWNER TO test;

--
-- Name: VIEW v_coverage_trend; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON VIEW public.v_coverage_trend IS 'Evolucao semanal da cobertura com calculo de variacao — Story 001.5/001.7';


--
-- Name: v_opportunity_coverage_summary; Type: VIEW; Schema: public; Owner: test
--

CREATE VIEW public.v_opportunity_coverage_summary AS
 SELECT uf,
    count(*) AS total_opportunities,
    count(
        CASE
            WHEN (status_canonico = 'open'::text) THEN 1
            ELSE NULL::integer
        END) AS open_count,
    count(
        CASE
            WHEN (status_canonico = 'upcoming'::text) THEN 1
            ELSE NULL::integer
        END) AS upcoming_count,
    count(
        CASE
            WHEN (status_canonico = 'closed'::text) THEN 1
            ELSE NULL::integer
        END) AS closed_count,
    count(DISTINCT municipio) AS municipios_cobertos,
    count(DISTINCT orgao_cnpj) AS orgaos_distintos
   FROM public.opportunity_intel
  WHERE (is_active = true)
  GROUP BY uf;


ALTER VIEW public.v_opportunity_coverage_summary OWNER TO test;

--
-- Name: v_unmatched_bids; Type: VIEW; Schema: public; Owner: test
--

CREATE VIEW public.v_unmatched_bids AS
 SELECT pncp_id,
    source,
    orgao_cnpj,
    orgao_razao_social,
    municipio,
    codigo_municipio_ibge,
    data_publicacao,
    match_method,
    match_score,
    match_confidence,
    ingested_at,
        CASE
            WHEN ((orgao_cnpj IS NOT NULL) AND (orgao_cnpj <> ''::text)) THEN 'has_cnpj'::text
            ELSE 'name_only'::text
        END AS match_opportunity,
        CASE
            WHEN (data_publicacao >= (CURRENT_DATE - 90)) THEN 'recent'::text
            ELSE 'historical'::text
        END AS recency
   FROM public.pncp_raw_bids
  WHERE ((matched_entity_id IS NULL) AND (((orgao_cnpj IS NOT NULL) AND (orgao_cnpj <> ''::text)) OR ((orgao_razao_social IS NOT NULL) AND (orgao_razao_social <> ''::text))))
  ORDER BY data_publicacao DESC NULLS LAST, ingested_at DESC;


ALTER VIEW public.v_unmatched_bids OWNER TO test;

--
-- Name: VIEW v_unmatched_bids; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON VIEW public.v_unmatched_bids IS 'Bids sem matched_entity_id — para debugging do entity name-matching (Story 001.3)';


--
-- Name: COLUMN v_unmatched_bids.match_opportunity; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON COLUMN public.v_unmatched_bids.match_opportunity IS 'Indica se o bid tem CNPJ (has_cnpj) ou apenas nome (name_only) para match';


--
-- Name: COLUMN v_unmatched_bids.recency; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON COLUMN public.v_unmatched_bids.recency IS 'Indica se o bid e recente (90 dias) ou historico';


--
-- Name: coverage_snapshots id; Type: DEFAULT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.coverage_snapshots ALTER COLUMN id SET DEFAULT nextval('public.coverage_snapshots_id_seq'::regclass);


--
-- Name: ingestion_runs id; Type: DEFAULT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.ingestion_runs ALTER COLUMN id SET DEFAULT nextval('public.ingestion_runs_id_seq'::regclass);


--
-- Name: opportunity_checkpoints id; Type: DEFAULT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.opportunity_checkpoints ALTER COLUMN id SET DEFAULT nextval('public.opportunity_checkpoints_id_seq'::regclass);


--
-- Name: opportunity_intel id; Type: DEFAULT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.opportunity_intel ALTER COLUMN id SET DEFAULT nextval('public.opportunity_intel_id_seq'::regclass);


--
-- Name: opportunity_runs id; Type: DEFAULT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.opportunity_runs ALTER COLUMN id SET DEFAULT nextval('public.opportunity_runs_id_seq'::regclass);


--
-- Name: pncp_supplier_contracts id; Type: DEFAULT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.pncp_supplier_contracts ALTER COLUMN id SET DEFAULT nextval('public.pncp_supplier_contracts_id_seq'::regclass);


--
-- Name: sc_public_entities id; Type: DEFAULT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.sc_public_entities ALTER COLUMN id SET DEFAULT nextval('public.sc_public_entities_id_seq'::regclass);


--
-- Name: _migrations _migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public._migrations
    ADD CONSTRAINT _migrations_pkey PRIMARY KEY (version);


--
-- Name: enriched_entities chk_ee_cnpj_not_empty; Type: CHECK CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE public.enriched_entities
    ADD CONSTRAINT chk_ee_cnpj_not_empty CHECK ((cnpj <> ''::text)) NOT VALID;


--
-- Name: CONSTRAINT chk_ee_cnpj_not_empty ON enriched_entities; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON CONSTRAINT chk_ee_cnpj_not_empty ON public.enriched_entities IS 'TD-DB-03: CNPJ nao pode ser string vazia';


--
-- Name: enriched_entities chk_ee_enriched_at_not_future; Type: CHECK CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE public.enriched_entities
    ADD CONSTRAINT chk_ee_enriched_at_not_future CHECK ((enriched_at <= (now() + '01:00:00'::interval))) NOT VALID;


--
-- Name: CONSTRAINT chk_ee_enriched_at_not_future ON enriched_entities; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON CONSTRAINT chk_ee_enriched_at_not_future ON public.enriched_entities IS 'TD-DB-03: enriched_at nao pode estar no futuro (tolerancia de 1h para fuso)';


--
-- Name: enriched_entities chk_ee_enriched_source_not_empty; Type: CHECK CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE public.enriched_entities
    ADD CONSTRAINT chk_ee_enriched_source_not_empty CHECK ((enriched_source <> ''::text)) NOT VALID;


--
-- Name: CONSTRAINT chk_ee_enriched_source_not_empty ON enriched_entities; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON CONSTRAINT chk_ee_enriched_source_not_empty ON public.enriched_entities IS 'TD-DB-03: enriched_source nao pode ser string vazia';


--
-- Name: coverage_snapshots coverage_snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.coverage_snapshots
    ADD CONSTRAINT coverage_snapshots_pkey PRIMARY KEY (id);


--
-- Name: enriched_entities enriched_entities_pkey; Type: CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.enriched_entities
    ADD CONSTRAINT enriched_entities_pkey PRIMARY KEY (cnpj);


--
-- Name: entity_coverage entity_coverage_pkey; Type: CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.entity_coverage
    ADD CONSTRAINT entity_coverage_pkey PRIMARY KEY (entity_id, source);


--
-- Name: ingestion_checkpoints ingestion_checkpoints_pkey; Type: CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.ingestion_checkpoints
    ADD CONSTRAINT ingestion_checkpoints_pkey PRIMARY KEY (source, scope_key);


--
-- Name: ingestion_runs ingestion_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.ingestion_runs
    ADD CONSTRAINT ingestion_runs_pkey PRIMARY KEY (id);


--
-- Name: opportunity_checkpoints opportunity_checkpoints_pkey; Type: CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.opportunity_checkpoints
    ADD CONSTRAINT opportunity_checkpoints_pkey PRIMARY KEY (id);


--
-- Name: opportunity_checkpoints opportunity_checkpoints_source_scope_key_key; Type: CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.opportunity_checkpoints
    ADD CONSTRAINT opportunity_checkpoints_source_scope_key_key UNIQUE (source, scope_key);


--
-- Name: opportunity_intel opportunity_intel_pkey; Type: CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.opportunity_intel
    ADD CONSTRAINT opportunity_intel_pkey PRIMARY KEY (id);


--
-- Name: opportunity_runs opportunity_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.opportunity_runs
    ADD CONSTRAINT opportunity_runs_pkey PRIMARY KEY (id);


--
-- Name: pncp_raw_bids pncp_raw_bids_content_hash_key; Type: CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.pncp_raw_bids
    ADD CONSTRAINT pncp_raw_bids_content_hash_key UNIQUE (content_hash);


--
-- Name: pncp_raw_bids pncp_raw_bids_pkey; Type: CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.pncp_raw_bids
    ADD CONSTRAINT pncp_raw_bids_pkey PRIMARY KEY (pncp_id);


--
-- Name: pncp_supplier_contracts pncp_supplier_contracts_contrato_id_key; Type: CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.pncp_supplier_contracts
    ADD CONSTRAINT pncp_supplier_contracts_contrato_id_key UNIQUE (contrato_id);


--
-- Name: pncp_supplier_contracts pncp_supplier_contracts_pkey; Type: CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.pncp_supplier_contracts
    ADD CONSTRAINT pncp_supplier_contracts_pkey PRIMARY KEY (id);


--
-- Name: sc_public_entities sc_public_entities_pkey; Type: CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.sc_public_entities
    ADD CONSTRAINT sc_public_entities_pkey PRIMARY KEY (id);


--
-- Name: idx_bids_active; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_bids_active ON public.pncp_raw_bids USING btree (is_active, data_publicacao DESC) WHERE (is_active = true);


--
-- Name: idx_bids_encerramento; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_bids_encerramento ON public.pncp_raw_bids USING btree (data_encerramento) WHERE (data_encerramento IS NOT NULL);


--
-- Name: idx_bids_esfera; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_bids_esfera ON public.pncp_raw_bids USING btree (esfera_id);


--
-- Name: idx_bids_ingested; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_bids_ingested ON public.pncp_raw_bids USING btree (ingested_at DESC);


--
-- Name: idx_bids_match_coverage; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_bids_match_coverage ON public.pncp_raw_bids USING btree (match_method, matched_entity_id) WHERE (matched_entity_id IS NOT NULL);


--
-- Name: idx_bids_match_method; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_bids_match_method ON public.pncp_raw_bids USING btree (match_method) WHERE (match_method IS NOT NULL);


--
-- Name: idx_bids_matched_entity; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_bids_matched_entity ON public.pncp_raw_bids USING btree (matched_entity_id) WHERE (matched_entity_id IS NOT NULL);


--
-- Name: idx_bids_modalidade; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_bids_modalidade ON public.pncp_raw_bids USING btree (modalidade_id, data_publicacao DESC);


--
-- Name: idx_bids_orgao_cnpj; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_bids_orgao_cnpj ON public.pncp_raw_bids USING btree (orgao_cnpj);


--
-- Name: idx_bids_orgao_hash; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_bids_orgao_hash ON public.pncp_raw_bids USING btree (orgao_cnpj, content_hash);


--
-- Name: idx_bids_source; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_bids_source ON public.pncp_raw_bids USING btree (source);


--
-- Name: idx_bids_tsv; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_bids_tsv ON public.pncp_raw_bids USING gin (tsv);


--
-- Name: idx_bids_uf_data; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_bids_uf_data ON public.pncp_raw_bids USING btree (uf, data_publicacao DESC);


--
-- Name: idx_bids_uf_source; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_bids_uf_source ON public.pncp_raw_bids USING btree (uf, source, data_publicacao DESC);


--
-- Name: idx_bids_valor; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_bids_valor ON public.pncp_raw_bids USING btree (valor_total_estimado);


--
-- Name: idx_cov_covered; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_cov_covered ON public.entity_coverage USING btree (is_covered, within_200km);


--
-- Name: idx_cov_last_seen; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_cov_last_seen ON public.entity_coverage USING btree (last_seen_at);


--
-- Name: idx_cov_snap_date; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_cov_snap_date ON public.coverage_snapshots USING btree (snapshot_date);


--
-- Name: idx_cov_snap_source; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_cov_snap_source ON public.coverage_snapshots USING btree (source, snapshot_date);


--
-- Name: idx_cov_source; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_cov_source ON public.entity_coverage USING btree (source, is_covered);


--
-- Name: idx_ee_enriched_at; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_ee_enriched_at ON public.enriched_entities USING btree (enriched_at);


--
-- Name: idx_ee_uf; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_ee_uf ON public.enriched_entities USING btree (uf);


--
-- Name: idx_ir_source_status; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_ir_source_status ON public.ingestion_runs USING btree (source, status);


--
-- Name: idx_ir_started; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_ir_started ON public.ingestion_runs USING btree (started_at DESC);


--
-- Name: idx_oi_data_abertura; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_oi_data_abertura ON public.opportunity_intel USING btree (data_abertura);


--
-- Name: idx_oi_data_encerramento; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_oi_data_encerramento ON public.opportunity_intel USING btree (data_encerramento);


--
-- Name: idx_oi_is_active; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_oi_is_active ON public.opportunity_intel USING btree (is_active);


--
-- Name: idx_oi_ranking; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_oi_ranking ON public.opportunity_intel USING btree (ranking);


--
-- Name: idx_oi_ranking_score; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_oi_ranking_score ON public.opportunity_intel USING btree (ranking, ranking_score DESC);


--
-- Name: idx_oi_source; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_oi_source ON public.opportunity_intel USING btree (source);


--
-- Name: idx_oi_source_id; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_oi_source_id ON public.opportunity_intel USING btree (source, source_id);


--
-- Name: idx_oi_status_canonico; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_oi_status_canonico ON public.opportunity_intel USING btree (status_canonico);


--
-- Name: idx_oi_uf; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_oi_uf ON public.opportunity_intel USING btree (uf);


--
-- Name: idx_oi_uf_status; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_oi_uf_status ON public.opportunity_intel USING btree (uf, status_canonico);


--
-- Name: idx_psc_data; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_psc_data ON public.pncp_supplier_contracts USING btree (data_publicacao DESC);


--
-- Name: idx_psc_fornecedor; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_psc_fornecedor ON public.pncp_supplier_contracts USING btree (fornecedor_cnpj, data_publicacao DESC);


--
-- Name: idx_psc_objeto_contrato_gin; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_psc_objeto_contrato_gin ON public.pncp_supplier_contracts USING gin (objeto_contrato public.gin_trgm_ops) WHERE (is_active = true);


--
-- Name: INDEX idx_psc_objeto_contrato_gin; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON INDEX public.idx_psc_objeto_contrato_gin IS 'TD-DB-08: GIN trigram index on objeto_contrato for fast textual search (Story TD-1.1)';


--
-- Name: idx_psc_objeto_trgm; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_psc_objeto_trgm ON public.pncp_supplier_contracts USING gin (objeto_contrato public.gin_trgm_ops);


--
-- Name: idx_psc_orgao; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_psc_orgao ON public.pncp_supplier_contracts USING btree (orgao_cnpj);


--
-- Name: idx_psc_uf; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_psc_uf ON public.pncp_supplier_contracts USING btree (uf, data_publicacao DESC);


--
-- Name: idx_psc_valor; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_psc_valor ON public.pncp_supplier_contracts USING btree (valor_total);


--
-- Name: idx_spe_cnpj; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_spe_cnpj ON public.sc_public_entities USING btree (cnpj_8);


--
-- Name: idx_spe_cnpj_unique; Type: INDEX; Schema: public; Owner: test
--

CREATE UNIQUE INDEX idx_spe_cnpj_unique ON public.sc_public_entities USING btree (cnpj_8);


--
-- Name: idx_spe_ibge; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_spe_ibge ON public.sc_public_entities USING btree (codigo_ibge);


--
-- Name: idx_spe_municipio; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_spe_municipio ON public.sc_public_entities USING btree (municipio);


--
-- Name: idx_spe_natureza; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_spe_natureza ON public.sc_public_entities USING btree (cod_natureza);


--
-- Name: idx_spe_raio; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_spe_raio ON public.sc_public_entities USING btree (raio_200km, is_active);


--
-- Name: uq_oi_content_hash; Type: INDEX; Schema: public; Owner: test
--

CREATE UNIQUE INDEX uq_oi_content_hash ON public.opportunity_intel USING btree (content_hash);


--
-- Name: pncp_raw_bids trg_bids_coverage; Type: TRIGGER; Schema: public; Owner: test
--

CREATE TRIGGER trg_bids_coverage AFTER INSERT ON public.pncp_raw_bids FOR EACH ROW EXECUTE FUNCTION public.update_entity_coverage();


--
-- Name: pncp_raw_bids trg_bids_coverage_update; Type: TRIGGER; Schema: public; Owner: test
--

CREATE TRIGGER trg_bids_coverage_update AFTER UPDATE ON public.pncp_raw_bids FOR EACH ROW EXECUTE FUNCTION public.update_entity_coverage_on_update();


--
-- Name: pncp_raw_bids trg_bids_updated_at; Type: TRIGGER; Schema: public; Owner: test
--

CREATE TRIGGER trg_bids_updated_at BEFORE UPDATE ON public.pncp_raw_bids FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: entity_coverage entity_coverage_entity_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.entity_coverage
    ADD CONSTRAINT entity_coverage_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES public.sc_public_entities(id) ON DELETE CASCADE;


--
-- Name: pncp_raw_bids fk_bids_matched_entity; Type: FK CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.pncp_raw_bids
    ADD CONSTRAINT fk_bids_matched_entity FOREIGN KEY (matched_entity_id) REFERENCES public.sc_public_entities(id) ON DELETE SET NULL;


--
-- Name: opportunity_intel fk_oi_run_id; Type: FK CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.opportunity_intel
    ADD CONSTRAINT fk_oi_run_id FOREIGN KEY (run_id) REFERENCES public.opportunity_runs(id) ON DELETE SET NULL;


--
-- PostgreSQL database dump complete
--

\unrestrict ZcqeckEqSZvl3lvkBJJHRzPkvrauAIuAa5VuBDWa0h8KeWIBu6CeFMmQeqk2axE

