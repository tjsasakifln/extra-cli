--
-- PostgreSQL database dump
--

\restrict smZnMxUC7BX8xGUQA3b2YBIXvLch7ZUsJaIF2eekmoOaYYnqClYfBk4mlzoDy5e

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
-- Name: public; Type: SCHEMA; Schema: -; Owner: test
--

-- *not* creating schema, since initdb creates it


ALTER SCHEMA public OWNER TO test;

--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: test
--

COMMENT ON SCHEMA public IS '';


--
-- Name: tiger; Type: SCHEMA; Schema: -; Owner: test
--

CREATE SCHEMA tiger;


ALTER SCHEMA tiger OWNER TO test;

--
-- Name: tiger_data; Type: SCHEMA; Schema: -; Owner: test
--

CREATE SCHEMA tiger_data;


ALTER SCHEMA tiger_data OWNER TO test;

--
-- Name: topology; Type: SCHEMA; Schema: -; Owner: test
--

CREATE SCHEMA topology;


ALTER SCHEMA topology OWNER TO test;

--
-- Name: SCHEMA topology; Type: COMMENT; Schema: -; Owner: test
--

COMMENT ON SCHEMA topology IS 'PostGIS Topology schema';


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
-- Name: evidence_state; Type: TYPE; Schema: public; Owner: test
--

CREATE TYPE public.evidence_state AS ENUM (
    'success_with_data',
    'success_zero',
    'partial',
    'connection_failed',
    'auth_failed',
    'parse_failed',
    'transform_failed',
    'persist_failed',
    'not_applicable',
    'not_investigated',
    'success',
    'error',
    'pending',
    'stale',
    'blocked'
);


ALTER TYPE public.evidence_state OWNER TO test;

--
-- Name: fn_cap_coverage_updated_at(); Type: FUNCTION; Schema: public; Owner: test
--

CREATE FUNCTION public.fn_cap_coverage_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.fn_cap_coverage_updated_at() OWNER TO test;

--
-- Name: fn_capture_contract_snapshot(); Type: FUNCTION; Schema: public; Owner: test
--

CREATE FUNCTION public.fn_capture_contract_snapshot() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    max_version INTEGER;
BEGIN
    SELECT COALESCE(MAX(version), 0) + 1
    INTO max_version
    FROM public.contract_version_history
    WHERE contrato_id = COALESCE(NEW.contrato_id, OLD.contrato_id);

    INSERT INTO public.contract_version_history (
        contrato_id, version, changed_by, change_type, snapshot
    ) VALUES (
        COALESCE(NEW.contrato_id, OLD.contrato_id),
        max_version,
        current_user,
        CASE
            WHEN TG_OP = 'DELETE' THEN 'deletion'
            WHEN TG_OP = 'UPDATE' THEN 'snapshot'
            ELSE 'snapshot'
        END,
        row_to_json(COALESCE(NEW, OLD))::JSONB
    );

    RETURN COALESCE(NEW, OLD);
END;
$$;


ALTER FUNCTION public.fn_capture_contract_snapshot() OWNER TO test;

--
-- Name: fn_purge_old_data(text, text, integer, boolean, integer); Type: FUNCTION; Schema: public; Owner: test
--

CREATE FUNCTION public.fn_purge_old_data(p_table text DEFAULT 'pncp_raw_bids'::text, p_field text DEFAULT 'data_publicacao'::text, p_retention_days integer DEFAULT 730, p_dry_run boolean DEFAULT true, p_batch_size integer DEFAULT 10000) RETURNS TABLE(action text, table_name text, rows_affected bigint, duration_ms double precision)
    LANGUAGE plpgsql
    AS $_$
DECLARE
    cutoff_date DATE;
    v_count     BIGINT;
    start_ts    TIMESTAMPTZ;
    end_ts      TIMESTAMPTZ;
BEGIN
    cutoff_date := CURRENT_DATE - p_retention_days;
    start_ts := clock_timestamp();

    -- Validate table/field to prevent SQL injection (whitelist)
    IF p_table NOT IN ('pncp_raw_bids', 'pncp_supplier_contracts') THEN
        RETURN QUERY SELECT 'error'::TEXT, p_table, 0::BIGINT, 0::DOUBLE PRECISION;
        RETURN;
    END IF;
    IF p_field NOT IN ('data_publicacao', 'data_encerramento', 'ingested_at') THEN
        RETURN QUERY SELECT 'error'::TEXT, p_field, 0::BIGINT, 0::DOUBLE PRECISION;
        RETURN;
    END IF;

    IF p_table = 'pncp_raw_bids' THEN
        EXECUTE format(
            'SELECT COUNT(*) FROM %I WHERE %I < $1 AND is_active = TRUE',
            p_table, p_field
        ) INTO v_count USING cutoff_date;

        IF p_dry_run THEN
            end_ts := clock_timestamp();
            RETURN QUERY SELECT 'dry-run'::TEXT, p_table, v_count,
                EXTRACT(EPOCH FROM (end_ts - start_ts)) * 1000;
        ELSE
            -- Batch delete (soft-delete: is_active = FALSE preserves FK integrity)
            LOOP
                EXECUTE format(
                    'UPDATE %I SET is_active = FALSE WHERE %I < $1 AND is_active = TRUE LIMIT $2',
                    p_table, p_field
                ) USING cutoff_date, p_batch_size;

                EXIT WHEN NOT FOUND;
            END LOOP;

            end_ts := clock_timestamp();
            RETURN QUERY SELECT 'purged'::TEXT, p_table, v_count,
                EXTRACT(EPOCH FROM (end_ts - start_ts)) * 1000;
        END IF;
    ELSE
        -- pncp_supplier_contracts (mesma logica)
        EXECUTE format(
            'SELECT COUNT(*) FROM %I WHERE %I < $1 AND is_active = TRUE',
            p_table, p_field
        ) INTO v_count USING cutoff_date;

        IF p_dry_run THEN
            end_ts := clock_timestamp();
            RETURN QUERY SELECT 'dry-run'::TEXT, p_table, v_count,
                EXTRACT(EPOCH FROM (end_ts - start_ts)) * 1000;
        ELSE
            LOOP
                EXECUTE format(
                    'UPDATE %I SET is_active = FALSE WHERE %I < $1 AND is_active = TRUE LIMIT $2',
                    p_table, p_field
                ) USING cutoff_date, p_batch_size;
                EXIT WHEN NOT FOUND;
            END LOOP;

            end_ts := clock_timestamp();
            RETURN QUERY SELECT 'purged'::TEXT, p_table, v_count,
                EXTRACT(EPOCH FROM (end_ts - start_ts)) * 1000;
        END IF;
    END IF;
END;
$_$;


ALTER FUNCTION public.fn_purge_old_data(p_table text, p_field text, p_retention_days integer, p_dry_run boolean, p_batch_size integer) OWNER TO test;

--
-- Name: FUNCTION fn_purge_old_data(p_table text, p_field text, p_retention_days integer, p_dry_run boolean, p_batch_size integer); Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON FUNCTION public.fn_purge_old_data(p_table text, p_field text, p_retention_days integer, p_dry_run boolean, p_batch_size integer) IS 'Configurable data retention purge. Default: 730 days. Use dry_run=TRUE to preview. Story 1.2 (DT-22)';


--
-- Name: fn_reconciliation_summary(text, integer); Type: FUNCTION; Schema: public; Owner: test
--

CREATE FUNCTION public.fn_reconciliation_summary(p_source text DEFAULT NULL::text, p_days integer DEFAULT 30) RETURNS TABLE(source text, total_snapshots bigint, reconciled bigint, last_snapshot timestamp with time zone, pct_reconciled numeric)
    LANGUAGE plpgsql STABLE
    AS $$
BEGIN
    RETURN QUERY
    SELECT
        cs.source,
        COUNT(*)::BIGINT AS total_snapshots,
        COUNT(*) FILTER (WHERE cs.source_reconciled)::BIGINT AS reconciled,
        MAX(cs.snapshot_date::TIMESTAMPTZ) AS last_snapshot,
        ROUND(
            100.0 * COUNT(*) FILTER (WHERE cs.source_reconciled) / GREATEST(COUNT(*), 1),
            1
        ) AS pct_reconciled
    FROM public.coverage_snapshots cs
    WHERE (p_source IS NULL OR cs.source = p_source)
      AND cs.snapshot_date >= CURRENT_DATE - p_days
    GROUP BY cs.source
    ORDER BY cs.source;
END;
$$;


ALTER FUNCTION public.fn_reconciliation_summary(p_source text, p_days integer) OWNER TO test;

--
-- Name: FUNCTION fn_reconciliation_summary(p_source text, p_days integer); Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON FUNCTION public.fn_reconciliation_summary(p_source text, p_days integer) IS 'Summary of snapshot reconciliation per source. Story 1.2';


--
-- Name: fn_validate_coverage_evidence(); Type: FUNCTION; Schema: public; Owner: test
--

CREATE FUNCTION public.fn_validate_coverage_evidence() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NEW.state = 'success_with_data' AND NEW.count_persisted <= 0 THEN
        RAISE EXCEPTION 'success_with_data requires count_persisted > 0 (got %)', NEW.count_persisted;
    END IF;
    IF NEW.state = 'success_zero' AND NEW.count_persisted > 0 THEN
        RAISE EXCEPTION 'success_zero requires count_persisted = 0 (got %)', NEW.count_persisted;
    END IF;
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.fn_validate_coverage_evidence() OWNER TO test;

--
-- Name: fn_value_statistics(text, integer, integer); Type: FUNCTION; Schema: public; Owner: test
--

CREATE FUNCTION public.fn_value_statistics(p_uf text DEFAULT NULL::text, p_modalidade_id integer DEFAULT NULL::integer, p_days integer DEFAULT 365) RETURNS TABLE(observation_type text, total_observations bigint, avg_valor numeric, median_valor numeric, min_valor numeric, max_valor numeric, p25_valor numeric, p75_valor numeric, stddev_valor numeric)
    LANGUAGE plpgsql STABLE
    AS $$
BEGIN
    RETURN QUERY
    SELECT
        v.observation_type,
        COUNT(*)::BIGINT,
        ROUND(AVG(v.valor), 2),
        ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY v.valor)::NUMERIC, 2),
        ROUND(MIN(v.valor), 2),
        ROUND(MAX(v.valor), 2),
        ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY v.valor)::NUMERIC, 2),
        ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY v.valor)::NUMERIC, 2),
        ROUND(STDDEV(v.valor)::NUMERIC, 2)
    FROM public.v_value_observations_canonical v
    WHERE (p_uf IS NULL OR v.uf = p_uf)
      AND (p_modalidade_id IS NULL OR v.modalidade_id = p_modalidade_id)
      AND v.data_publicacao >= CURRENT_DATE - p_days
      AND v.valor IS NOT NULL
    GROUP BY v.observation_type
    ORDER BY v.observation_type;
END;
$$;


ALTER FUNCTION public.fn_value_statistics(p_uf text, p_modalidade_id integer, p_days integer) OWNER TO test;

