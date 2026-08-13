-- 090_public_read_select_only_lock.sql
-- Incremental contract lock for databases that already applied 087–089.
-- Fresh installs already contain these objects in the patched 087–089 files.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

UPDATE public.dlq_entries
SET terminal_at = COALESCE(failed_at, terminal_at)
WHERE failed_at IS NOT NULL
  AND (terminal_at IS NULL OR terminal_at > failed_at);

CREATE OR REPLACE FUNCTION public.ingest_canonical_public_observation_v1(p_observation JSONB)
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
    source_name TEXT := p_observation->>'source';
    source_record TEXT := p_observation->>'source_record_id';
    source_version TEXT := COALESCE(NULLIF(p_observation->>'source_version', ''), 'v1');
    raw_hash TEXT := p_observation->>'raw_sha256';
    process_key_value TEXT := p_observation->>'process_key';
    event_type_value TEXT := p_observation->>'event_type';
    policy TEXT := COALESCE(NULLIF(p_observation->>'policy_version', ''), 'canonical-events-v1');
    facts JSONB := COALESCE(p_observation->'facts', '{}'::JSONB);
    match_state TEXT := upper(COALESCE(NULLIF(btrim(p_observation->>'match_state'), ''), 'EXACT'));
    observation_id_value TEXT;
    process_entity_id TEXT;
    event_id_value TEXT;
    revision_id_value TEXT;
    fact_hash_value TEXT;
    conflict_id_value TEXT;
    related JSONB;
    related_entity_id TEXT;
    relation_name TEXT;
