-- 088_canonical_public_events.sql
-- Persistent client-independent entities/events/observations with bitemporal revisions (#273/#289).

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE OR REPLACE FUNCTION public.canonical_public_id(p_prefix TEXT, p_parts TEXT[])
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
STRICT
SET search_path TO public, pg_temp
AS $$
    SELECT p_prefix || '_' || substr(
        encode(public.digest(array_to_string(p_parts, E'\x1f'), 'sha256'), 'hex'),
        1,
        32
    );
$$;

CREATE TABLE IF NOT EXISTS public.canonical_public_entities_v2 (
    entity_id             TEXT PRIMARY KEY,
    entity_type           TEXT NOT NULL CHECK (entity_type IN ('organ', 'unit', 'company', 'supplier', 'process')),
    strong_key            TEXT NOT NULL,
    display_name          TEXT,
    tax_identifier_type   TEXT,
    tax_identifier_export TEXT,
    state                 TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (state IN ('ACTIVE', 'MERGED', 'SPLIT', 'RETIRED')),
    canonical_successor_id TEXT REFERENCES public.canonical_public_entities_v2(entity_id),
    first_seen_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by_policy     TEXT NOT NULL,
    CHECK (strong_key !~* 'client[_-]?id'),
    CHECK (canonical_successor_id IS NULL OR canonical_successor_id <> entity_id),
    UNIQUE (entity_type, strong_key)
);

CREATE TABLE IF NOT EXISTS public.canonical_public_entity_aliases_v2 (
    alias_id              TEXT PRIMARY KEY,
    entity_id             TEXT NOT NULL REFERENCES public.canonical_public_entities_v2(entity_id),
    alias_kind            TEXT NOT NULL,
    alias_value           TEXT NOT NULL,
    source                TEXT NOT NULL,
    source_record_id      TEXT,
    confidence            NUMERIC(6,5) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    valid_from            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to              TIMESTAMPTZ,
    policy_version        TEXT NOT NULL,
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    UNIQUE (entity_id, alias_kind, alias_value, source, valid_from)
);

CREATE INDEX IF NOT EXISTS idx_canonical_alias_lookup_v2
    ON public.canonical_public_entity_aliases_v2 (alias_kind, alias_value, valid_from DESC)
    WHERE valid_to IS NULL;

CREATE TABLE IF NOT EXISTS public.canonical_public_events_v1 (
    event_id              TEXT PRIMARY KEY,
    event_type            TEXT NOT NULL CHECK (event_type IN (
        'tender_publication', 'tender_status', 'tender_document_change', 'contract_lifecycle'
    )),
    process_key           TEXT NOT NULL,
    subject_entity_id     TEXT NOT NULL REFERENCES public.canonical_public_entities_v2(entity_id),
    official_number       TEXT,
    state                 TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (state IN ('ACTIVE', 'MERGED', 'SPLIT', 'RETIRED')),
    canonical_successor_id TEXT REFERENCES public.canonical_public_events_v1(event_id),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by_policy     TEXT NOT NULL,
    CHECK (process_key !~* 'client[_-]?id'),
    CHECK (canonical_successor_id IS NULL OR canonical_successor_id <> event_id),
    UNIQUE (event_type, process_key)
);

CREATE INDEX IF NOT EXISTS idx_canonical_events_subject_v1
    ON public.canonical_public_events_v1 (subject_entity_id, event_type, process_key);
CREATE INDEX IF NOT EXISTS idx_canonical_events_process_v1
    ON public.canonical_public_events_v1 (process_key, event_type);

CREATE TABLE IF NOT EXISTS public.canonical_public_observations (
    observation_id        TEXT PRIMARY KEY,
    source                TEXT NOT NULL,
    source_record_id      TEXT NOT NULL,
    source_version        TEXT NOT NULL,
    document_version      TEXT,
    raw_sha256            TEXT NOT NULL CHECK (raw_sha256 ~ '^[0-9a-f]{64}$'),
    observed_at           TIMESTAMPTZ NOT NULL,
    received_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_uri            TEXT,
    snapshot_id           TEXT,
    payload_hash          TEXT NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
    payload               JSONB NOT NULL,
    CHECK (NOT (payload ? 'client_id')),
    UNIQUE (source, source_record_id, source_version, raw_sha256)
);

CREATE INDEX IF NOT EXISTS idx_canonical_observations_source
    ON public.canonical_public_observations (source, observed_at DESC, observation_id);
CREATE INDEX IF NOT EXISTS idx_canonical_observations_snapshot
    ON public.canonical_public_observations (snapshot_id, observation_id)
    WHERE snapshot_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.canonical_event_observation_links (
    event_id              TEXT NOT NULL REFERENCES public.canonical_public_events_v1(event_id),
    observation_id        TEXT NOT NULL REFERENCES public.canonical_public_observations(observation_id),
    link_role             TEXT NOT NULL CHECK (link_role IN ('asserts', 'corrects', 'documents', 'status_of')),
    confidence            NUMERIC(6,5) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    match_policy_version  TEXT NOT NULL,
    linked_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (event_id, observation_id, link_role)
);

CREATE INDEX IF NOT EXISTS idx_canonical_event_obs_by_observation
    ON public.canonical_event_observation_links (observation_id, event_id);

CREATE TABLE IF NOT EXISTS public.canonical_event_entity_links (
    event_id              TEXT NOT NULL REFERENCES public.canonical_public_events_v1(event_id),
    entity_id             TEXT NOT NULL REFERENCES public.canonical_public_entities_v2(entity_id),
    relation_type         TEXT NOT NULL CHECK (relation_type IN ('subject_process', 'buyer', 'supplier', 'publisher')),
    observation_id        TEXT NOT NULL REFERENCES public.canonical_public_observations(observation_id),
    confidence            NUMERIC(6,5) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    policy_version        TEXT NOT NULL,
    PRIMARY KEY (event_id, entity_id, relation_type, observation_id)
);

CREATE INDEX IF NOT EXISTS idx_canonical_event_entity_by_entity
    ON public.canonical_event_entity_links (entity_id, event_id, relation_type);

CREATE TABLE IF NOT EXISTS public.canonical_event_revisions (
    revision_id           TEXT PRIMARY KEY,
    event_id              TEXT NOT NULL REFERENCES public.canonical_public_events_v1(event_id),
    valid_from            TIMESTAMPTZ NOT NULL,
    valid_to              TIMESTAMPTZ,
    system_from           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    system_to             TIMESTAMPTZ,
    status_code           TEXT,
    title                 TEXT,
    publication_at        TIMESTAMPTZ,
    document_sha256       TEXT,
    contract_value        NUMERIC(18,2),
    official_number       TEXT,
    fact_hash             TEXT NOT NULL CHECK (fact_hash ~ '^[0-9a-f]{64}$'),
    fact_payload          JSONB NOT NULL,
    created_from_observation_id TEXT NOT NULL REFERENCES public.canonical_public_observations(observation_id),
    policy_version        TEXT NOT NULL,
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    CHECK (system_to IS NULL OR system_to > system_from),
    UNIQUE (event_id, valid_from, fact_hash)
);

CREATE INDEX IF NOT EXISTS idx_canonical_revision_asof
    ON public.canonical_event_revisions (event_id, valid_from DESC, system_from DESC);
CREATE INDEX IF NOT EXISTS idx_canonical_revision_fact
    ON public.canonical_event_revisions (fact_hash, event_id);

CREATE TABLE IF NOT EXISTS public.canonical_match_conflicts (
    conflict_id           TEXT PRIMARY KEY,
    observation_id        TEXT NOT NULL REFERENCES public.canonical_public_observations(observation_id),
    conflict_type         TEXT NOT NULL,
    candidate_event_ids   TEXT[] NOT NULL,
    reason_codes          TEXT[] NOT NULL,
    policy_version        TEXT NOT NULL,
    status                TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'RESOLVED', 'REJECTED', 'DEFERRED')),
    owner                 TEXT,
    next_action           TEXT NOT NULL DEFAULT 'human_identity_review',
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at           TIMESTAMPTZ,
    resolution            JSONB,
    CHECK (cardinality(candidate_event_ids) >= 2)
);