--
-- Name: FUNCTION fn_value_statistics(p_uf text, p_modalidade_id integer, p_days integer); Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON FUNCTION public.fn_value_statistics(p_uf text, p_modalidade_id integer, p_days integer) IS 'Statistical summary of value observations. Used by bid_simulator. Story 1.2';


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
        SELECT ec.source,
               COUNT(*) AS total_entities,
               SUM(CASE WHEN ec.is_covered THEN 1 ELSE 0 END) AS covered_entities
        FROM public.entity_coverage ec
        WHERE EXISTS (
            SELECT 1 FROM public.sc_public_entities e
            WHERE e.id = ec.entity_id AND e.is_active = TRUE
        )
        GROUP BY ec.source
    LOOP
        INSERT INTO public.coverage_snapshots (snapshot_date, source, total_entities, covered_entities, pct_covered)
        VALUES (snap_date, rec.source, rec.total_entities, rec.covered_entities,
                ROUND(100.0 * rec.covered_entities / NULLIF(rec.total_entities, 0), 2))
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

COMMENT ON FUNCTION public.generate_coverage_snapshot(snap_date date) IS 'Gera snapshot de cobertura para todas as fontes';


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

    -- Soft-delete: marca como inativo (NAO remove fisicamente)
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
-- Name: FUNCTION purge_old_bids(p_retention_days integer); Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON FUNCTION public.purge_old_bids(p_retention_days integer) IS 'TD-DB-14 (confirmado): Soft-delete — UPDATE is_active = FALSE. Nunca faz DELETE. Registros permanecem recuperaveis.';


--
-- Name: purge_old_bids_hard(integer); Type: FUNCTION; Schema: public; Owner: test
--

CREATE FUNCTION public.purge_old_bids_hard(p_soft_retention_days integer DEFAULT 90) RETURNS TABLE(hard_deleted_count integer, remaining_soft_deleted integer)
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_cutoff DATE;
    v_deleted INT;
    v_remaining INT;
BEGIN
    v_cutoff := CURRENT_DATE - p_soft_retention_days;

    -- Hard-delete apenas registros ja soft-deleted ha mais de N dias
    DELETE FROM pncp_raw_bids
    WHERE is_active = FALSE
      AND updated_at < v_cutoff::TIMESTAMPTZ;

    GET DIAGNOSTICS v_deleted = ROW_COUNT;

    SELECT COUNT(*)::INT INTO v_remaining
    FROM pncp_raw_bids
    WHERE is_active = FALSE;

    RETURN QUERY SELECT v_deleted, v_remaining;
END;
$$;


ALTER FUNCTION public.purge_old_bids_hard(p_soft_retention_days integer) OWNER TO test;

--
-- Name: FUNCTION purge_old_bids_hard(p_soft_retention_days integer); Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON FUNCTION public.purge_old_bids_hard(p_soft_retention_days integer) IS 'TD-DB-14: Hard-delete controlado — remove fisicamente registros soft-deleted ha mais de p_soft_retention_days dias. So executa quando a retencao de soft-delete expirou. Use com cautela.';


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
-- Name: trg_oi_last_seen(); Type: FUNCTION; Schema: public; Owner: test
--

CREATE FUNCTION public.trg_oi_last_seen() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.last_seen_at = NOW();
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.trg_oi_last_seen() OWNER TO test;

--
-- Name: trg_oi_updated_at(); Type: FUNCTION; Schema: public; Owner: test
--

CREATE FUNCTION public.trg_oi_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.trg_oi_updated_at() OWNER TO test;

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
        INSERT INTO public.entity_coverage (
            entity_id, source, last_seen_at, total_bids, is_covered, within_200km, match_method
        )
        VALUES (
            NEW.matched_entity_id,
            NEW.source,
            NEW.data_publicacao,
            1,
            COALESCE(NEW.data_publicacao >= CURRENT_DATE - 90, FALSE),
            COALESCE((SELECT raio_200km FROM public.sc_public_entities WHERE id = NEW.matched_entity_id), FALSE),
            COALESCE(NEW.match_method, 'direct')
        )
        ON CONFLICT (entity_id, source) DO UPDATE
        SET
            last_seen_at = GREATEST(
                COALESCE(public.entity_coverage.last_seen_at, '1970-01-01'::date),
                COALESCE(NEW.data_publicacao, '1970-01-01'::date)
            ),
            total_bids = public.entity_coverage.total_bids + 1,
            is_covered = GREATEST(
                COALESCE(public.entity_coverage.last_seen_at, '1970-01-01'::date),
                COALESCE(NEW.data_publicacao, '1970-01-01'::date)
            ) >= CURRENT_DATE - 90,
            match_method = CASE
                WHEN public.entity_coverage.match_method IN ('direct', 'hierarchical') THEN public.entity_coverage.match_method
                ELSE COALESCE(NEW.match_method, 'direct')
            END;
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
    IF NEW.matched_entity_id IS NOT NULL
       AND (OLD.matched_entity_id IS NULL OR OLD.matched_entity_id <> NEW.matched_entity_id)
    THEN
        INSERT INTO public.entity_coverage (
            entity_id, source, last_seen_at, total_bids, is_covered, within_200km, match_method
        )
        VALUES (
            NEW.matched_entity_id,
            NEW.source,
            NEW.data_publicacao,
            1,
            COALESCE(NEW.data_publicacao >= CURRENT_DATE - 90, FALSE),
            COALESCE((SELECT raio_200km FROM public.sc_public_entities WHERE id = NEW.matched_entity_id), FALSE),
            COALESCE(NEW.match_method, 'direct')
        )
        ON CONFLICT (entity_id, source) DO UPDATE
        SET
            last_seen_at = GREATEST(
                COALESCE(public.entity_coverage.last_seen_at, '1970-01-01'::date),
                COALESCE(NEW.data_publicacao, '1970-01-01'::date)
            ),
            total_bids = public.entity_coverage.total_bids + 1,
            is_covered = GREATEST(
                COALESCE(public.entity_coverage.last_seen_at, '1970-01-01'::date),
                COALESCE(NEW.data_publicacao, '1970-01-01'::date)
            ) >= CURRENT_DATE - 90,
            match_method = CASE
                WHEN public.entity_coverage.match_method IN ('direct', 'hierarchical')
                THEN public.entity_coverage.match_method
                ELSE COALESCE(NEW.match_method, 'direct')
            END;
    END IF;
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.update_entity_coverage_on_update() OWNER TO test;

--
-- Name: update_entity_hierarchy_timestamp(); Type: FUNCTION; Schema: public; Owner: test
--

CREATE FUNCTION public.update_entity_hierarchy_timestamp() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.update_entity_hierarchy_timestamp() OWNER TO test;

--
-- Name: upsert_opportunity_intel(jsonb); Type: FUNCTION; Schema: public; Owner: test
--

CREATE FUNCTION public.upsert_opportunity_intel(batch jsonb) RETURNS TABLE(action text, record_id bigint, content_hash text)
    LANGUAGE plpgsql
    AS $$
DECLARE
    rec JSONB;
BEGIN
    FOR rec IN SELECT * FROM jsonb_array_elements(batch)
    LOOP
        INSERT INTO opportunity_intel (
            source, source_id, source_url, content_hash,
            numero_controle_pncp,
            crawl_batch_id, run_id,
            first_seen_at, last_seen_at,
            orgao_cnpj, orgao_nome, ente_federativo,
            uf, municipio, codigo_ibge,
            numero_processo, numero_edital,
            modalidade, modalidade_id,
            objeto, categoria,
            valor_estimado, valor_homologado, valor_semantica,
            data_publicacao, data_abertura, data_encerramento, data_homologacao,
            status_fonte, status_canonico, status_motivo, status_data,
            link_edital, link_anexos,
            qualidade_score, qualidade_fatores, dados_ausentes,
            ranking, ranking_score, ranking_fatores, ranking_regras, ranking_confianca,
            proveniencia, metadata
        ) VALUES (
            rec->>'source',
            rec->>'source_id',
            rec->>'source_url',
            rec->>'content_hash',
            rec->>'numero_controle_pncp',
            rec->>'crawl_batch_id',
            (rec->>'run_id')::BIGINT,
            COALESCE((rec->>'first_seen_at')::TIMESTAMPTZ, NOW()),
            COALESCE((rec->>'last_seen_at')::TIMESTAMPTZ, NOW()),
            rec->>'orgao_cnpj',
            rec->>'orgao_nome',
            rec->>'ente_federativo',
            rec->>'uf',
            rec->>'municipio',
            rec->>'codigo_ibge',
            rec->>'numero_processo',
            rec->>'numero_edital',
            rec->>'modalidade',
            (rec->>'modalidade_id')::INTEGER,
            rec->>'objeto',
            rec->>'categoria',
            (rec->>'valor_estimado')::NUMERIC,
            (rec->>'valor_homologado')::NUMERIC,
            rec->>'valor_semantica',
            (rec->>'data_publicacao')::TIMESTAMPTZ,
            (rec->>'data_abertura')::TIMESTAMPTZ,
            (rec->>'data_encerramento')::TIMESTAMPTZ,
            (rec->>'data_homologacao')::TIMESTAMPTZ,
            rec->>'status_fonte',
            COALESCE(rec->>'status_canonico', 'unknown'),
            rec->>'status_motivo',
            (rec->>'status_data')::TIMESTAMPTZ,
            rec->>'link_edital',
            CASE WHEN rec->'link_anexos' IS NOT NULL
                 THEN ARRAY(SELECT * FROM jsonb_array_elements_text(rec->'link_anexos'))
            END,
            COALESCE((rec->>'qualidade_score')::INTEGER, 0),
            COALESCE(rec->'qualidade_fatores', '{}'),
            CASE WHEN rec->'dados_ausentes' IS NOT NULL
                 THEN ARRAY(SELECT * FROM jsonb_array_elements_text(rec->'dados_ausentes'))
            END,
            COALESCE(rec->>'ranking', 'REVIEW'),
            COALESCE((rec->>'ranking_score')::INTEGER, 0),
            COALESCE(rec->'ranking_fatores', '{}'),
            CASE WHEN rec->'ranking_regras' IS NOT NULL
                 THEN ARRAY(SELECT * FROM jsonb_array_elements_text(rec->'ranking_regras'))
            END,
            COALESCE(rec->>'ranking_confianca', 'MEDIUM'),
            COALESCE(rec->'proveniencia', '{}'),
            COALESCE(rec->'metadata', '{}')
        )
        ON CONFLICT ON CONSTRAINT uq_oi_content_hash DO UPDATE SET
            source_url = EXCLUDED.source_url,
            numero_controle_pncp = COALESCE(EXCLUDED.numero_controle_pncp, opportunity_intel.numero_controle_pncp),
            crawl_batch_id = EXCLUDED.crawl_batch_id,
            run_id = EXCLUDED.run_id,
            last_seen_at = NOW(),
            orgao_cnpj = COALESCE(EXCLUDED.orgao_cnpj, opportunity_intel.orgao_cnpj),
            orgao_nome = COALESCE(EXCLUDED.orgao_nome, opportunity_intel.orgao_nome),
            uf = COALESCE(EXCLUDED.uf, opportunity_intel.uf),
            municipio = COALESCE(EXCLUDED.municipio, opportunity_intel.municipio),
            codigo_ibge = COALESCE(EXCLUDED.codigo_ibge, opportunity_intel.codigo_ibge),
            numero_processo = COALESCE(EXCLUDED.numero_processo, opportunity_intel.numero_processo),
            numero_edital = COALESCE(EXCLUDED.numero_edital, opportunity_intel.numero_edital),
            modalidade = COALESCE(EXCLUDED.modalidade, opportunity_intel.modalidade),
            modalidade_id = COALESCE(EXCLUDED.modalidade_id, opportunity_intel.modalidade_id),
            objeto = COALESCE(EXCLUDED.objeto, opportunity_intel.objeto),
            categoria = COALESCE(EXCLUDED.categoria, opportunity_intel.categoria),
            valor_estimado = COALESCE(EXCLUDED.valor_estimado, opportunity_intel.valor_estimado),
            valor_homologado = COALESCE(EXCLUDED.valor_homologado, opportunity_intel.valor_homologado),
            valor_semantica = COALESCE(EXCLUDED.valor_semantica, opportunity_intel.valor_semantica),
            data_publicacao = COALESCE(EXCLUDED.data_publicacao, opportunity_intel.data_publicacao),
            data_abertura = COALESCE(EXCLUDED.data_abertura, opportunity_intel.data_abertura),
            data_encerramento = COALESCE(EXCLUDED.data_encerramento, opportunity_intel.data_encerramento),
            data_homologacao = COALESCE(EXCLUDED.data_homologacao, opportunity_intel.data_homologacao),
            status_fonte = EXCLUDED.status_fonte,
            status_canonico = EXCLUDED.status_canonico,
            status_motivo = EXCLUDED.status_motivo,
            status_data = EXCLUDED.status_data,
            link_edital = COALESCE(EXCLUDED.link_edital, opportunity_intel.link_edital),
            link_anexos = COALESCE(EXCLUDED.link_anexos, opportunity_intel.link_anexos),
            qualidade_score = EXCLUDED.qualidade_score,
            qualidade_fatores = EXCLUDED.qualidade_fatores,
            dados_ausentes = EXCLUDED.dados_ausentes,
            ranking = EXCLUDED.ranking,
            ranking_score = EXCLUDED.ranking_score,
            ranking_fatores = EXCLUDED.ranking_fatores,
            ranking_regras = EXCLUDED.ranking_regras,
            ranking_confianca = EXCLUDED.ranking_confianca,
            proveniencia = EXCLUDED.proveniencia,
            metadata = EXCLUDED.metadata,
            is_active = EXCLUDED.is_active
        RETURNING
            (CASE WHEN xmax = 0 THEN 'insert' ELSE 'update' END)::TEXT AS action,
            id AS record_id,
            content_hash
        INTO action, record_id, content_hash;

        RETURN NEXT;
    END LOOP;