BEGIN
    IF p_observation ? 'client_id' OR p_observation::TEXT ~* '"client[_-]?id"' THEN
        RAISE EXCEPTION 'client_id is forbidden in canonical public authority' USING ERRCODE = '22023';
    END IF;
    IF source_name IS NULL OR source_record IS NULL OR raw_hash !~ '^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'source, source_record_id and lowercase raw_sha256 are required' USING ERRCODE = '22023';
    END IF;
    IF event_type_value IS NULL
       OR event_type_value NOT IN ('tender_publication', 'tender_status', 'tender_document_change', 'contract_lifecycle') THEN
        RAISE EXCEPTION 'unsupported event_type %', event_type_value USING ERRCODE = '22023';
    END IF;
    IF match_state NOT IN ('EXACT', 'AMBIGUOUS') THEN
        RAISE EXCEPTION 'match_state % is not an identity authority (expected EXACT or AMBIGUOUS)', match_state
            USING ERRCODE = '22023';
    END IF;

    observation_id_value := public.canonical_public_id(
        'obs', ARRAY[source_name, source_record, source_version, raw_hash]
    );
    INSERT INTO public.canonical_public_observations (
        observation_id, source, source_record_id, source_version,
        document_version, raw_sha256, observed_at, source_uri,
        snapshot_id, payload_hash, payload
    ) VALUES (
        observation_id_value, source_name, source_record, source_version,
        p_observation->>'document_version', raw_hash,
        (p_observation->>'observed_at')::TIMESTAMPTZ,
        p_observation->>'source_uri', p_observation->>'snapshot_id',
        encode(digest(p_observation::TEXT, 'sha256'), 'hex'), p_observation
    ) ON CONFLICT (observation_id) DO NOTHING;

    IF match_state = 'AMBIGUOUS' THEN
        conflict_id_value := public.canonical_public_id(
            'cnf', ARRAY[observation_id_value, COALESCE(p_observation->'candidate_event_ids', '[]')::TEXT, policy]
        );
        INSERT INTO public.canonical_match_conflicts (
            conflict_id, observation_id, conflict_type, candidate_event_ids,
            reason_codes, policy_version, owner
        ) VALUES (
            conflict_id_value, observation_id_value,
            COALESCE(p_observation->>'conflict_type', 'ambiguous_event_match'),
            ARRAY(SELECT jsonb_array_elements_text(p_observation->'candidate_event_ids')),
            ARRAY(SELECT jsonb_array_elements_text(COALESCE(p_observation->'reason_codes', '["weak_key_collision"]'))),
            policy, p_observation->>'owner'
        ) ON CONFLICT (conflict_id) DO NOTHING;
        RETURN jsonb_build_object(
            'state', 'CONFLICT', 'observation_id', observation_id_value,
            'event_id', NULL, 'conflict_id', conflict_id_value
        );
    END IF;

    IF process_key_value IS NULL OR btrim(process_key_value) = '' OR process_key_value ~* 'client[_-]?id' THEN
        RAISE EXCEPTION 'strong client-independent process_key is required' USING ERRCODE = '22023';
    END IF;
    process_entity_id := public.ensure_canonical_public_entity_v2(
        'process', process_key_value, facts->>'title', NULL, NULL,
        source_name, source_record, policy
    );
    event_id_value := public.canonical_public_id('evt', ARRAY[event_type_value, process_key_value]);
    INSERT INTO public.canonical_public_events_v1 (
        event_id, event_type, process_key, subject_entity_id,
        official_number, created_by_policy
    ) VALUES (
        event_id_value, event_type_value, process_key_value, process_entity_id,
        facts->>'official_number', policy
    ) ON CONFLICT (event_id) DO NOTHING;

    INSERT INTO public.canonical_event_observation_links (
        event_id, observation_id, link_role, confidence, match_policy_version
    ) VALUES (
        event_id_value, observation_id_value,
        COALESCE(p_observation->>'link_role', 'asserts'),
        COALESCE((p_observation->>'confidence')::NUMERIC, 1), policy
    ) ON CONFLICT DO NOTHING;

    INSERT INTO public.canonical_event_entity_links (
        event_id, entity_id, relation_type, observation_id, confidence, policy_version
    ) VALUES (event_id_value, process_entity_id, 'subject_process', observation_id_value, 1, policy)
    ON CONFLICT DO NOTHING;

    FOR related IN SELECT value FROM jsonb_array_elements(COALESCE(p_observation->'entities', '[]'::JSONB)) LOOP
        relation_name := related->>'relation_type';
        related_entity_id := public.ensure_canonical_public_entity_v2(
            related->>'entity_type', related->>'strong_key', related->>'display_name',
            related->>'tax_identifier_type', related->>'tax_identifier_export',
            source_name, source_record, policy
        );
        INSERT INTO public.canonical_event_entity_links (
            event_id, entity_id, relation_type, observation_id, confidence, policy_version
        ) VALUES (
            event_id_value, related_entity_id, relation_name, observation_id_value,
            COALESCE((related->>'confidence')::NUMERIC, 1), policy
        ) ON CONFLICT DO NOTHING;
    END LOOP;

    fact_hash_value := encode(digest(facts::TEXT, 'sha256'), 'hex');
    revision_id_value := public.canonical_public_id(
        'rev', ARRAY[event_id_value, p_observation->>'valid_from', fact_hash_value]
    );
    INSERT INTO public.canonical_event_revisions (
        revision_id, event_id, valid_from, valid_to, status_code, title,
        publication_at, document_sha256, contract_value, official_number,
        fact_hash, fact_payload, created_from_observation_id, policy_version
    ) VALUES (
        revision_id_value, event_id_value,
        (p_observation->>'valid_from')::TIMESTAMPTZ,
        NULLIF(p_observation->>'valid_to', '')::TIMESTAMPTZ,
        facts->>'status_code', facts->>'title',
        NULLIF(facts->>'publication_at', '')::TIMESTAMPTZ,
        facts->>'document_sha256', NULLIF(facts->>'contract_value', '')::NUMERIC,
        facts->>'official_number', fact_hash_value, facts,
        observation_id_value, policy
    ) ON CONFLICT (revision_id) DO NOTHING;

    RETURN jsonb_build_object(
        'state', 'LINKED', 'observation_id', observation_id_value,
        'event_id', event_id_value, 'revision_id', revision_id_value,
        'process_entity_id', process_entity_id, 'fact_hash', fact_hash_value
    );
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
    WHERE enabled
      AND view_name IN ('snapshots', 'tenders', 'contracts', 'entities', 'suppliers', 'organs');
    UPDATE public.public_read_surface_health_internal
    SET refreshed_at = NOW(), last_refresh_status = 'STALE',
        last_error = 'municipalities reserved until snapshot-bound municipality facts exist',
        updated_at = NOW()
    WHERE enabled AND view_name = 'municipalities';
    PERFORM set_config('app.canonical_snapshot_transition', 'off', TRUE);
    RETURN jsonb_build_object('snapshot_id', p_snapshot_id, 'state', 'READY_CANONICAL', 'content_hash', result_hash, 'blockers', '[]'::JSONB);
END;
$$;

CREATE OR REPLACE VIEW public_read_v1.current_snapshot AS
SELECT snapshot.snapshot_id, snapshot.cutoff_at AS as_of, snapshot.content_hash,
       snapshot.universe_hash, snapshot.policy_hash, snapshot.schema_hash,
       snapshot.adapter_hash, snapshot.data_hash, snapshot.document_hash,
       snapshot.dossier_hash, snapshot.closed_at,
       CASE
           WHEN EXISTS (
               SELECT 1 FROM public.canonical_snapshot_source_watermarks watermark
               WHERE watermark.snapshot_id = snapshot.snapshot_id
                 AND (watermark.completeness_state <> 'COMPLETE' OR watermark.freshness_state <> 'FRESH')
           ) THEN 'INCOMPLETE'
           WHEN NOT EXISTS (
               SELECT 1 FROM public.canonical_snapshot_source_watermarks watermark
               WHERE watermark.snapshot_id = snapshot.snapshot_id
           ) THEN 'UNKNOWN'
           ELSE 'COMPLETE'
       END AS completeness,
       jsonb_build_object('snapshot_id', snapshot.snapshot_id, 'content_hash', snapshot.content_hash) AS provenance
