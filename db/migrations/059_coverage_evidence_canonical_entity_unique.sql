-- Migration 059: allow per-entity coverage_evidence rows keyed by canonical_entity_key
-- without colliding on the aggregate unique (source, data_type, run_id) WHERE entity_id IS NULL.
--
-- Historical contracts operational adapter writes:
--   entity_id = NULL
--   canonical_entity_key = extra-...
--   source ∈ {pncp, contracts}
--   same run_id across the universe
--
-- The aggregate unique must only apply to true aggregate rows (no entity, no canonical key).

BEGIN;

DROP INDEX IF EXISTS uq_ce_source_aggregate_run;

CREATE UNIQUE INDEX uq_ce_source_aggregate_run
  ON public.coverage_evidence (source, data_type, run_id)
  WHERE entity_id IS NULL AND canonical_entity_key IS NULL;

COMMENT ON INDEX uq_ce_source_aggregate_run IS
  'Aggregate run uniqueness only when both entity_id and canonical_entity_key are NULL. Nominal per-entity rows use uq_ce_canonical_entity_run.';

COMMIT;