END;
$$;


ALTER FUNCTION public.upsert_opportunity_intel(batch jsonb) OWNER TO test;

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

--
-- Name: upsert_qw01_pncp_opportunities(jsonb); Type: FUNCTION; Schema: public; Owner: test
--

CREATE FUNCTION public.upsert_qw01_pncp_opportunities(batch jsonb) RETURNS TABLE(action text, record_id bigint, result_content_hash text)
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
            COALESCE(rec->>'uf', 'SC'), rec->>'municipio', rec->>'codigo_ibge',
            rec->>'numero_processo', rec->>'numero_edital', rec->>'modalidade',
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
            municipio = COALESCE(EXCLUDED.municipio, opportunity_intel.municipio),
            codigo_ibge = COALESCE(EXCLUDED.codigo_ibge, opportunity_intel.codigo_ibge),
            numero_processo = COALESCE(EXCLUDED.numero_processo, opportunity_intel.numero_processo),
            numero_edital = COALESCE(EXCLUDED.numero_edital, opportunity_intel.numero_edital),
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


ALTER FUNCTION public.upsert_qw01_pncp_opportunities(batch jsonb) OWNER TO test;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: _migrations; Type: TABLE; Schema: public; Owner: test
--

CREATE TABLE public._migrations (
    version text NOT NULL,
    name text NOT NULL,
    applied_at timestamp with time zone DEFAULT now() NOT NULL,
    checksum text,
    rollback_sql text
);


ALTER TABLE public._migrations OWNER TO test;

--
-- Name: capability_coverage; Type: TABLE; Schema: public; Owner: test
--

CREATE TABLE public.capability_coverage (
    id bigint NOT NULL,
    capability text NOT NULL,
    entity_id integer,
    source text NOT NULL,
    is_covered boolean DEFAULT false NOT NULL,
    coverage_pct numeric(5,2) DEFAULT 0,
    last_verified timestamp with time zone,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.capability_coverage OWNER TO test;

--
-- Name: TABLE capability_coverage; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON TABLE public.capability_coverage IS 'Capability-level coverage tracking. Story 1.2';


--
-- Name: COLUMN capability_coverage.capability; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON COLUMN public.capability_coverage.capability IS 'Nome da capacidade: opportunity_radar|contract_intel|entity_matching|coverage_truth|source_health';


--
-- Name: COLUMN capability_coverage.coverage_pct; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON COLUMN public.capability_coverage.coverage_pct IS 'Percentual de cobertura para esta capacidade (0.00 - 100.00)';


--
-- Name: capability_coverage_id_seq; Type: SEQUENCE; Schema: public; Owner: test
--

CREATE SEQUENCE public.capability_coverage_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.capability_coverage_id_seq OWNER TO test;

--
-- Name: capability_coverage_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: test
--

ALTER SEQUENCE public.capability_coverage_id_seq OWNED BY public.capability_coverage.id;


--
-- Name: contract_version_history; Type: TABLE; Schema: public; Owner: test
--

CREATE TABLE public.contract_version_history (
    id bigint NOT NULL,
    contrato_id text NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    changed_at timestamp with time zone DEFAULT now() NOT NULL,
    changed_by text DEFAULT 'migration_033'::text NOT NULL,
    change_type text DEFAULT 'snapshot'::text NOT NULL,
    snapshot jsonb NOT NULL
);


ALTER TABLE public.contract_version_history OWNER TO test;

--
-- Name: TABLE contract_version_history; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON TABLE public.contract_version_history IS 'Historical versions of pncp_supplier_contracts. Story 1.2';


--
-- Name: COLUMN contract_version_history.contrato_id; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON COLUMN public.contract_version_history.contrato_id IS 'FK logica para pncp_supplier_contracts.contrato_id';


--
-- Name: COLUMN contract_version_history.version; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON COLUMN public.contract_version_history.version IS 'Numero de versao incremental por contrato_id';


--
-- Name: COLUMN contract_version_history.change_type; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON COLUMN public.contract_version_history.change_type IS 'Tipo: snapshot|upsert|correction|deletion';


--
-- Name: COLUMN contract_version_history.snapshot; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON COLUMN public.contract_version_history.snapshot IS 'Snapshot completo do registro no momento da captura';


--
-- Name: contract_version_history_id_seq; Type: SEQUENCE; Schema: public; Owner: test
--

CREATE SEQUENCE public.contract_version_history_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.contract_version_history_id_seq OWNER TO test;

--
-- Name: contract_version_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: test
--

ALTER SEQUENCE public.contract_version_history_id_seq OWNED BY public.contract_version_history.id;


--
-- Name: coverage_evidence; Type: TABLE; Schema: public; Owner: test
--

CREATE TABLE public.coverage_evidence (
    id bigint NOT NULL,
    entity_id integer,
    source text NOT NULL,
    data_type text DEFAULT 'bids'::text NOT NULL,
    queried_start date,
    queried_end date,
    run_id text NOT NULL,
    started_at timestamp with time zone,
    completed_at timestamp with time zone DEFAULT now() NOT NULL,
    count_obtained integer DEFAULT 0 NOT NULL,
    count_transformed integer DEFAULT 0 NOT NULL,
    count_persisted integer DEFAULT 0 NOT NULL,
    state public.evidence_state DEFAULT 'not_investigated'::public.evidence_state NOT NULL,
    error_message text,
    error_code text,
    metadata jsonb DEFAULT '{}'::jsonb,
    canonical_entity_key text,
    applicability text DEFAULT 'applicable'::text NOT NULL,
    scope_key text,
    checked_at timestamp with time zone,
    pages_expected integer,
    pages_processed integer DEFAULT 0 NOT NULL,
    records_fetched integer DEFAULT 0 NOT NULL,
    open_records integer DEFAULT 0 NOT NULL,
    freshness_status text DEFAULT 'unknown'::text NOT NULL,
    evidence_metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT ck_ce_applicability CHECK ((applicability = ANY (ARRAY['applicable'::text, 'not_applicable'::text, 'unknown'::text]))),
    CONSTRAINT ck_ce_freshness_status CHECK ((freshness_status = ANY (ARRAY['fresh'::text, 'stale'::text, 'never'::text, 'unknown'::text])))
);


ALTER TABLE public.coverage_evidence OWNER TO test;

--
-- Name: COLUMN coverage_evidence.canonical_entity_key; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON COLUMN public.coverage_evidence.canonical_entity_key IS 'Stable seed identity hash; preserves legitimate duplicate CNPJ roots.';


--
-- Name: coverage_evidence_id_seq; Type: SEQUENCE; Schema: public; Owner: test
--

CREATE SEQUENCE public.coverage_evidence_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.coverage_evidence_id_seq OWNER TO test;

--
-- Name: coverage_evidence_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: test
--

ALTER SEQUENCE public.coverage_evidence_id_seq OWNED BY public.coverage_evidence.id;


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
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    source_reconciled boolean DEFAULT false NOT NULL,
    reconciliation_notes text,
    fingerprint text
);


ALTER TABLE public.coverage_snapshots OWNER TO test;

--
-- Name: TABLE coverage_snapshots; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON TABLE public.coverage_snapshots IS 'Snapshots semanais de cobertura por fonte — usado para tendencia no relatorio semanal (Story 001.7)';


--
-- Name: COLUMN coverage_snapshots.source_reconciled; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON COLUMN public.coverage_snapshots.source_reconciled IS 'Se este snapshot foi reconciliado contra a fonte de verdade';


--
-- Name: COLUMN coverage_snapshots.reconciliation_notes; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON COLUMN public.coverage_snapshots.reconciliation_notes IS 'Notas sobre a reconciliacao (gaps identificados, discrepancias)';


--
-- Name: COLUMN coverage_snapshots.fingerprint; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON COLUMN public.coverage_snapshots.fingerprint IS 'SHA-256 do conjunto de dados do snapshot para verificacao de integridade';


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
    within_200km boolean DEFAULT false NOT NULL,
    match_method text
);


ALTER TABLE public.entity_coverage OWNER TO test;

--
-- Name: COLUMN entity_coverage.match_method; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON COLUMN public.entity_coverage.match_method IS 'Metodo de match: direct|cnpj_fallback|hierarchical|name_match — adicionado por COVERAGE-2.4';