CREATE INDEX IF NOT EXISTS idx_canonical_conflicts_open
    ON public.canonical_match_conflicts (status, conflict_type, created_at, conflict_id)
    WHERE status = 'OPEN';

CREATE TABLE IF NOT EXISTS public.canonical_identity_decisions (
    decision_id           TEXT PRIMARY KEY,
    action                TEXT NOT NULL CHECK (action IN ('MERGE', 'SPLIT')),
    source_entity_id      TEXT NOT NULL REFERENCES public.canonical_public_entities_v2(entity_id),
    target_entity_id      TEXT NOT NULL REFERENCES public.canonical_public_entities_v2(entity_id),
    alias_values          TEXT[] NOT NULL DEFAULT '{}',
    reason                TEXT NOT NULL,
    evidence_observation_ids TEXT[] NOT NULL,
    policy_version        TEXT NOT NULL,
    decided_by            TEXT NOT NULL,
    decided_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (source_entity_id <> target_entity_id),
    CHECK (cardinality(evidence_observation_ids) > 0)
);

CREATE INDEX IF NOT EXISTS idx_canonical_decisions_entities
    ON public.canonical_identity_decisions (source_entity_id, target_entity_id, decided_at);

CREATE OR REPLACE FUNCTION public.ensure_canonical_public_entity_v2(
    p_entity_type TEXT,
    p_strong_key TEXT,
    p_display_name TEXT,
    p_tax_identifier_type TEXT,
    p_tax_identifier_export TEXT,
    p_source TEXT,
    p_source_record_id TEXT,
    p_policy_version TEXT
)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    result_id TEXT;
    result_alias_id TEXT;
