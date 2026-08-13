-- 089_canonical_snapshot_public_read_v1.sql
-- Client-independent multifonte snapshot barrier and SELECT-only public contract (#287/#354).

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

CREATE TABLE IF NOT EXISTS public.canonical_public_snapshots (
    snapshot_id              TEXT PRIMARY KEY,
    cutoff_at                TIMESTAMPTZ NOT NULL,
    cutoff_timezone          TEXT NOT NULL DEFAULT 'America/Sao_Paulo'
                                  CHECK (cutoff_timezone = 'America/Sao_Paulo'),
    universe_hash            TEXT NOT NULL CHECK (universe_hash ~ '^[0-9a-f]{64}$'),
    policy_hash              TEXT NOT NULL CHECK (policy_hash ~ '^[0-9a-f]{64}$'),
    schema_hash              TEXT NOT NULL CHECK (schema_hash ~ '^[0-9a-f]{64}$'),
    adapter_hash             TEXT NOT NULL CHECK (adapter_hash ~ '^[0-9a-f]{64}$'),
    data_hash                TEXT NOT NULL CHECK (data_hash ~ '^[0-9a-f]{64}$'),
    document_hash            TEXT NOT NULL CHECK (document_hash ~ '^[0-9a-f]{64}$'),
    dossier_hash             TEXT NOT NULL CHECK (dossier_hash ~ '^[0-9a-f]{64}$'),
    state                    TEXT NOT NULL DEFAULT 'BUILDING'
                                  CHECK (state IN ('BUILDING', 'BLOCKED', 'READY_CANONICAL', 'SUPERSEDED')),
    required_pair_count      INTEGER NOT NULL CHECK (required_pair_count >= 0),
    relevant_dossier_count   INTEGER NOT NULL CHECK (relevant_dossier_count >= 0),
    blockers                 JSONB NOT NULL DEFAULT '[]'::JSONB,
    content_hash             TEXT CHECK (content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'),
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at                TIMESTAMPTZ,
    superseded_at            TIMESTAMPTZ,
    created_by               TEXT NOT NULL,
    CHECK (snapshot_id !~* 'client|profile'),
    CHECK (state <> 'READY_CANONICAL' OR (closed_at IS NOT NULL AND content_hash IS NOT NULL AND blockers = '[]'::JSONB))
);

CREATE INDEX IF NOT EXISTS idx_canonical_snapshots_ready
    ON public.canonical_public_snapshots (cutoff_at DESC, snapshot_id)
    WHERE state = 'READY_CANONICAL';

CREATE TABLE IF NOT EXISTS public.canonical_snapshot_source_watermarks (
    snapshot_id              TEXT NOT NULL REFERENCES public.canonical_public_snapshots(snapshot_id),
    source                   TEXT NOT NULL,
    source_run_id            TEXT NOT NULL,
    watermark_at             TIMESTAMPTZ NOT NULL,
    freshness_state          TEXT NOT NULL CHECK (freshness_state IN ('FRESH', 'STALE', 'FAILED', 'BLOCKED', 'UNKNOWN')),
    completeness_state       TEXT NOT NULL CHECK (completeness_state IN ('COMPLETE', 'INCOMPLETE', 'UNKNOWN')),
    applicable_pair_count    INTEGER NOT NULL CHECK (applicable_pair_count >= 0),
    evaluated_pair_count     INTEGER NOT NULL CHECK (evaluated_pair_count >= 0),
    evidence_hash            TEXT NOT NULL CHECK (evidence_hash ~ '^[0-9a-f]{64}$'),
    recorded_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (snapshot_id, source)
);

CREATE TABLE IF NOT EXISTS public.canonical_snapshot_event_revisions (
    snapshot_id              TEXT NOT NULL REFERENCES public.canonical_public_snapshots(snapshot_id),
    event_id                 TEXT NOT NULL REFERENCES public.canonical_public_events_v1(event_id),
    revision_id              TEXT NOT NULL REFERENCES public.canonical_event_revisions(revision_id),
    fact_hash                TEXT NOT NULL CHECK (fact_hash ~ '^[0-9a-f]{64}$'),
    included_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (snapshot_id, event_id),
    UNIQUE (snapshot_id, revision_id)
);

CREATE INDEX IF NOT EXISTS idx_snapshot_revision_lookup
    ON public.canonical_snapshot_event_revisions (event_id, snapshot_id, revision_id);

CREATE TABLE IF NOT EXISTS public.canonical_snapshot_documents (
    snapshot_id              TEXT NOT NULL REFERENCES public.canonical_public_snapshots(snapshot_id),
    observation_id           TEXT NOT NULL REFERENCES public.canonical_public_observations(observation_id),
    document_sha256          TEXT NOT NULL CHECK (document_sha256 ~ '^[0-9a-f]{64}$'),
    completeness_state       TEXT NOT NULL CHECK (completeness_state IN ('COMPLETE', 'INCOMPLETE', 'BLOCKED')),
    PRIMARY KEY (snapshot_id, observation_id, document_sha256)
);

CREATE TABLE IF NOT EXISTS public.canonical_snapshot_dossiers (
    snapshot_id              TEXT NOT NULL REFERENCES public.canonical_public_snapshots(snapshot_id),
    dossier_id               TEXT NOT NULL,
    dossier_revision_hash    TEXT NOT NULL CHECK (dossier_revision_hash ~ '^[0-9a-f]{64}$'),
    completeness_state       TEXT NOT NULL CHECK (completeness_state IN ('COMPLETE', 'INCOMPLETE', 'BLOCKED')),
    reason_codes             TEXT[] NOT NULL DEFAULT '{}',
    PRIMARY KEY (snapshot_id, dossier_id)
);

CREATE TABLE IF NOT EXISTS public.canonical_snapshot_invalidations (
    invalidation_id          TEXT PRIMARY KEY,
    snapshot_id              TEXT NOT NULL REFERENCES public.canonical_public_snapshots(snapshot_id),
    event_id                 TEXT NOT NULL REFERENCES public.canonical_public_events_v1(event_id),
    prior_revision_id        TEXT NOT NULL REFERENCES public.canonical_event_revisions(revision_id),
    new_revision_id          TEXT NOT NULL REFERENCES public.canonical_event_revisions(revision_id),
    reason                   TEXT NOT NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (snapshot_id, new_revision_id)
);

CREATE TABLE IF NOT EXISTS public.public_consumer_projections (
    projection_id            TEXT PRIMARY KEY,
    consumer_id              TEXT NOT NULL,
    snapshot_id              TEXT NOT NULL REFERENCES public.canonical_public_snapshots(snapshot_id),
    template_hash            TEXT NOT NULL CHECK (template_hash ~ '^[0-9a-f]{64}$'),
    private_profile_hash     TEXT,
    state                    TEXT NOT NULL DEFAULT 'READY'
                                  CHECK (state IN ('READY', 'STALE_PRIVATE', 'STALE_FACTUAL', 'BLOCKED')),
    invalidation_reason      TEXT,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    invalidated_at           TIMESTAMPTZ,
    UNIQUE (consumer_id, snapshot_id, template_hash, private_profile_hash)
);

CREATE INDEX IF NOT EXISTS idx_consumer_projection_snapshot
    ON public.public_consumer_projections (snapshot_id, state, consumer_id);

CREATE TABLE IF NOT EXISTS public.public_read_surface_health_internal (
    view_name                TEXT PRIMARY KEY,
    enabled                  BOOLEAN NOT NULL DEFAULT TRUE,
    refreshed_at             TIMESTAMPTZ,
    query_count              BIGINT NOT NULL DEFAULT 0 CHECK (query_count >= 0),
    error_count              BIGINT NOT NULL DEFAULT 0 CHECK (error_count >= 0),
    query_p95_ms             NUMERIC,
    last_refresh_status      TEXT NOT NULL DEFAULT 'NEVER'
                                  CHECK (last_refresh_status IN ('NEVER', 'VALID', 'FAILED', 'STALE')),
    last_error               TEXT,
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO public.public_read_surface_health_internal (view_name)
VALUES ('snapshots'), ('tenders'), ('contracts'), ('entities'), ('suppliers'), ('organs'), ('municipalities')
ON CONFLICT (view_name) DO NOTHING;

CREATE OR REPLACE FUNCTION public.begin_canonical_public_snapshot_v1(
    p_cutoff_at TIMESTAMPTZ,
    p_universe_hash TEXT,
    p_policy_hash TEXT,
    p_schema_hash TEXT,
    p_adapter_hash TEXT,
    p_data_hash TEXT,
    p_document_hash TEXT,
    p_dossier_hash TEXT,
    p_required_pair_count INTEGER,
    p_relevant_dossier_count INTEGER,
    p_created_by TEXT
)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    result_id TEXT;
BEGIN
    IF p_created_by ~* 'client|profile' THEN
        RAISE EXCEPTION 'canonical snapshot creator cannot encode client/profile identity' USING ERRCODE = '22023';
    END IF;
    result_id := public.canonical_public_id('snp', ARRAY[
        p_cutoff_at::TEXT, p_universe_hash, p_policy_hash, p_schema_hash,
        p_adapter_hash, p_data_hash, p_document_hash, p_dossier_hash
    ]);
    INSERT INTO public.canonical_public_snapshots (
        snapshot_id, cutoff_at, universe_hash, policy_hash, schema_hash,
        adapter_hash, data_hash, document_hash, dossier_hash,
        required_pair_count, relevant_dossier_count, created_by
    ) VALUES (
        result_id, p_cutoff_at, p_universe_hash, p_policy_hash, p_schema_hash,
        p_adapter_hash, p_data_hash, p_document_hash, p_dossier_hash,
        p_required_pair_count, p_relevant_dossier_count, p_created_by
    ) ON CONFLICT (snapshot_id) DO NOTHING;
    RETURN result_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.put_canonical_snapshot_watermark_v1(
    p_snapshot_id TEXT,
    p_source TEXT,
    p_source_run_id TEXT,
    p_watermark_at TIMESTAMPTZ,
    p_freshness_state TEXT,
    p_completeness_state TEXT,
    p_applicable_pair_count INTEGER,
    p_evaluated_pair_count INTEGER,
    p_evidence_hash TEXT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    cutoff_value TIMESTAMPTZ;
BEGIN
    SELECT cutoff_at INTO STRICT cutoff_value FROM public.canonical_public_snapshots
    WHERE snapshot_id = p_snapshot_id AND state IN ('BUILDING', 'BLOCKED') FOR UPDATE;
    IF p_watermark_at > cutoff_value THEN
        RAISE EXCEPTION 'source watermark is after snapshot cutoff' USING ERRCODE = '22023';
    END IF;
    INSERT INTO public.canonical_snapshot_source_watermarks (
        snapshot_id, source, source_run_id, watermark_at, freshness_state,
        completeness_state, applicable_pair_count, evaluated_pair_count, evidence_hash
    ) VALUES (
        p_snapshot_id, p_source, p_source_run_id, p_watermark_at,
        p_freshness_state, p_completeness_state,
        p_applicable_pair_count, p_evaluated_pair_count, p_evidence_hash
    ) ON CONFLICT (snapshot_id, source) DO UPDATE SET
        source_run_id = EXCLUDED.source_run_id,
        watermark_at = EXCLUDED.watermark_at,
        freshness_state = EXCLUDED.freshness_state,
        completeness_state = EXCLUDED.completeness_state,
        applicable_pair_count = EXCLUDED.applicable_pair_count,
        evaluated_pair_count = EXCLUDED.evaluated_pair_count,
        evidence_hash = EXCLUDED.evidence_hash,
        recorded_at = NOW();
END;
$$;

CREATE OR REPLACE FUNCTION public.close_canonical_public_snapshot_v1(p_snapshot_id TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO public, pg_temp
AS $$
DECLARE
    snapshot_row public.canonical_public_snapshots%ROWTYPE;
    blocker_list JSONB := '[]'::JSONB;
    watermark_count INTEGER;
    evaluated_pairs INTEGER;
    dossier_count INTEGER;
    revision_count INTEGER;
    result_hash TEXT;
BEGIN
    SELECT * INTO STRICT snapshot_row FROM public.canonical_public_snapshots
    WHERE snapshot_id = p_snapshot_id FOR UPDATE;
    IF snapshot_row.state = 'READY_CANONICAL' THEN
        RETURN jsonb_build_object('snapshot_id', p_snapshot_id, 'state', snapshot_row.state, 'content_hash', snapshot_row.content_hash, 'blockers', snapshot_row.blockers);
    END IF;

    SELECT count(*), COALESCE(sum(evaluated_pair_count), 0)
    INTO watermark_count, evaluated_pairs
    FROM public.canonical_snapshot_source_watermarks WHERE snapshot_id = p_snapshot_id;
    SELECT count(*) INTO dossier_count FROM public.canonical_snapshot_dossiers
    WHERE snapshot_id = p_snapshot_id AND completeness_state = 'COMPLETE';
    SELECT count(*) INTO revision_count FROM public.canonical_snapshot_event_revisions
    WHERE snapshot_id = p_snapshot_id;

    IF watermark_count = 0 THEN blocker_list := blocker_list || '"missing_source_watermarks"'::JSONB; END IF;
    IF EXISTS (SELECT 1 FROM public.canonical_snapshot_source_watermarks WHERE snapshot_id = p_snapshot_id AND (freshness_state <> 'FRESH' OR completeness_state <> 'COMPLETE' OR evaluated_pair_count < applicable_pair_count)) THEN
        blocker_list := blocker_list || '"source_freshness_or_completeness_failed"'::JSONB;
    END IF;
    IF evaluated_pairs < snapshot_row.required_pair_count THEN blocker_list := blocker_list || '"applicable_pairs_not_evaluated"'::JSONB; END IF;
    IF dossier_count < snapshot_row.relevant_dossier_count THEN blocker_list := blocker_list || '"relevant_dossiers_not_complete"'::JSONB; END IF;
    IF EXISTS (SELECT 1 FROM public.canonical_snapshot_documents WHERE snapshot_id = p_snapshot_id AND completeness_state <> 'COMPLETE') THEN
        blocker_list := blocker_list || '"documents_incomplete"'::JSONB;
    END IF;
    IF revision_count = 0 THEN blocker_list := blocker_list || '"no_canonical_event_revisions"'::JSONB; END IF;

    PERFORM set_config('app.canonical_snapshot_transition', 'on', TRUE);
    IF blocker_list <> '[]'::JSONB THEN
        UPDATE public.canonical_public_snapshots SET state = 'BLOCKED', blockers = blocker_list
        WHERE snapshot_id = p_snapshot_id;
        PERFORM set_config('app.canonical_snapshot_transition', 'off', TRUE);
        RETURN jsonb_build_object('snapshot_id', p_snapshot_id, 'state', 'BLOCKED', 'blockers', blocker_list);
    END IF;

    SELECT encode(digest(concat_ws('|',
        snapshot_row.snapshot_id, snapshot_row.universe_hash, snapshot_row.policy_hash,
        snapshot_row.schema_hash, snapshot_row.adapter_hash, snapshot_row.data_hash,
        snapshot_row.document_hash, snapshot_row.dossier_hash,
        COALESCE((SELECT string_agg(source || ':' || source_run_id || ':' || watermark_at::TEXT || ':' || evidence_hash, ',' ORDER BY source) FROM public.canonical_snapshot_source_watermarks WHERE snapshot_id = p_snapshot_id), ''),
        COALESCE((SELECT string_agg(event_id || ':' || revision_id || ':' || fact_hash, ',' ORDER BY event_id) FROM public.canonical_snapshot_event_revisions WHERE snapshot_id = p_snapshot_id), ''),
        COALESCE((SELECT string_agg(observation_id || ':' || document_sha256, ',' ORDER BY observation_id, document_sha256) FROM public.canonical_snapshot_documents WHERE snapshot_id = p_snapshot_id), ''),
        COALESCE((SELECT string_agg(dossier_id || ':' || dossier_revision_hash, ',' ORDER BY dossier_id) FROM public.canonical_snapshot_dossiers WHERE snapshot_id = p_snapshot_id), '')
    ), 'sha256'), 'hex') INTO result_hash;

    UPDATE public.canonical_public_snapshots
    SET state = 'READY_CANONICAL', blockers = '[]'::JSONB,
        content_hash = result_hash, closed_at = NOW()
    WHERE snapshot_id = p_snapshot_id;
    UPDATE public.public_read_surface_health_internal
    SET refreshed_at = NOW(), last_refresh_status = 'VALID', last_error = NULL, updated_at = NOW()
    WHERE enabled;
    PERFORM set_config('app.canonical_snapshot_transition', 'off', TRUE);
    RETURN jsonb_build_object('snapshot_id', p_snapshot_id, 'state', 'READY_CANONICAL', 'content_hash', result_hash, 'blockers', '[]'::JSONB);
END;
$$;

REVOKE ALL ON FUNCTION public.close_canonical_public_snapshot_v1(TEXT) FROM PUBLIC;

CREATE OR REPLACE FUNCTION public.invalidate_consumer_projection_private_v1(
    p_projection_id TEXT,
    p_new_template_hash TEXT,
    p_new_private_profile_hash TEXT
)
RETURNS VOID
LANGUAGE sql
AS $$
    UPDATE public.public_consumer_projections
    SET state = 'STALE_PRIVATE', invalidated_at = NOW(),
        invalidation_reason = concat('private/template change:', p_new_template_hash, ':', COALESCE(p_new_private_profile_hash, 'none'))
    WHERE projection_id = p_projection_id;
$$;

CREATE OR REPLACE FUNCTION public.fanout_canonical_revision_invalidation_v1()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO public.canonical_snapshot_invalidations (
        invalidation_id, snapshot_id, event_id, prior_revision_id, new_revision_id, reason
    )
    SELECT public.canonical_public_id('inv', ARRAY[membership.snapshot_id, NEW.revision_id]),
           membership.snapshot_id, NEW.event_id, membership.revision_id, NEW.revision_id,
           'new_factual_revision_after_snapshot_cutoff'
    FROM public.canonical_snapshot_event_revisions membership
    JOIN public.canonical_public_snapshots snapshot USING (snapshot_id)
    WHERE membership.event_id = NEW.event_id
      AND membership.revision_id <> NEW.revision_id
      AND snapshot.state = 'READY_CANONICAL'
      AND NEW.system_from > snapshot.cutoff_at
    ON CONFLICT DO NOTHING;

    UPDATE public.public_consumer_projections projection
    SET state = 'STALE_FACTUAL', invalidated_at = NOW(),
        invalidation_reason = 'new_factual_revision:' || NEW.revision_id
    WHERE projection.snapshot_id IN (
        SELECT snapshot_id FROM public.canonical_snapshot_invalidations
        WHERE new_revision_id = NEW.revision_id
    ) AND projection.state = 'READY';
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_canonical_revision_snapshot_fanout ON public.canonical_event_revisions;
CREATE TRIGGER trg_canonical_revision_snapshot_fanout
    AFTER INSERT ON public.canonical_event_revisions
    FOR EACH ROW EXECUTE FUNCTION public.fanout_canonical_revision_invalidation_v1();

CREATE OR REPLACE FUNCTION public.guard_closed_canonical_snapshot_v1()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    guarded_snapshot_id TEXT;
    guarded_state TEXT;
BEGIN
    IF current_setting('app.allow_canonical_test_cleanup', TRUE) = 'on'
       AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = current_user AND rolsuper) THEN
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END IF;
    guarded_snapshot_id := CASE WHEN TG_TABLE_NAME = 'canonical_public_snapshots'
        THEN COALESCE(OLD.snapshot_id, NEW.snapshot_id)
        ELSE COALESCE(NEW.snapshot_id, OLD.snapshot_id) END;
    SELECT state INTO guarded_state FROM public.canonical_public_snapshots WHERE snapshot_id = guarded_snapshot_id;
    IF TG_TABLE_NAME = 'canonical_snapshot_source_watermarks' AND TG_OP <> 'DELETE' THEN
        IF NEW.watermark_at > (SELECT cutoff_at FROM public.canonical_public_snapshots WHERE snapshot_id = guarded_snapshot_id) THEN
            RAISE EXCEPTION 'source watermark is after snapshot cutoff' USING ERRCODE = '22023';
        END IF;
    END IF;
    IF TG_TABLE_NAME = 'canonical_snapshot_event_revisions' AND TG_OP <> 'DELETE' THEN
        IF NOT EXISTS (
            SELECT 1 FROM public.canonical_event_revisions revision
            WHERE revision.revision_id = NEW.revision_id
              AND revision.event_id = NEW.event_id
              AND revision.fact_hash = NEW.fact_hash
        ) THEN
            RAISE EXCEPTION 'snapshot event/revision/fact tuple is inconsistent' USING ERRCODE = '23514';
        END IF;
    END IF;
    IF guarded_state IN ('READY_CANONICAL', 'SUPERSEDED')
       AND NOT (
           current_setting('app.canonical_snapshot_transition', TRUE) = 'on'
           AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = current_user AND rolsuper)
       ) THEN
        RAISE EXCEPTION 'closed canonical snapshot % is immutable', guarded_snapshot_id USING ERRCODE = '55000';
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

DROP TRIGGER IF EXISTS trg_canonical_snapshot_guard ON public.canonical_public_snapshots;
CREATE TRIGGER trg_canonical_snapshot_guard BEFORE UPDATE OR DELETE ON public.canonical_public_snapshots
FOR EACH ROW EXECUTE FUNCTION public.guard_closed_canonical_snapshot_v1();

DO $$
DECLARE table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'canonical_snapshot_source_watermarks', 'canonical_snapshot_event_revisions',
        'canonical_snapshot_documents', 'canonical_snapshot_dossiers'
    ] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trg_closed_snapshot_membership_guard ON public.%I', table_name);
        EXECUTE format('CREATE TRIGGER trg_closed_snapshot_membership_guard BEFORE INSERT OR UPDATE OR DELETE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.guard_closed_canonical_snapshot_v1()', table_name);
    END LOOP;
END $$;

CREATE SCHEMA IF NOT EXISTS public_read_v1;

CREATE OR REPLACE VIEW public_read_v1.current_snapshot AS
SELECT snapshot_id, cutoff_at AS as_of, content_hash, universe_hash, policy_hash,
       schema_hash, adapter_hash, data_hash, document_hash, dossier_hash,
       closed_at, 'COMPLETE'::TEXT AS completeness,
       jsonb_build_object('snapshot_id', snapshot_id, 'content_hash', content_hash) AS provenance
FROM public.canonical_public_snapshots
WHERE state = 'READY_CANONICAL'
ORDER BY cutoff_at DESC, snapshot_id DESC
LIMIT 1;

CREATE OR REPLACE VIEW public_read_v1.access_gate AS
SELECT NOT COALESCE((SELECT enabled FROM public.truth_plane_kill_switch WHERE singleton), TRUE) AS enabled;

CREATE OR REPLACE VIEW public_read_v1.tenders AS
SELECT event.event_id, event.process_key, event.event_type, revision.status_code,
       revision.title, revision.publication_at, revision.official_number,
       snapshot.as_of, revision.system_from AS source_updated_at,
       'COMPLETE'::TEXT AS completeness, ARRAY[]::TEXT[] AS reason_codes,
       observation.source, observation.source_uri,
       jsonb_build_object('observation_id', observation.observation_id, 'raw_sha256', observation.raw_sha256, 'revision_id', revision.revision_id, 'snapshot_id', snapshot.snapshot_id) AS provenance
FROM public_read_v1.current_snapshot snapshot
JOIN public.canonical_snapshot_event_revisions membership USING (snapshot_id)
JOIN public.canonical_public_events_v1 event USING (event_id)
JOIN public.canonical_event_revisions revision USING (revision_id)
JOIN public.canonical_public_observations observation ON observation.observation_id = revision.created_from_observation_id
CROSS JOIN public_read_v1.access_gate gate
WHERE event.event_type IN ('tender_publication', 'tender_status', 'tender_document_change') AND gate.enabled;

CREATE OR REPLACE VIEW public_read_v1.contracts AS
SELECT event.event_id, event.process_key, revision.status_code, revision.title,
       revision.contract_value, revision.official_number,
       snapshot.as_of, revision.system_from AS source_updated_at,
       'COMPLETE'::TEXT AS completeness, ARRAY[]::TEXT[] AS reason_codes,
       observation.source, observation.source_uri,
       jsonb_build_object('observation_id', observation.observation_id, 'raw_sha256', observation.raw_sha256, 'revision_id', revision.revision_id, 'snapshot_id', snapshot.snapshot_id) AS provenance
FROM public_read_v1.current_snapshot snapshot
JOIN public.canonical_snapshot_event_revisions membership USING (snapshot_id)
JOIN public.canonical_public_events_v1 event USING (event_id)
JOIN public.canonical_event_revisions revision USING (revision_id)
JOIN public.canonical_public_observations observation ON observation.observation_id = revision.created_from_observation_id
CROSS JOIN public_read_v1.access_gate gate
WHERE event.event_type = 'contract_lifecycle' AND gate.enabled;

CREATE OR REPLACE VIEW public_read_v1.entities AS
WITH entity_links AS (
    SELECT DISTINCT snapshot.snapshot_id, snapshot.as_of, link.entity_id,
           link.event_id, link.observation_id
    FROM public_read_v1.current_snapshot snapshot
    JOIN public.canonical_snapshot_event_revisions membership USING (snapshot_id)
    JOIN public.canonical_event_entity_links link USING (event_id)
    CROSS JOIN public_read_v1.access_gate gate
    WHERE gate.enabled
), entity_provenance AS (
    SELECT snapshot_id, as_of, entity_id,
           jsonb_agg(
               jsonb_build_object('event_id', event_id, 'observation_id', observation_id)
               ORDER BY event_id, observation_id
           ) AS lineage
    FROM entity_links
    GROUP BY snapshot_id, as_of, entity_id
)
SELECT entity.entity_id, entity.entity_type, entity.display_name,
       entity.tax_identifier_type, entity.tax_identifier_export,
       provenance.as_of, entity.last_seen_at AS source_updated_at,
       'COMPLETE'::TEXT AS completeness, ARRAY[]::TEXT[] AS reason_codes,
       jsonb_build_object('snapshot_id', provenance.snapshot_id, 'lineage', provenance.lineage) AS provenance
FROM entity_provenance provenance
JOIN public.canonical_public_entities_v2 entity USING (entity_id);

CREATE OR REPLACE VIEW public_read_v1.suppliers AS
SELECT * FROM public_read_v1.entities WHERE entity_type IN ('supplier', 'company');
CREATE OR REPLACE VIEW public_read_v1.organs AS
SELECT * FROM public_read_v1.entities WHERE entity_type IN ('organ', 'unit');

CREATE OR REPLACE VIEW public_read_v1.municipalities AS
SELECT DISTINCT public.canonical_public_id('mun', ARRAY[COALESCE(organ.ibge_code, ''), COALESCE(organ.uf, ''), COALESCE(organ.municipio, '')]) AS municipality_id,
       organ.ibge_code, organ.uf, organ.municipio AS name,
       snapshot.as_of, organ.updated_at AS source_updated_at,
       'COMPLETE'::TEXT AS completeness, ARRAY[]::TEXT[] AS reason_codes,
       jsonb_build_object('snapshot_id', snapshot.snapshot_id, 'organ_canonical_key', organ.canonical_key) AS provenance
FROM public_read_v1.current_snapshot snapshot
JOIN public_read_v1.organs exposed ON TRUE
JOIN public.canonical_public_entities_v2 entity ON entity.entity_id = exposed.entity_id
JOIN public.canonical_organs organ ON organ.cnpj14 = regexp_replace(entity.strong_key, '\D', '', 'g')
WHERE organ.municipio IS NOT NULL;

CREATE OR REPLACE VIEW public_read_v1.surface_health AS
SELECT health.view_name, health.enabled,
       health.refreshed_at, health.query_count, health.error_count,
       health.query_p95_ms, health.last_refresh_status,
       snapshot.snapshot_id, snapshot.as_of,
       CASE WHEN switch.enabled THEN 'KILL_SWITCH_BLOCKED'
            WHEN health.last_refresh_status = 'VALID' THEN 'COMPLETE'
            ELSE 'INCOMPLETE' END AS completeness,
       jsonb_build_object('snapshot_id', snapshot.snapshot_id, 'content_hash', snapshot.content_hash) AS provenance
FROM public.public_read_surface_health_internal health
LEFT JOIN public_read_v1.current_snapshot snapshot ON TRUE
CROSS JOIN public.truth_plane_kill_switch switch
WHERE switch.singleton;

CREATE TABLE IF NOT EXISTS public_read_v1.contract_releases (
    version                  TEXT PRIMARY KEY,
    released_at              TIMESTAMPTZ NOT NULL,
    schema_hash              TEXT NOT NULL CHECK (schema_hash ~ '^[0-9a-f]{64}$'),
    compatibility_policy     TEXT NOT NULL,
    deprecation_window_days  INTEGER NOT NULL CHECK (deprecation_window_days >= 90),
    changelog                TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS public_read_v1.query_budgets (
    query_family             TEXT PRIMARY KEY,
    statement_timeout_ms     INTEGER NOT NULL,
    p95_budget_ms            INTEGER NOT NULL,
    max_rows                 INTEGER NOT NULL,
    max_concurrent           INTEGER NOT NULL,
    representative_query     TEXT NOT NULL
);

INSERT INTO public_read_v1.query_budgets VALUES
    ('tenders_by_process', 2000, 250, 100, 4, 'SELECT * FROM public_read_v1.tenders WHERE process_key = $1 LIMIT 100'),
    ('contracts_by_process', 2000, 250, 100, 4, 'SELECT * FROM public_read_v1.contracts WHERE process_key = $1 LIMIT 100'),
    ('entities_by_id', 1000, 100, 10, 4, 'SELECT * FROM public_read_v1.entities WHERE entity_id = $1 LIMIT 10'),
    ('surface_health', 1000, 100, 20, 2, 'SELECT * FROM public_read_v1.surface_health LIMIT 20')
ON CONFLICT (query_family) DO UPDATE SET
    statement_timeout_ms = EXCLUDED.statement_timeout_ms,
    p95_budget_ms = EXCLUDED.p95_budget_ms,
    max_rows = EXCLUDED.max_rows,
    max_concurrent = EXCLUDED.max_concurrent,
    representative_query = EXCLUDED.representative_query;

DO $$
DECLARE release_hash TEXT;
BEGIN
    SELECT encode(digest(string_agg(table_name || ':' || ordinal_position || ':' || column_name || ':' || data_type || ':' || is_nullable, '|' ORDER BY table_name, ordinal_position), 'sha256'), 'hex')
    INTO release_hash
    FROM information_schema.columns
    WHERE table_schema = 'public_read_v1'
      AND table_name IN ('current_snapshot', 'tenders', 'contracts', 'entities', 'suppliers', 'organs', 'municipalities', 'surface_health');
    INSERT INTO public_read_v1.contract_releases VALUES (
        'v1.0.0', NOW(), release_hash,
        'Additive nullable columns only within v1; removal/type/nullability changes require public_read_v2.',
        180,
        'Initial canonical snapshot, tender, contract, entity, supplier, organ, municipality and health families.'
    ) ON CONFLICT (version) DO UPDATE SET schema_hash = EXCLUDED.schema_hash;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'smartlic_public_reader') THEN
        CREATE ROLE smartlic_public_reader NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION;
        COMMENT ON ROLE smartlic_public_reader IS 'managed-by-extra-migration-089';
    END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO smartlic_public_reader', current_database());
    EXECUTE format('GRANT smartlic_public_reader TO %I', current_user);
END $$;

ALTER ROLE smartlic_public_reader SET statement_timeout = '2s';
ALTER ROLE smartlic_public_reader SET lock_timeout = '500ms';
ALTER ROLE smartlic_public_reader SET idle_in_transaction_session_timeout = '5s';
ALTER ROLE smartlic_public_reader SET default_transaction_read_only = 'on';
REVOKE ALL ON SCHEMA public FROM smartlic_public_reader;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM smartlic_public_reader;
GRANT USAGE ON SCHEMA public_read_v1 TO smartlic_public_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public_read_v1 TO smartlic_public_reader;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA public_read_v1 FROM smartlic_public_reader;

COMMIT;