--
-- Name: entity_hierarchy; Type: TABLE; Schema: public; Owner: test
--

CREATE TABLE public.entity_hierarchy (
    entity_id integer NOT NULL,
    parent_entity_id integer NOT NULL,
    relationship character varying(32) NOT NULL,
    match_confidence character varying(16) NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT entity_hierarchy_match_confidence_check CHECK (((match_confidence)::text = ANY ((ARRAY['direct'::character varying, 'hierarchical'::character varying, 'inferred'::character varying])::text[]))),
    CONSTRAINT entity_hierarchy_relationship_check CHECK (((relationship)::text = ANY ((ARRAY['prefeitura'::character varying, 'camara'::character varying, 'autarquia'::character varying, 'fundacao'::character varying, 'fundo'::character varying, 'conselho'::character varying, 'outros'::character varying])::text[])))
);


ALTER TABLE public.entity_hierarchy OWNER TO test;

--
-- Name: TABLE entity_hierarchy; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON TABLE public.entity_hierarchy IS 'Mapeamento hierarquico de entidades municipais para suas respectivas prefeituras — Story COVERAGE-1.8';


--
-- Name: COLUMN entity_hierarchy.entity_id; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON COLUMN public.entity_hierarchy.entity_id IS 'ID da entidade filha (secretaria, fundacao, autarquia, etc.)';


--
-- Name: COLUMN entity_hierarchy.parent_entity_id; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON COLUMN public.entity_hierarchy.parent_entity_id IS 'ID da entidade pai (prefeitura/municipio)';


--
-- Name: COLUMN entity_hierarchy.relationship; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON COLUMN public.entity_hierarchy.relationship IS 'Tipo de relacao: prefeitura | camara | autarquia | fundacao | fundo | conselho | outros';


--
-- Name: COLUMN entity_hierarchy.match_confidence; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON COLUMN public.entity_hierarchy.match_confidence IS 'Confianca do vinculo: direct | hierarchical | inferred';


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
    source text NOT NULL,
    scope_key text NOT NULL,
    last_page integer,
    last_date date,
    last_id text,
    records_fetched integer DEFAULT 0,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    external_run_id text,
    pages_expected integer,
    scope_complete boolean DEFAULT false NOT NULL,
    completion_reason text
);


ALTER TABLE public.opportunity_checkpoints OWNER TO test;

--
-- Name: opportunity_coverage; Type: TABLE; Schema: public; Owner: test
--

CREATE TABLE public.opportunity_coverage (
    entity_id integer NOT NULL,
    source text NOT NULL,
    period_start date,
    period_end date,
    pages_expected integer,
    pages_processed integer,
    last_attempt timestamp with time zone,
    result text,
    count_obtained integer DEFAULT 0,
    count_open integer DEFAULT 0,
    freshness interval,
    error_message text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_oc_result CHECK ((result = ANY (ARRAY['success'::text, 'success_zero'::text, 'partial'::text, 'error'::text, 'pending'::text])))
);


ALTER TABLE public.opportunity_coverage OWNER TO test;

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
    scope_key text,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    finished_at timestamp with time zone,
    records_fetched integer DEFAULT 0,
    records_new integer DEFAULT 0,
    records_updated integer DEFAULT 0,
    pages_processed integer DEFAULT 0,
    pages_expected integer,
    status text DEFAULT 'running'::text NOT NULL,
    error_message text,
    metadata jsonb DEFAULT '{}'::jsonb,
    external_run_id text,
    source_strategy text,
    period_start date,
    period_end date,
    records_expected integer,
    scope_complete boolean DEFAULT false NOT NULL,
    completion_reason text,
    error_code text,
    CONSTRAINT ck_or_status CHECK ((status = ANY (ARRAY['running'::text, 'completed'::text, 'completed_zero'::text, 'failed'::text, 'partial'::text])))
);


ALTER TABLE public.opportunity_runs OWNER TO test;

--
-- Name: COLUMN opportunity_runs.scope_complete; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON COLUMN public.opportunity_runs.scope_complete IS 'True only when every declared source scope has auditable pagination completion.';


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
    match_confidence text,
    CONSTRAINT chk_pncp_raw_bids_esfera_id CHECK (((esfera_id IS NULL) OR (esfera_id = ANY (ARRAY[1, 2, 3, 4]))))
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
-- Name: CONSTRAINT chk_pncp_raw_bids_esfera_id ON pncp_raw_bids; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON CONSTRAINT chk_pncp_raw_bids_esfera_id ON public.pncp_raw_bids IS 'TD-DB-09: esfera_id deve ser 1=Federal, 2=Estadual, 3=Municipal, 4=Distrital, ou NULL';


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
    codigo_municipio_ibge text,
    municipio_inferido boolean DEFAULT false NOT NULL
);


ALTER TABLE public.pncp_supplier_contracts OWNER TO test;

--
-- Name: COLUMN pncp_supplier_contracts.codigo_municipio_ibge; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON COLUMN public.pncp_supplier_contracts.codigo_municipio_ibge IS '7-digit IBGE municipality code, backfilled by sc_dados_abertos_backfill.py';


--
-- Name: COLUMN pncp_supplier_contracts.municipio_inferido; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON COLUMN public.pncp_supplier_contracts.municipio_inferido IS 'TRUE when municipio was inferred (not from original source)';


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
-- Name: retention_policy; Type: TABLE; Schema: public; Owner: test
--

CREATE TABLE public.retention_policy (
    id bigint NOT NULL,
    table_name text NOT NULL,
    field_name text NOT NULL,
    retention_days integer DEFAULT 730 NOT NULL,
    strategy text DEFAULT 'soft_delete'::text NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_retention_strategy CHECK ((strategy = ANY (ARRAY['soft_delete'::text, 'hard_delete'::text, 'archive'::text])))
);


ALTER TABLE public.retention_policy OWNER TO test;

--
-- Name: TABLE retention_policy; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON TABLE public.retention_policy IS 'Retention policy configuration. Story 1.2 (DT-22)';


--
-- Name: retention_policy_id_seq; Type: SEQUENCE; Schema: public; Owner: test
--

CREATE SEQUENCE public.retention_policy_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.retention_policy_id_seq OWNER TO test;

--
-- Name: retention_policy_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: test
--

ALTER SEQUENCE public.retention_policy_id_seq OWNED BY public.retention_policy.id;


--
-- Name: sc_dados_abertos_backfill_log; Type: TABLE; Schema: public; Owner: test
--

