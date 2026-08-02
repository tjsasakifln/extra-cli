# ADR: Decision & Outcome Memory v1

- **Status:** Accepted
- **Date:** 2026-08-02
- **Campaign:** EXTRA-DECISION-OUTCOME-MEMORY-01
- **Baseline:** `origin/main` @ `704975a7bcdd43d4dc6769fbf6c14726327ab37b`

## Context

Weekly decision packages were independent run-local artifacts (`human-decisions.jsonl`
per `run_dir`). They did not form a client-scoped, cross-cycle operational memory
linking decision → action → outcome → learning.

## Decision

1. **PostgreSQL is authoritative** for decisions, actions, and outcomes
   (`dm_decision_events`, `dm_action_events`, `dm_outcome_events`).
2. **Append-only events** with supersession for corrections; UPDATE/DELETE blocked
   by triggers.
3. **Generic module** `scripts/decision_memory/` requires explicit `client_id`
   (no silent `extra` default in the core).
4. **Extra adapter** in `scripts.ops.extra_decision_review` maps legacy
   ACCEPT/DEFER/REJECT → GO/REVIEW/NO_GO and persists canonically when a DSN is
   configured; `--artifact-only` yields `NON_CANONICAL_ARTIFACT_ONLY`.
5. **JSON/JSONL/PDF** are projections or import inputs, never sole source of truth
   after persistence is enabled.
6. **Temporal integrity** is explicit (`PROSPECTIVE`, `HISTORICAL_UNVERIFIED`,
   `OUTCOME_WITHOUT_PRIOR_DECISION`, `TEMPORAL_ORDER_UNKNOWN`). Backfills are not
   falsified as prospective.
7. **Metrics** expose numerator/denominator/unknowns/limitations and never auto-compute
   causal “decision influence” or loss avoided.
8. **Migration number** chosen dynamically from `origin/main` filesystem max (`067`)
   → `068_decision_outcome_memory.sql`. Local DB may have carried an unmerged
   predictive `068` from PR #197; evidence documents reconciliation.

## Consequences

- Human review path can fail-closed if PG write fails (no silent JSONL PASS).
- Cross-client isolation enforced by constraints, service filters, and triggers.
- Weekly board section is DB-derived when DSN is available.
- RLS was **not** enabled in v1 (service-layer + constraints + tests); avoids false
  security theater if app role is superuser-like.

## Non-claims

- Does not prove CONFENGE caused wins.
- Does not predict outcomes.
- Does not invent margins or human acceptances.
- Historical imports are not prospective.

## References

- `db/migrations/068_decision_outcome_memory.sql`
- `scripts/decision_memory/`
- `artifacts/campaigns/EXTRA-DECISION-OUTCOME-MEMORY-01/`