BEGIN
    IF p_strong_key IS NULL OR btrim(p_strong_key) = '' OR p_strong_key ~* 'client[_-]?id' THEN
        RAISE EXCEPTION 'strong client-independent entity key is required' USING ERRCODE = '22023';
    END IF;
    result_id := public.canonical_public_id('ent', ARRAY[p_entity_type, p_strong_key]);
    INSERT INTO public.canonical_public_entities_v2 (
        entity_id, entity_type, strong_key, display_name,
        tax_identifier_type, tax_identifier_export, created_by_policy
    ) VALUES (
        result_id, p_entity_type, p_strong_key, p_display_name,
        p_tax_identifier_type, p_tax_identifier_export, p_policy_version
    ) ON CONFLICT (entity_id) DO UPDATE
      SET last_seen_at = NOW(),
          display_name = COALESCE(canonical_public_entities_v2.display_name, EXCLUDED.display_name);

    result_alias_id := public.canonical_public_id(
        'als', ARRAY[result_id, 'strong_key', p_strong_key, p_source]
    );
    INSERT INTO public.canonical_public_entity_aliases_v2 (
        alias_id, entity_id, alias_kind, alias_value, source,
        source_record_id, confidence, policy_version
    ) VALUES (
        result_alias_id, result_id, 'strong_key', p_strong_key, p_source,
        p_source_record_id, 1, p_policy_version
    ) ON CONFLICT (alias_id) DO NOTHING;
    RETURN result_id;
END;
$$;

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

CREATE OR REPLACE FUNCTION public.canonical_event_revision_as_of_v1(
    p_event_id TEXT,
    p_valid_at TIMESTAMPTZ,
    p_system_at TIMESTAMPTZ DEFAULT NOW()
)
RETURNS SETOF public.canonical_event_revisions
LANGUAGE sql
STABLE
AS $$
    SELECT revision.*
    FROM public.canonical_event_revisions revision
    WHERE revision.event_id = p_event_id
      AND revision.valid_from <= p_valid_at
      AND (revision.valid_to IS NULL OR revision.valid_to > p_valid_at)
      AND revision.system_from <= p_system_at
      AND (revision.system_to IS NULL OR revision.system_to > p_system_at)
    ORDER BY revision.valid_from DESC, revision.system_from DESC, revision.revision_id DESC
    LIMIT 1;
$$;

CREATE OR REPLACE FUNCTION public.record_canonical_identity_decision_v1(
    p_action TEXT,
    p_source_entity_id TEXT,
    p_target_entity_id TEXT,
    p_alias_values TEXT[],
    p_reason TEXT,
    p_evidence_observation_ids TEXT[],
    p_policy_version TEXT,
    p_decided_by TEXT
)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    result_id TEXT;
    alias_row RECORD;
    split_at TIMESTAMPTZ;