CREATE TABLE public.sc_dados_abertos_backfill_log (
    id integer NOT NULL,
    orgao_cnpj text NOT NULL,
    match_method text,
    municipio text,
    codigo_ibge text,
    motivo text,
    executed_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.sc_dados_abertos_backfill_log OWNER TO test;

--
-- Name: TABLE sc_dados_abertos_backfill_log; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON TABLE public.sc_dados_abertos_backfill_log IS 'Audit log for COVERAGE-1.9 municipio backfill: tracks every CNPJ attempt and its outcome';


--
-- Name: sc_dados_abertos_backfill_log_id_seq; Type: SEQUENCE; Schema: public; Owner: test
--

CREATE SEQUENCE public.sc_dados_abertos_backfill_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sc_dados_abertos_backfill_log_id_seq OWNER TO test;

--
-- Name: sc_dados_abertos_backfill_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: test
--

ALTER SEQUENCE public.sc_dados_abertos_backfill_log_id_seq OWNED BY public.sc_dados_abertos_backfill_log.id;


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
-- Name: v_capability_coverage_summary; Type: VIEW; Schema: public; Owner: test
--

CREATE VIEW public.v_capability_coverage_summary AS
 SELECT capability,
    (count(*))::integer AS total_entries,
    (count(*) FILTER (WHERE is_covered))::integer AS covered_entries,
    round(((100.0 * (count(*) FILTER (WHERE is_covered))::numeric) / (GREATEST(count(*), (1)::bigint))::numeric), 1) AS pct_covered,
    max(last_verified) AS last_verified_at
   FROM public.capability_coverage
  GROUP BY capability
  ORDER BY capability;


ALTER VIEW public.v_capability_coverage_summary OWNER TO test;

--
-- Name: VIEW v_capability_coverage_summary; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON VIEW public.v_capability_coverage_summary IS 'Summary of capability coverage per capability. Story 1.2';


--
-- Name: v_contracts_canonical; Type: VIEW; Schema: public; Owner: test
--

CREATE VIEW public.v_contracts_canonical AS
 SELECT c.contrato_id,
    c.orgao_cnpj,
    c.orgao_nome,
    c.fornecedor_cnpj,
    c.fornecedor_nome,
    c.objeto_contrato AS objeto,
    c.valor_total AS valor,
    c.data_inicio,
    c.data_fim,
    c.data_publicacao,
    c.uf,
    c.municipio,
    c.codigo_municipio_ibge,
    c.municipio_inferido,
    c.source,
    c.source_id,
    e.id AS entity_id,
    e.razao_social AS entity_nome,
    e.cnpj_8 AS entity_cnpj_8,
    e.raio_200km AS within_200km,
    enr.cnae_principal,
    enr.natureza_juridica
   FROM ((public.pncp_supplier_contracts c
     LEFT JOIN public.sc_public_entities e ON ((e.cnpj_8 = "left"(c.fornecedor_cnpj, 8))))
     LEFT JOIN public.enriched_entities enr ON ((enr.cnpj = c.fornecedor_cnpj)))
  WHERE ((c.data_inicio IS NOT NULL) OR (c.data_publicacao IS NOT NULL));


ALTER VIEW public.v_contracts_canonical OWNER TO test;

--
-- Name: VIEW v_contracts_canonical; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON VIEW public.v_contracts_canonical IS 'Canonical contracts view v1.0 — contratos ativos com dados de fornecedores. Story 1.2';


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

COMMENT ON VIEW public.v_coverage_gaps IS 'Entes publicos com gap TOTAL de cobertura — COVERAGE-2.4';


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
-- Name: v_coverage_health; Type: VIEW; Schema: public; Owner: test
--

CREATE VIEW public.v_coverage_health AS
 SELECT source,
    (count(*))::integer AS total_entities,
    (count(*) FILTER (WHERE is_covered))::integer AS covered,
    round(((100.0 * (count(*) FILTER (WHERE is_covered))::numeric) / (GREATEST(count(*), (1)::bigint))::numeric), 1) AS pct_covered,
    (count(*) FILTER (WHERE (within_200km AND is_covered)))::integer AS covered_200km,
    (count(*) FILTER (WHERE within_200km))::integer AS total_200km,
    round(((100.0 * (count(*) FILTER (WHERE (within_200km AND is_covered)))::numeric) / (GREATEST(count(*) FILTER (WHERE within_200km), (1)::bigint))::numeric), 1) AS pct_200km,
    (max(last_seen_at))::date AS last_coverage_date,
    ((now())::date - (max(last_seen_at))::date) AS days_since_last_coverage
   FROM public.entity_coverage ec
  GROUP BY source
  ORDER BY source;


ALTER VIEW public.v_coverage_health OWNER TO test;

--
-- Name: VIEW v_coverage_health; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON VIEW public.v_coverage_health IS 'Coverage health per source. Story 1.2';


--
-- Name: v_coverage_summary; Type: VIEW; Schema: public; Owner: test
--

CREATE VIEW public.v_coverage_summary AS
 SELECT source,
    within_200km,
    is_covered,
    count(*) AS entity_count,
    round((((count(*))::numeric * 100.0) / NULLIF(sum(count(*)) OVER (PARTITION BY within_200km), (0)::numeric)), 1) AS pct
   FROM public.entity_coverage ec
  WHERE (EXISTS ( SELECT 1
           FROM public.sc_public_entities e
          WHERE ((e.id = ec.entity_id) AND (e.is_active = true))))
  GROUP BY source, within_200km, is_covered
  ORDER BY source, within_200km, is_covered;


ALTER VIEW public.v_coverage_summary OWNER TO test;

--
-- Name: VIEW v_coverage_summary; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON VIEW public.v_coverage_summary IS 'Sumario de cobertura por source e raio_200km — COVERAGE-2.4';


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

COMMENT ON VIEW public.v_coverage_trend IS 'Evolucao semanal da cobertura com calculo de variacao';


--
-- Name: v_entities_canonical; Type: VIEW; Schema: public; Owner: test
--

CREATE VIEW public.v_entities_canonical AS
 SELECT e.id AS entity_id,
    e.cnpj_8 AS cnpj_8_base,
    e.razao_social,
    e.municipio,
    e.codigo_ibge,
    e.natureza_juridica,
    e.cod_natureza,
    e.latitude,
    e.longitude,
    e.distancia_fk,
    e.raio_200km AS within_200km,
    e.is_active,
    ec.total_bids,
    ec.is_covered,
    ec.last_seen_at AS last_coverage_at
   FROM (public.sc_public_entities e
     LEFT JOIN public.entity_coverage ec ON (((ec.entity_id = e.id) AND (ec.source = 'pncp'::text))));


ALTER VIEW public.v_entities_canonical OWNER TO test;

--
-- Name: VIEW v_entities_canonical; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON VIEW public.v_entities_canonical IS 'Canonical entity view v1.0 — entidades SC com metadados de cobertura. Story 1.2';


--
-- Name: COLUMN v_entities_canonical.entity_id; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON COLUMN public.v_entities_canonical.entity_id IS 'PK da entidade (sc_public_entities.id)';


--
-- Name: COLUMN v_entities_canonical.cnpj_8_base; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON COLUMN public.v_entities_canonical.cnpj_8_base IS 'CNPJ base 8 digitos';


--
-- Name: COLUMN v_entities_canonical.within_200km; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON COLUMN public.v_entities_canonical.within_200km IS 'Dentro do raio 200km de Florianopolis';


--
-- Name: COLUMN v_entities_canonical.is_covered; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON COLUMN public.v_entities_canonical.is_covered IS 'Se a entidade tem coverage ativa';


--
-- Name: COLUMN v_entities_canonical.last_coverage_at; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON COLUMN public.v_entities_canonical.last_coverage_at IS 'Ultima vez que a entidade foi coberta por crawl';


--
-- Name: v_entity_match_summary; Type: VIEW; Schema: public; Owner: test
--

CREATE VIEW public.v_entity_match_summary AS
 SELECT match_method,
    (count(*))::integer AS total_bids,
    (count(*) FILTER (WHERE (matched_entity_id IS NOT NULL)))::integer AS matched,
    round(((100.0 * (count(*) FILTER (WHERE (matched_entity_id IS NOT NULL)))::numeric) / (GREATEST(count(*), (1)::bigint))::numeric), 1) AS pct_matched,
    min(match_score) AS min_score,
    max(match_score) AS max_score,
    round(avg(match_score), 3) AS avg_score,
    (count(DISTINCT matched_entity_id))::integer AS distinct_entities
   FROM public.pncp_raw_bids b
  WHERE (match_method IS NOT NULL)
  GROUP BY match_method
  ORDER BY match_method;


ALTER VIEW public.v_entity_match_summary OWNER TO test;

--
-- Name: VIEW v_entity_match_summary; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON VIEW public.v_entity_match_summary IS 'Entity match performance by method. Story 1.2';


--
-- Name: v_hierarchical_coverage; Type: VIEW; Schema: public; Owner: test
--

CREATE VIEW public.v_hierarchical_coverage AS
 SELECT e.id AS entity_id,
    e.razao_social,
    e.municipio,
    e.natureza_juridica,
    h.relationship,
    h.parent_entity_id,
    p.razao_social AS parent_razao_social,
    pec.is_covered AS parent_covered,
    pec.total_bids AS parent_total_bids,
    ec.is_covered AS direct_covered
   FROM ((((public.sc_public_entities e
     JOIN public.entity_hierarchy h ON ((h.entity_id = e.id)))
     JOIN public.sc_public_entities p ON ((p.id = h.parent_entity_id)))
     LEFT JOIN public.entity_coverage ec ON (((ec.entity_id = e.id) AND (ec.source = 'pncp'::text))))
     LEFT JOIN public.entity_coverage pec ON (((pec.entity_id = h.parent_entity_id) AND (pec.source = 'pncp'::text))))
  WHERE (e.is_active = true);


ALTER VIEW public.v_hierarchical_coverage OWNER TO test;

--
-- Name: VIEW v_hierarchical_coverage; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON VIEW public.v_hierarchical_coverage IS 'Visao consolidada da cobertura hierarquica — Story COVERAGE-1.8';


--
-- Name: v_latest_evidence; Type: VIEW; Schema: public; Owner: test
--

CREATE VIEW public.v_latest_evidence AS
 SELECT DISTINCT ON (entity_id, source, data_type) id,
    entity_id,
    source,
    data_type,
    queried_start,
    queried_end,
    run_id,
    started_at,
    completed_at,
    count_obtained,
    count_transformed,
    count_persisted,
    state,
    error_message,
    error_code,
    metadata
   FROM public.coverage_evidence
  ORDER BY entity_id, source, data_type, completed_at DESC;


ALTER VIEW public.v_latest_evidence OWNER TO test;

--
-- Name: v_migration_status; Type: VIEW; Schema: public; Owner: test
--

CREATE VIEW public.v_migration_status AS
 SELECT version,
    name,
    applied_at,
    checksum,
        CASE
            WHEN (rollback_sql IS NOT NULL) THEN 'reversible'::text
            ELSE 'irreversible'::text
        END AS reversibility,
        CASE
            WHEN (checksum IS NOT NULL) THEN 'verified'::text
            ELSE 'unverified'::text
        END AS integrity_status
   FROM public._migrations
  ORDER BY (version)::integer;


ALTER VIEW public.v_migration_status OWNER TO test;

--
-- Name: VIEW v_migration_status; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON VIEW public.v_migration_status IS 'Migration tracking status. Story 1.2';


--
-- Name: v_open_opportunities_canonical; Type: VIEW; Schema: public; Owner: test
--

CREATE VIEW public.v_open_opportunities_canonical AS
 SELECT b.pncp_id AS bid_id,
    b.pncp_id,
    b.objeto_compra AS objeto,
    b.valor_total_estimado AS valor_estimado,
    b.modalidade_id,
    b.modalidade_nome AS modalidade,
    b.esfera_id,
    b.uf,
    b.municipio,
    b.codigo_municipio_ibge AS codigo_ibge,
    b.orgao_cnpj,
    b.orgao_razao_social AS orgao_nome,
    b.data_publicacao,
    b.data_abertura,
    b.data_encerramento,
    b.link_pncp AS link_edital,
    b.source,
    b.source_id,
    b.match_method,
    b.match_score,
    b.match_confidence,
    e.id AS matched_entity_id,
    e.razao_social AS matched_entity_nome,
    e.raio_200km AS within_200km,
    e.cnpj_8 AS entity_cnpj_8
   FROM (public.pncp_raw_bids b
     LEFT JOIN public.sc_public_entities e ON ((e.id = b.matched_entity_id)))
  WHERE ((b.data_encerramento >= CURRENT_DATE) OR ((b.data_encerramento IS NULL) AND (b.data_publicacao >= (CURRENT_DATE - '30 days'::interval))));


ALTER VIEW public.v_open_opportunities_canonical OWNER TO test;

--
-- Name: VIEW v_open_opportunities_canonical; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON VIEW public.v_open_opportunities_canonical IS 'Canonical open opportunities view v1.0 — licitacoes abertas. Story 1.2';


--
-- Name: COLUMN v_open_opportunities_canonical.within_200km; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON COLUMN public.v_open_opportunities_canonical.within_200km IS 'Se a entidade matched esta dentro do raio 200km';


--
-- Name: v_opportunity_by_source; Type: VIEW; Schema: public; Owner: test
--

CREATE VIEW public.v_opportunity_by_source AS
 SELECT source,
    status_canonico,
    count(*) AS total,
    count(*) FILTER (WHERE (ranking = 'GO'::text)) AS go_count,
    count(*) FILTER (WHERE (ranking = 'REVIEW'::text)) AS review_count,
    count(*) FILTER (WHERE (ranking = 'NO_GO'::text)) AS no_go_count,
    min(data_abertura) AS earliest_abertura,
    max(data_encerramento) AS latest_encerramento,
    min(ingested_at) AS first_ingested,
    max(ingested_at) AS last_ingested
   FROM public.opportunity_intel
  WHERE (is_active = true)
  GROUP BY source, status_canonico
  ORDER BY source, status_canonico;


ALTER VIEW public.v_opportunity_by_source OWNER TO test;

--
-- Name: v_opportunity_coverage_summary; Type: VIEW; Schema: public; Owner: test
--

CREATE VIEW public.v_opportunity_coverage_summary AS
 SELECT source,
    count(DISTINCT entity_id) AS entities_attempted,
    count(DISTINCT entity_id) FILTER (WHERE (result = ANY (ARRAY['success'::text, 'success_zero'::text]))) AS entities_covered,
    count(DISTINCT entity_id) FILTER (WHERE (result = 'success'::text)) AS entities_with_data,
    count(DISTINCT entity_id) FILTER (WHERE (result = 'success_zero'::text)) AS entities_empty,
    count(DISTINCT entity_id) FILTER (WHERE (result = 'error'::text)) AS entities_error,
    sum(count_obtained) AS total_records,
    sum(count_open) AS total_open,
    max(last_attempt) AS last_run,
    round((((count(DISTINCT entity_id) FILTER (WHERE (result = ANY (ARRAY['success'::text, 'success_zero'::text]))))::numeric / (NULLIF(count(DISTINCT entity_id), 0))::numeric) * (100)::numeric), 1) AS pct_covered
   FROM public.opportunity_coverage oc
  GROUP BY source
  ORDER BY source;


ALTER VIEW public.v_opportunity_coverage_summary OWNER TO test;

--
-- Name: v_opportunity_open; Type: VIEW; Schema: public; Owner: test
--

CREATE VIEW public.v_opportunity_open AS
 SELECT oi.id,
    oi.source,
    oi.source_id,
    oi.source_url,
    oi.content_hash,
    oi.numero_controle_pncp,
    oi.crawl_batch_id,
    oi.run_id,
    oi.ingested_at,
    oi.updated_at,
    oi.first_seen_at,
    oi.last_seen_at,
    oi.orgao_cnpj,
    oi.orgao_nome,
    oi.ente_federativo,
    oi.uf,
    oi.municipio,
    oi.codigo_ibge,
    oi.numero_processo,
    oi.numero_edital,
    oi.modalidade,
    oi.modalidade_id,
    oi.objeto,
    oi.categoria,
    oi.valor_estimado,
    oi.valor_homologado,
    oi.valor_semantica,
    oi.data_publicacao,
    oi.data_abertura,
    oi.data_encerramento,
    oi.data_homologacao,
    oi.status_fonte,
    oi.status_canonico,
    oi.status_motivo,
    oi.status_data,
    oi.link_edital,
    oi.link_anexos,
    oi.qualidade_score,
    oi.qualidade_fatores,
    oi.dados_ausentes,
    oi.ranking,
    oi.ranking_score,
    oi.ranking_fatores,
    oi.ranking_regras,
    oi.ranking_confianca,
    oi.proveniencia,
    oi.is_active,
    oi.metadata,
    spe.razao_social AS orgao_razao_social,
    spe.municipio AS orgao_municipio,
    spe.distancia_fk AS distancia_florianopolis_km,
    spe.raio_200km
   FROM (public.opportunity_intel oi
     LEFT JOIN public.sc_public_entities spe ON ((oi.orgao_cnpj = spe.cnpj_8)))
  WHERE ((oi.status_canonico = ANY (ARRAY['open'::text, 'upcoming'::text])) AND (oi.is_active = true));


ALTER VIEW public.v_opportunity_open OWNER TO test;

--
-- Name: v_schema_integrity; Type: VIEW; Schema: public; Owner: test
--

CREATE VIEW public.v_schema_integrity AS
 SELECT 'tables'::text AS check_type,
    (count(*))::integer AS total_expected,
    (count(*) FILTER (WHERE (EXISTS ( SELECT 1
           FROM information_schema.tables t
          WHERE (((t.table_schema)::name = 'public'::name) AND ((t.table_name)::name = o.object_name))))))::integer AS present,
    (count(*) FILTER (WHERE (NOT (EXISTS ( SELECT 1
           FROM information_schema.tables t
          WHERE (((t.table_schema)::name = 'public'::name) AND ((t.table_name)::name = o.object_name)))))))::integer AS missing
   FROM ( VALUES ('pncp_raw_bids'::text), ('pncp_supplier_contracts'::text), ('sc_public_entities'::text), ('enriched_entities'::text), ('entity_coverage'::text), ('entity_hierarchy'::text), ('coverage_snapshots'::text), ('coverage_evidence'::text), ('opportunity_intel'::text), ('ingestion_runs'::text), ('ingestion_checkpoints'::text)) o(object_name)
UNION ALL
 SELECT 'views'::text AS check_type,
    (count(*))::integer AS total_expected,
    (count(*) FILTER (WHERE (EXISTS ( SELECT 1
           FROM information_schema.views v
          WHERE (((v.table_schema)::name = 'public'::name) AND ((v.table_name)::name = o.object_name))))))::integer AS present,
    (count(*) FILTER (WHERE (NOT (EXISTS ( SELECT 1
           FROM information_schema.views v
          WHERE (((v.table_schema)::name = 'public'::name) AND ((v.table_name)::name = o.object_name)))))))::integer AS missing
   FROM ( VALUES ('v_entities_canonical'::text), ('v_open_opportunities_canonical'::text), ('v_contracts_canonical'::text), ('v_suppliers_canonical'::text), ('v_value_observations_canonical'::text), ('v_latest_evidence'::text), ('v_source_health'::text), ('v_coverage_health'::text), ('v_schema_integrity'::text), ('v_capability_coverage_summary'::text)) o(object_name)
UNION ALL
 SELECT 'fk_constraints'::text AS check_type,
    (count(*))::integer AS total_expected,
    (count(*) FILTER (WHERE (EXISTS ( SELECT 1
           FROM (pg_constraint c
             JOIN pg_class cl ON ((c.conrelid = cl.oid)))
          WHERE (c.conname = o.object_name)))))::integer AS present,
    (count(*) FILTER (WHERE (NOT (EXISTS ( SELECT 1
           FROM (pg_constraint c
             JOIN pg_class cl ON ((c.conrelid = cl.oid)))
          WHERE (c.conname = o.object_name))))))::integer AS missing
   FROM ( VALUES ('fk_bids_orgao_entity'::text), ('fk_contracts_supplier_entity'::text), ('fk_contracts_orgao_entity'::text), ('uq_spe_cnpj_8'::text), ('uq_oi_content_hash'::text)) o(object_name);


ALTER VIEW public.v_schema_integrity OWNER TO test;

--
-- Name: VIEW v_schema_integrity; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON VIEW public.v_schema_integrity IS 'Schema integrity check — tables, views, constraints expected vs actual. Story 1.2';


--
-- Name: v_source_health; Type: VIEW; Schema: public; Owner: test
--

CREATE VIEW public.v_source_health AS
 SELECT source,
    count(*) FILTER (WHERE (entity_id IS NOT NULL)) AS total_entity_rows,
    count(*) FILTER (WHERE (entity_id IS NULL)) AS total_aggregate_rows,
    count(*) FILTER (WHERE ((entity_id IS NOT NULL) AND (state = 'success_with_data'::public.evidence_state))) AS success_with_data,
    count(*) FILTER (WHERE ((entity_id IS NOT NULL) AND (state = 'success_zero'::public.evidence_state))) AS success_zero,
    count(*) FILTER (WHERE ((entity_id IS NOT NULL) AND (state = 'partial'::public.evidence_state))) AS partial,
    count(*) FILTER (WHERE ((entity_id IS NOT NULL) AND (state = 'connection_failed'::public.evidence_state))) AS connection_failed,
    count(*) FILTER (WHERE ((entity_id IS NOT NULL) AND (state = 'auth_failed'::public.evidence_state))) AS auth_failed,
    count(*) FILTER (WHERE ((entity_id IS NOT NULL) AND (state = 'parse_failed'::public.evidence_state))) AS parse_failed,
    count(*) FILTER (WHERE ((entity_id IS NOT NULL) AND (state = 'transform_failed'::public.evidence_state))) AS transform_failed,
    count(*) FILTER (WHERE ((entity_id IS NOT NULL) AND (state = 'persist_failed'::public.evidence_state))) AS persist_failed,
    count(*) FILTER (WHERE ((entity_id IS NOT NULL) AND (state = 'not_applicable'::public.evidence_state))) AS not_applicable,
    count(*) FILTER (WHERE ((entity_id IS NOT NULL) AND (state = 'not_investigated'::public.evidence_state))) AS not_investigated,
    max(completed_at) AS last_check_at
   FROM public.v_latest_evidence
  GROUP BY source
  ORDER BY source;


ALTER VIEW public.v_source_health OWNER TO test;

--
-- Name: v_suppliers_canonical; Type: VIEW; Schema: public; Owner: test
--

CREATE VIEW public.v_suppliers_canonical AS
 SELECT e.cnpj AS cnpj_completo,
    e.razao_social,
    e.nome_fantasia,
    e.cnae_principal,
    e.cnae_secundarios,
    e.municipio,
    e.uf,
    e.codigo_ibge,
    e.natureza_juridica,
    e.situacao,
    e.enriched_at AS ultima_atualizacao,
    e.enriched_source,
    sc.cnpj_8 AS entidade_cnpj_8,
    sc.razao_social AS entidade_nome,
    sc.raio_200km AS within_200km,
    count(DISTINCT c.contrato_id) AS total_contratos,
    sum(c.valor_total) AS valor_total_contratos
   FROM ((public.enriched_entities e
     LEFT JOIN public.sc_public_entities sc ON ((sc.cnpj_8 = "left"(e.cnpj, 8))))
     LEFT JOIN public.pncp_supplier_contracts c ON ((c.fornecedor_cnpj = e.cnpj)))
  GROUP BY e.cnpj, e.razao_social, e.nome_fantasia, e.cnae_principal, e.cnae_secundarios, e.municipio, e.uf, e.codigo_ibge, e.natureza_juridica, e.situacao, e.enriched_at, e.enriched_source, sc.cnpj_8, sc.razao_social, sc.raio_200km;


ALTER VIEW public.v_suppliers_canonical OWNER TO test;

--
-- Name: VIEW v_suppliers_canonical; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON VIEW public.v_suppliers_canonical IS 'Canonical suppliers view v1.0 — fornecedores com agregacao de contratos. Story 1.2';


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

COMMENT ON VIEW public.v_unmatched_bids IS 'Bids sem matched_entity_id — para debugging do entity name-matching';


--
-- Name: COLUMN v_unmatched_bids.match_opportunity; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON COLUMN public.v_unmatched_bids.match_opportunity IS 'Indica se o bid tem CNPJ (has_cnpj) ou apenas nome (name_only) para match';


--
-- Name: COLUMN v_unmatched_bids.recency; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON COLUMN public.v_unmatched_bids.recency IS 'Indica se o bid e recente (90 dias) ou historico';


--
-- Name: v_value_observations_canonical; Type: VIEW; Schema: public; Owner: test
--

CREATE VIEW public.v_value_observations_canonical AS
 SELECT 'bid'::text AS observation_type,
    b.pncp_id AS source_id,
    b.orgao_cnpj,
    b.municipio,
    b.uf,
    b.modalidade_id,
    b.modalidade_nome AS modalidade,
    b.objeto_compra AS objeto,
    b.valor_total_estimado AS valor,
    b.data_publicacao,
    e.cnpj_8 AS entity_cnpj_8,
    e.raio_200km AS within_200km
   FROM (public.pncp_raw_bids b
     LEFT JOIN public.sc_public_entities e ON ((e.id = b.matched_entity_id)))
  WHERE ((b.valor_total_estimado IS NOT NULL) AND (b.valor_total_estimado > (0)::numeric))
UNION ALL
 SELECT 'contract'::text AS observation_type,
    c.contrato_id AS source_id,
    c.orgao_cnpj,
    c.municipio,
    c.uf,
    NULL::integer AS modalidade_id,
    NULL::text AS modalidade,
    c.objeto_contrato AS objeto,
    c.valor_total AS valor,
    c.data_publicacao,
    e.cnpj_8 AS entity_cnpj_8,
    e.raio_200km AS within_200km
   FROM (public.pncp_supplier_contracts c
     LEFT JOIN public.sc_public_entities e ON ((e.cnpj_8 = "left"(c.fornecedor_cnpj, 8))))
  WHERE ((c.valor_total IS NOT NULL) AND (c.valor_total > (0)::numeric));


ALTER VIEW public.v_value_observations_canonical OWNER TO test;

--
-- Name: VIEW v_value_observations_canonical; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON VIEW public.v_value_observations_canonical IS 'Canonical value observations view v1.0 — bids e contracts para analise. Story 1.2';


--
-- Name: COLUMN v_value_observations_canonical.observation_type; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON COLUMN public.v_value_observations_canonical.observation_type IS 'Tipo: ''bid'' para licitacao, ''contract'' para contrato';


--
-- Name: capability_coverage id; Type: DEFAULT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.capability_coverage ALTER COLUMN id SET DEFAULT nextval('public.capability_coverage_id_seq'::regclass);


--
-- Name: contract_version_history id; Type: DEFAULT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.contract_version_history ALTER COLUMN id SET DEFAULT nextval('public.contract_version_history_id_seq'::regclass);


--
-- Name: coverage_evidence id; Type: DEFAULT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.coverage_evidence ALTER COLUMN id SET DEFAULT nextval('public.coverage_evidence_id_seq'::regclass);


--
-- Name: coverage_snapshots id; Type: DEFAULT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.coverage_snapshots ALTER COLUMN id SET DEFAULT nextval('public.coverage_snapshots_id_seq'::regclass);


--
-- Name: ingestion_runs id; Type: DEFAULT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.ingestion_runs ALTER COLUMN id SET DEFAULT nextval('public.ingestion_runs_id_seq'::regclass);


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
-- Name: retention_policy id; Type: DEFAULT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.retention_policy ALTER COLUMN id SET DEFAULT nextval('public.retention_policy_id_seq'::regclass);


--
-- Name: sc_dados_abertos_backfill_log id; Type: DEFAULT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.sc_dados_abertos_backfill_log ALTER COLUMN id SET DEFAULT nextval('public.sc_dados_abertos_backfill_log_id_seq'::regclass);


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
-- Name: capability_coverage capability_coverage_pkey; Type: CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.capability_coverage
    ADD CONSTRAINT capability_coverage_pkey PRIMARY KEY (id);


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
-- Name: coverage_evidence ck_ce_success_zero_scope; Type: CHECK CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE public.coverage_evidence
    ADD CONSTRAINT ck_ce_success_zero_scope CHECK (((state <> 'success_zero'::public.evidence_state) OR ((queried_start IS NOT NULL) AND (queried_end IS NOT NULL) AND (scope_key IS NOT NULL) AND (pages_processed > 0) AND (((pages_expected IS NOT NULL) AND (pages_processed >= pages_expected)) OR ((pages_expected IS NULL) AND ((evidence_metadata ->> 'completion_rule'::text) = ANY (ARRAY['short_page_without_total'::text, 'empty_page_after_valid_scope'::text, 'http_204_complete'::text]))))))) NOT VALID;


--
-- Name: contract_version_history contract_version_history_pkey; Type: CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.contract_version_history
    ADD CONSTRAINT contract_version_history_pkey PRIMARY KEY (id);


--
-- Name: coverage_evidence coverage_evidence_pkey; Type: CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.coverage_evidence
    ADD CONSTRAINT coverage_evidence_pkey PRIMARY KEY (id);


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
-- Name: entity_hierarchy entity_hierarchy_pkey; Type: CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.entity_hierarchy
    ADD CONSTRAINT entity_hierarchy_pkey PRIMARY KEY (entity_id);


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
    ADD CONSTRAINT opportunity_checkpoints_pkey PRIMARY KEY (source, scope_key);


--
-- Name: opportunity_coverage opportunity_coverage_pkey; Type: CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.opportunity_coverage
    ADD CONSTRAINT opportunity_coverage_pkey PRIMARY KEY (entity_id, source);


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
-- Name: retention_policy retention_policy_pkey; Type: CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.retention_policy
    ADD CONSTRAINT retention_policy_pkey PRIMARY KEY (id);


--
-- Name: sc_dados_abertos_backfill_log sc_dados_abertos_backfill_log_pkey; Type: CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.sc_dados_abertos_backfill_log
    ADD CONSTRAINT sc_dados_abertos_backfill_log_pkey PRIMARY KEY (id);


--
-- Name: sc_public_entities sc_public_entities_pkey; Type: CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.sc_public_entities
    ADD CONSTRAINT sc_public_entities_pkey PRIMARY KEY (id);


--
-- Name: capability_coverage uq_cap_coverage; Type: CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.capability_coverage
    ADD CONSTRAINT uq_cap_coverage UNIQUE (capability, entity_id, source);


--
-- Name: contract_version_history uq_contract_version; Type: CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.contract_version_history
    ADD CONSTRAINT uq_contract_version UNIQUE (contrato_id, version);


--
-- Name: opportunity_intel uq_oi_content_hash; Type: CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.opportunity_intel
    ADD CONSTRAINT uq_oi_content_hash UNIQUE (content_hash);


--
-- Name: retention_policy uq_retention_policy; Type: CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.retention_policy
    ADD CONSTRAINT uq_retention_policy UNIQUE (table_name, field_name);


--
-- Name: sc_public_entities uq_spe_cnpj_8; Type: CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.sc_public_entities
    ADD CONSTRAINT uq_spe_cnpj_8 UNIQUE (cnpj_8);


--
-- Name: CONSTRAINT uq_spe_cnpj_8 ON sc_public_entities; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON CONSTRAINT uq_spe_cnpj_8 ON public.sc_public_entities IS 'Unique constraint on CNPJ base (8 digits). Created by Story 1.2 (DT-06).';


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
-- Name: INDEX idx_bids_matched_entity; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON INDEX public.idx_bids_matched_entity IS 'TD-DB-07: Partial index on matched_entity_id for coverage JOIN performance (Story TD-2.3)';


--
-- Name: idx_bids_modalidade; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_bids_modalidade ON public.pncp_raw_bids USING btree (modalidade_id, data_publicacao DESC);


--
-- Name: idx_bids_objeto_compra_gin; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_bids_objeto_compra_gin ON public.pncp_raw_bids USING gin (objeto_compra public.gin_trgm_ops) WHERE (is_active = true);


--
-- Name: INDEX idx_bids_objeto_compra_gin; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON INDEX public.idx_bids_objeto_compra_gin IS 'TD-DB-06: GIN trigram index on objeto_compra for fast ILIKE search (Story TD-2.3)';


--
-- Name: idx_bids_orgao_cnpj; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_bids_orgao_cnpj ON public.pncp_raw_bids USING btree (orgao_cnpj);


--
-- Name: idx_bids_orgao_cnpj_lookup; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_bids_orgao_cnpj_lookup ON public.pncp_raw_bids USING btree (orgao_cnpj, data_publicacao DESC) WHERE (orgao_cnpj IS NOT NULL);


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
-- Name: idx_cc_capability; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_cc_capability ON public.capability_coverage USING btree (capability, is_covered);


--
-- Name: idx_cc_entity; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_cc_entity ON public.capability_coverage USING btree (entity_id, capability) WHERE (entity_id IS NOT NULL);


--
-- Name: idx_ce_canonical_entity_source; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_ce_canonical_entity_source ON public.coverage_evidence USING btree (canonical_entity_key, source, checked_at DESC);


--
-- Name: idx_ce_completed; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_ce_completed ON public.coverage_evidence USING btree (completed_at);


--
-- Name: idx_ce_entity_source; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_ce_entity_source ON public.coverage_evidence USING btree (entity_id, source);


--
-- Name: idx_ce_run; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_ce_run ON public.coverage_evidence USING btree (run_id);


--
-- Name: idx_ce_source_state; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_ce_source_state ON public.coverage_evidence USING btree (source, state);


--
-- Name: idx_ce_state; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_ce_state ON public.coverage_evidence USING btree (state);


--
-- Name: idx_contracts_fornecedor_cnpj_lookup; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_contracts_fornecedor_cnpj_lookup ON public.pncp_supplier_contracts USING btree (fornecedor_cnpj) WHERE (fornecedor_cnpj IS NOT NULL);


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
-- Name: idx_cov_snap_reconciled; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_cov_snap_reconciled ON public.coverage_snapshots USING btree (source, source_reconciled) WHERE (source_reconciled = true);


--
-- Name: idx_cov_snap_source; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_cov_snap_source ON public.coverage_snapshots USING btree (source, snapshot_date);


--
-- Name: idx_cov_source; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_cov_source ON public.entity_coverage USING btree (source, is_covered);


--
-- Name: idx_cvh_changed_at; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_cvh_changed_at ON public.contract_version_history USING btree (changed_at DESC) WHERE (change_type = 'snapshot'::text);


--
-- Name: idx_cvh_contrato_id; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_cvh_contrato_id ON public.contract_version_history USING btree (contrato_id, version DESC);


--
-- Name: idx_ee_enriched_at; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_ee_enriched_at ON public.enriched_entities USING btree (enriched_at);


--
-- Name: idx_ee_uf; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_ee_uf ON public.enriched_entities USING btree (uf);


--
-- Name: idx_entity_hierarchy_coverage; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_entity_hierarchy_coverage ON public.entity_hierarchy USING btree (entity_id, parent_entity_id) INCLUDE (relationship);


--
-- Name: idx_entity_hierarchy_parent; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_entity_hierarchy_parent ON public.entity_hierarchy USING btree (parent_entity_id);


--
-- Name: idx_entity_hierarchy_relationship; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_entity_hierarchy_relationship ON public.entity_hierarchy USING btree (relationship);


--
-- Name: idx_ir_source_status; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_ir_source_status ON public.ingestion_runs USING btree (source, status);


--
-- Name: idx_ir_started; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_ir_started ON public.ingestion_runs USING btree (started_at DESC);


--
-- Name: idx_match_logging_lookup; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_match_logging_lookup ON public.pncp_raw_bids USING btree (match_method, matched_entity_id) WHERE (matched_entity_id IS NOT NULL);


--
-- Name: INDEX idx_match_logging_lookup; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON INDEX public.idx_match_logging_lookup IS 'TD-DB-07: Composite index for match_logging lookup (match_method + matched_entity_id)';


--
-- Name: idx_oc_last_attempt; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_oc_last_attempt ON public.opportunity_coverage USING btree (last_attempt DESC);


--
-- Name: idx_oc_result; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_oc_result ON public.opportunity_coverage USING btree (result);


--
-- Name: idx_oc_source; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_oc_source ON public.opportunity_coverage USING btree (source);


--
-- Name: idx_oi_codigo_ibge; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_oi_codigo_ibge ON public.opportunity_intel USING btree (codigo_ibge);


--
-- Name: idx_oi_crawl_batch_id; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_oi_crawl_batch_id ON public.opportunity_intel USING btree (crawl_batch_id);


--
-- Name: idx_oi_data_abertura; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_oi_data_abertura ON public.opportunity_intel USING btree (data_abertura);


--
-- Name: idx_oi_data_encerramento; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_oi_data_encerramento ON public.opportunity_intel USING btree (data_encerramento);


--
-- Name: idx_oi_ingested_at; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_oi_ingested_at ON public.opportunity_intel USING btree (ingested_at);


--
-- Name: idx_oi_is_active; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_oi_is_active ON public.opportunity_intel USING btree (is_active);


--
-- Name: idx_oi_modalidade; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_oi_modalidade ON public.opportunity_intel USING btree (modalidade);


--
-- Name: idx_oi_municipio; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_oi_municipio ON public.opportunity_intel USING btree (municipio);


--
-- Name: idx_oi_numero_controle_pncp; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_oi_numero_controle_pncp ON public.opportunity_intel USING btree (numero_controle_pncp);


--
-- Name: idx_oi_numero_edital; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_oi_numero_edital ON public.opportunity_intel USING btree (numero_edital);


--
-- Name: idx_oi_numero_processo; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_oi_numero_processo ON public.opportunity_intel USING btree (numero_processo);


--
-- Name: idx_oi_objeto_gin; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_oi_objeto_gin ON public.opportunity_intel USING gin (to_tsvector('portuguese'::regconfig, COALESCE(objeto, ''::text)));


--
-- Name: idx_oi_orgao_cnpj; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_oi_orgao_cnpj ON public.opportunity_intel USING btree (orgao_cnpj);


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
-- Name: idx_oi_source_status; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_oi_source_status ON public.opportunity_intel USING btree (source, status_canonico);


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
-- Name: idx_or_source; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_or_source ON public.opportunity_runs USING btree (source);


--
-- Name: idx_or_started_at; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_or_started_at ON public.opportunity_runs USING btree (started_at DESC);


--
-- Name: idx_or_status; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_or_status ON public.opportunity_runs USING btree (status);


--
-- Name: idx_psc_data; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_psc_data ON public.pncp_supplier_contracts USING btree (data_publicacao DESC);


--
-- Name: idx_psc_fornecedor; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_psc_fornecedor ON public.pncp_supplier_contracts USING btree (fornecedor_cnpj, data_publicacao DESC);


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
-- Name: idx_sdabfl_executed_at; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_sdabfl_executed_at ON public.sc_dados_abertos_backfill_log USING btree (executed_at DESC);


--
-- Name: idx_sdabfl_motivo; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_sdabfl_motivo ON public.sc_dados_abertos_backfill_log USING btree (motivo);


--
-- Name: idx_sdabfl_orgao_cnpj; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_sdabfl_orgao_cnpj ON public.sc_dados_abertos_backfill_log USING btree (orgao_cnpj);


--
-- Name: idx_spe_cnpj; Type: INDEX; Schema: public; Owner: test
--

CREATE INDEX idx_spe_cnpj ON public.sc_public_entities USING btree (cnpj_8);


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
-- Name: uq_ce_canonical_entity_run; Type: INDEX; Schema: public; Owner: test
--

CREATE UNIQUE INDEX uq_ce_canonical_entity_run ON public.coverage_evidence USING btree (canonical_entity_key, source, data_type, run_id) WHERE (canonical_entity_key IS NOT NULL);


--
-- Name: uq_ce_legacy_entity_run; Type: INDEX; Schema: public; Owner: test
--

CREATE UNIQUE INDEX uq_ce_legacy_entity_run ON public.coverage_evidence USING btree (entity_id, source, data_type, run_id) WHERE ((canonical_entity_key IS NULL) AND (entity_id IS NOT NULL));


--
-- Name: uq_ce_source_aggregate_run; Type: INDEX; Schema: public; Owner: test
--

CREATE UNIQUE INDEX uq_ce_source_aggregate_run ON public.coverage_evidence USING btree (source, data_type, run_id) WHERE (entity_id IS NULL);


--
-- Name: uq_oi_orgao_processo_edital; Type: INDEX; Schema: public; Owner: test
--

CREATE UNIQUE INDEX uq_oi_orgao_processo_edital ON public.opportunity_intel USING btree (orgao_cnpj, numero_processo, numero_edital) WHERE ((orgao_cnpj IS NOT NULL) AND (numero_processo IS NOT NULL) AND (numero_edital IS NOT NULL) AND (is_active = true));


--
-- Name: uq_oi_pncp_id; Type: INDEX; Schema: public; Owner: test
--

CREATE UNIQUE INDEX uq_oi_pncp_id ON public.opportunity_intel USING btree (numero_controle_pncp) WHERE ((numero_controle_pncp IS NOT NULL) AND (is_active = true));


--
-- Name: uq_or_external_run_id; Type: INDEX; Schema: public; Owner: test
--

CREATE UNIQUE INDEX uq_or_external_run_id ON public.opportunity_runs USING btree (external_run_id) WHERE (external_run_id IS NOT NULL);


--
-- Name: pncp_raw_bids trg_bids_coverage; Type: TRIGGER; Schema: public; Owner: test
--

CREATE TRIGGER trg_bids_coverage AFTER INSERT ON public.pncp_raw_bids FOR EACH ROW EXECUTE FUNCTION public.update_entity_coverage();


--
-- Name: pncp_raw_bids trg_bids_coverage_update; Type: TRIGGER; Schema: public; Owner: test
--

CREATE TRIGGER trg_bids_coverage_update AFTER UPDATE ON public.pncp_raw_bids FOR EACH ROW WHEN ((old.matched_entity_id IS DISTINCT FROM new.matched_entity_id)) EXECUTE FUNCTION public.update_entity_coverage_on_update();


--
-- Name: pncp_raw_bids trg_bids_updated_at; Type: TRIGGER; Schema: public; Owner: test
--

CREATE TRIGGER trg_bids_updated_at BEFORE UPDATE ON public.pncp_raw_bids FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: capability_coverage trg_cap_coverage_updated_at; Type: TRIGGER; Schema: public; Owner: test
--

CREATE TRIGGER trg_cap_coverage_updated_at BEFORE UPDATE ON public.capability_coverage FOR EACH ROW EXECUTE FUNCTION public.fn_cap_coverage_updated_at();


--
-- Name: pncp_supplier_contracts trg_contract_versioning; Type: TRIGGER; Schema: public; Owner: test
--

CREATE TRIGGER trg_contract_versioning AFTER INSERT OR DELETE OR UPDATE ON public.pncp_supplier_contracts FOR EACH ROW EXECUTE FUNCTION public.fn_capture_contract_snapshot();

ALTER TABLE public.pncp_supplier_contracts DISABLE TRIGGER trg_contract_versioning;


--
-- Name: TRIGGER trg_contract_versioning ON pncp_supplier_contracts; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON TRIGGER trg_contract_versioning ON public.pncp_supplier_contracts IS 'Contract versioning trigger — DISABLED by default. Enable via: ALTER TABLE ... ENABLE TRIGGER trg_contract_versioning; Story 1.2';


--
-- Name: entity_hierarchy trg_entity_hierarchy_timestamp; Type: TRIGGER; Schema: public; Owner: test
--

CREATE TRIGGER trg_entity_hierarchy_timestamp BEFORE UPDATE ON public.entity_hierarchy FOR EACH ROW EXECUTE FUNCTION public.update_entity_hierarchy_timestamp();


--
-- Name: opportunity_intel trg_opportunity_intel_last_seen; Type: TRIGGER; Schema: public; Owner: test
--

CREATE TRIGGER trg_opportunity_intel_last_seen BEFORE UPDATE ON public.opportunity_intel FOR EACH ROW EXECUTE FUNCTION public.trg_oi_last_seen();


--
-- Name: opportunity_intel trg_opportunity_intel_updated_at; Type: TRIGGER; Schema: public; Owner: test
--

CREATE TRIGGER trg_opportunity_intel_updated_at BEFORE UPDATE ON public.opportunity_intel FOR EACH ROW EXECUTE FUNCTION public.trg_oi_updated_at();


--
-- Name: entity_coverage entity_coverage_entity_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.entity_coverage
    ADD CONSTRAINT entity_coverage_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES public.sc_public_entities(id) ON DELETE CASCADE;


--
-- Name: entity_hierarchy entity_hierarchy_entity_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.entity_hierarchy
    ADD CONSTRAINT entity_hierarchy_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES public.sc_public_entities(id);


--
-- Name: entity_hierarchy entity_hierarchy_parent_entity_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.entity_hierarchy
    ADD CONSTRAINT entity_hierarchy_parent_entity_id_fkey FOREIGN KEY (parent_entity_id) REFERENCES public.sc_public_entities(id);


--
-- Name: pncp_raw_bids fk_bids_matched_entity; Type: FK CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.pncp_raw_bids
    ADD CONSTRAINT fk_bids_matched_entity FOREIGN KEY (matched_entity_id) REFERENCES public.sc_public_entities(id) ON DELETE SET NULL;


--
-- Name: pncp_raw_bids fk_bids_orgao_entity; Type: FK CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.pncp_raw_bids
    ADD CONSTRAINT fk_bids_orgao_entity FOREIGN KEY (orgao_cnpj) REFERENCES public.sc_public_entities(cnpj_8) ON UPDATE CASCADE ON DELETE SET NULL NOT VALID;


--
-- Name: CONSTRAINT fk_bids_orgao_entity ON pncp_raw_bids; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON CONSTRAINT fk_bids_orgao_entity ON public.pncp_raw_bids IS 'FK orgao_cnpj → sc_public_entities.cnpj_8. Created NOT VALID por Story 1.2 (DT-19). Validar: ALTER TABLE pncp_raw_bids VALIDATE CONSTRAINT fk_bids_orgao_entity;';


--
-- Name: pncp_supplier_contracts fk_contracts_orgao_entity; Type: FK CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.pncp_supplier_contracts
    ADD CONSTRAINT fk_contracts_orgao_entity FOREIGN KEY (orgao_cnpj) REFERENCES public.sc_public_entities(cnpj_8) ON UPDATE CASCADE ON DELETE SET NULL NOT VALID;


--
-- Name: pncp_supplier_contracts fk_contracts_supplier_entity; Type: FK CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.pncp_supplier_contracts
    ADD CONSTRAINT fk_contracts_supplier_entity FOREIGN KEY (fornecedor_cnpj) REFERENCES public.sc_public_entities(cnpj_8) ON UPDATE CASCADE ON DELETE SET NULL NOT VALID;


--
-- Name: CONSTRAINT fk_contracts_supplier_entity ON pncp_supplier_contracts; Type: COMMENT; Schema: public; Owner: test
--

COMMENT ON CONSTRAINT fk_contracts_supplier_entity ON public.pncp_supplier_contracts IS 'FK fornecedor_cnpj → sc_public_entities.cnpj_8. Story 1.2 (DT-20).';


--
-- Name: opportunity_intel fk_oi_run_id; Type: FK CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.opportunity_intel
    ADD CONSTRAINT fk_oi_run_id FOREIGN KEY (run_id) REFERENCES public.opportunity_runs(id) ON DELETE SET NULL;


--
-- Name: opportunity_coverage opportunity_coverage_entity_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: test
--

ALTER TABLE ONLY public.opportunity_coverage
    ADD CONSTRAINT opportunity_coverage_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES public.sc_public_entities(id);


--
-- Name: SCHEMA public; Type: ACL; Schema: -; Owner: test
--

REVOKE USAGE ON SCHEMA public FROM PUBLIC;
GRANT ALL ON SCHEMA public TO PUBLIC;


--
-- PostgreSQL database dump complete
--

\unrestrict smZnMxUC7BX8xGUQA3b2YBIXvLch7ZUsJaIF2eekmoOaYYnqClYfBk4mlzoDy5e