FROM public.canonical_public_snapshots snapshot
WHERE snapshot.state = 'READY_CANONICAL'
ORDER BY snapshot.cutoff_at DESC, snapshot.snapshot_id DESC
LIMIT 1;

CREATE OR REPLACE VIEW public_read_v1.tenders AS
SELECT event.event_id, event.process_key, event.event_type, revision.status_code,
       revision.title, revision.publication_at, revision.official_number,
       snapshot.as_of, revision.system_from AS source_updated_at,
       snapshot.completeness,
       CASE WHEN snapshot.completeness = 'COMPLETE' THEN ARRAY[]::TEXT[]
            WHEN snapshot.completeness = 'UNKNOWN' THEN ARRAY['missing_source_watermarks']
            ELSE ARRAY['source_watermark_incomplete'] END AS reason_codes,
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
       snapshot.completeness,
       CASE WHEN snapshot.completeness = 'COMPLETE' THEN ARRAY[]::TEXT[]
            WHEN snapshot.completeness = 'UNKNOWN' THEN ARRAY['missing_source_watermarks']
            ELSE ARRAY['source_watermark_incomplete'] END AS reason_codes,
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
       snapshot.completeness,
       CASE WHEN snapshot.completeness = 'COMPLETE' THEN ARRAY[]::TEXT[]
            WHEN snapshot.completeness = 'UNKNOWN' THEN ARRAY['missing_source_watermarks']
            ELSE ARRAY['source_watermark_incomplete'] END AS reason_codes,
       jsonb_build_object('snapshot_id', provenance.snapshot_id, 'lineage', provenance.lineage) AS provenance
FROM entity_provenance provenance
JOIN public.canonical_public_entities_v2 entity USING (entity_id)
JOIN public_read_v1.current_snapshot snapshot ON snapshot.snapshot_id = provenance.snapshot_id;

CREATE OR REPLACE VIEW public_read_v1.suppliers AS
SELECT * FROM public_read_v1.entities WHERE entity_type IN ('supplier', 'company');
CREATE OR REPLACE VIEW public_read_v1.organs AS
SELECT * FROM public_read_v1.entities WHERE entity_type IN ('organ', 'unit');

CREATE OR REPLACE VIEW public_read_v1.municipalities AS
SELECT
    NULL::TEXT AS municipality_id,
    NULL::TEXT AS ibge_code,
    NULL::TEXT AS uf,
    NULL::TEXT AS name,
    snapshot.as_of,
    snapshot.as_of AS source_updated_at,
    'UNKNOWN'::TEXT AS completeness,
    ARRAY['municipality_facts_not_snapshot_bound']::TEXT[] AS reason_codes,
    jsonb_build_object('snapshot_id', snapshot.snapshot_id) AS provenance
FROM public_read_v1.current_snapshot snapshot
WHERE FALSE;

GRANT SELECT ON ALL TABLES IN SCHEMA public_read_v1 TO smartlic_public_reader;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA public_read_v1 FROM smartlic_public_reader;

DO $$
DECLARE
    writer REGPROCEDURE;
BEGIN
    FOREACH writer IN ARRAY ARRAY[
        'public.upsert_pncp_raw_bids(JSONB)'::REGPROCEDURE,
        'public.ensure_canonical_public_entity_v2(TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT)'::REGPROCEDURE,
        'public.ingest_canonical_public_observation_v1(JSONB)'::REGPROCEDURE,
        'public.record_canonical_identity_decision_v1(TEXT, TEXT, TEXT, TEXT[], TEXT, TEXT[], TEXT, TEXT)'::REGPROCEDURE,
        'public.begin_canonical_public_snapshot_v1(TIMESTAMPTZ, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, INTEGER, INTEGER, TEXT)'::REGPROCEDURE,
        'public.put_canonical_snapshot_watermark_v1(TEXT, TEXT, TEXT, TIMESTAMPTZ, TEXT, TEXT, INTEGER, INTEGER, TEXT)'::REGPROCEDURE,
        'public.close_canonical_public_snapshot_v1(TEXT)'::REGPROCEDURE,
        'public.invalidate_consumer_projection_private_v1(TEXT, TEXT, TEXT)'::REGPROCEDURE
    ]
    LOOP
        EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC', writer);
        EXECUTE format('REVOKE ALL ON FUNCTION %s FROM smartlic_public_reader', writer);
    END LOOP;
END $$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM smartlic_public_reader;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM smartlic_public_reader;
REVOKE USAGE ON SCHEMA public FROM smartlic_public_reader;

COMMIT;