BEGIN
    IF upper(p_action) NOT IN ('MERGE', 'SPLIT') THEN
        RAISE EXCEPTION 'identity action must be MERGE or SPLIT' USING ERRCODE = '22023';
    END IF;
    result_id := public.canonical_public_id(
        'dec', ARRAY[upper(p_action), p_source_entity_id, p_target_entity_id, p_policy_version, p_reason]
    );
    INSERT INTO public.canonical_identity_decisions (
        decision_id, action, source_entity_id, target_entity_id, alias_values,
        reason, evidence_observation_ids, policy_version, decided_by
    ) VALUES (
        result_id, upper(p_action), p_source_entity_id, p_target_entity_id,
        COALESCE(p_alias_values, '{}'), p_reason, p_evidence_observation_ids,
        p_policy_version, p_decided_by
    ) ON CONFLICT (decision_id) DO NOTHING;

    IF upper(p_action) = 'MERGE' THEN
        UPDATE public.canonical_public_entities_v2
        SET state = 'MERGED', canonical_successor_id = p_target_entity_id
        WHERE entity_id = p_source_entity_id AND state = 'ACTIVE';
        FOR alias_row IN
            SELECT * FROM public.canonical_public_entity_aliases_v2
            WHERE entity_id = p_source_entity_id AND valid_to IS NULL
        LOOP
            INSERT INTO public.canonical_public_entity_aliases_v2 (
                alias_id, entity_id, alias_kind, alias_value, source,
                source_record_id, confidence, valid_from, policy_version
            ) VALUES (
                public.canonical_public_id('als', ARRAY[p_target_entity_id, alias_row.alias_kind, alias_row.alias_value, alias_row.source]),
                p_target_entity_id, alias_row.alias_kind, alias_row.alias_value,
                alias_row.source, alias_row.source_record_id, alias_row.confidence,
                NOW(), p_policy_version
            ) ON CONFLICT (alias_id) DO NOTHING;
        END LOOP;
    ELSE
        split_at := clock_timestamp();
        FOR alias_row IN
            SELECT alias_id, alias_kind, alias_value, source, source_record_id, confidence
            FROM public.canonical_public_entity_aliases_v2
            WHERE entity_id = p_source_entity_id
              AND valid_to IS NULL
              AND alias_value = ANY(COALESCE(p_alias_values, '{}'))
            ORDER BY alias_id
        LOOP
            UPDATE public.canonical_public_entity_aliases_v2
            SET valid_to = split_at
            WHERE alias_id = alias_row.alias_id AND valid_to IS NULL;
            INSERT INTO public.canonical_public_entity_aliases_v2 (
                alias_id, entity_id, alias_kind, alias_value, source,
                source_record_id, confidence, valid_from, policy_version
            ) VALUES (
                public.canonical_public_id('als', ARRAY[
                    p_target_entity_id, alias_row.alias_id, result_id, split_at::TEXT
                ]),
                p_target_entity_id, alias_row.alias_kind, alias_row.alias_value,
                alias_row.source, alias_row.source_record_id, alias_row.confidence,
                split_at, p_policy_version
            ) ON CONFLICT (alias_id) DO NOTHING;
        END LOOP;
        UPDATE public.canonical_public_entities_v2 SET state = 'SPLIT'
        WHERE entity_id = p_source_entity_id AND state = 'ACTIVE';
    END IF;
    RETURN result_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.guard_canonical_immutable_v1()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF current_setting('app.allow_canonical_test_cleanup', TRUE) = 'on'
       AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = current_user AND rolsuper) THEN
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END IF;
    RAISE EXCEPTION '% rows are immutable; append a revision/decision instead', TG_TABLE_NAME
        USING ERRCODE = '55000';
END;
$$;

DROP TRIGGER IF EXISTS trg_canonical_observations_immutable ON public.canonical_public_observations;
CREATE TRIGGER trg_canonical_observations_immutable
    BEFORE UPDATE OR DELETE ON public.canonical_public_observations
    FOR EACH ROW EXECUTE FUNCTION public.guard_canonical_immutable_v1();

DROP TRIGGER IF EXISTS trg_canonical_revisions_immutable ON public.canonical_event_revisions;
CREATE TRIGGER trg_canonical_revisions_immutable
    BEFORE UPDATE OR DELETE ON public.canonical_event_revisions
    FOR EACH ROW EXECUTE FUNCTION public.guard_canonical_immutable_v1();

DROP TRIGGER IF EXISTS trg_canonical_decisions_immutable ON public.canonical_identity_decisions;
CREATE TRIGGER trg_canonical_decisions_immutable
    BEFORE UPDATE OR DELETE ON public.canonical_identity_decisions
    FOR EACH ROW EXECUTE FUNCTION public.guard_canonical_immutable_v1();

COMMIT;
