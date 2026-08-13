BEGIN;

DROP FUNCTION IF EXISTS public.record_canonical_identity_decision_v1(TEXT, TEXT, TEXT, TEXT[], TEXT, TEXT[], TEXT, TEXT);
DROP FUNCTION IF EXISTS public.canonical_event_revision_as_of_v1(TEXT, TIMESTAMPTZ, TIMESTAMPTZ);
DROP FUNCTION IF EXISTS public.ingest_canonical_public_observation_v1(JSONB);
DROP FUNCTION IF EXISTS public.ensure_canonical_public_entity_v2(TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT);
DROP TABLE IF EXISTS public.canonical_identity_decisions;
DROP TABLE IF EXISTS public.canonical_match_conflicts;
DROP TABLE IF EXISTS public.canonical_event_revisions;
DROP TABLE IF EXISTS public.canonical_event_entity_links;
DROP TABLE IF EXISTS public.canonical_event_observation_links;
DROP TABLE IF EXISTS public.canonical_public_observations;
DROP TABLE IF EXISTS public.canonical_public_events_v1;
DROP TABLE IF EXISTS public.canonical_public_entity_aliases_v2;
DROP TABLE IF EXISTS public.canonical_public_entities_v2;
DROP FUNCTION IF EXISTS public.guard_canonical_immutable_v1();
DROP FUNCTION IF EXISTS public.canonical_public_id(TEXT, TEXT[]);

COMMIT;
