# Architecture — Decision & Outcome Memory v1

## Layers

```
CLI (scripts.decision_memory)
  → models/mapping/identity/idempotency/temporal (pure)
  → repository (append-only PostgreSQL)
  → projections (human-decisions.jsonl)
  → weekly_board / metrics / import_legacy

Extra adapter: scripts.ops.extra_decision_review
  → validate → PG commit → project JSONL
  → --artifact-only → NON_CANONICAL_ARTIFACT_ONLY
```

## Source of truth

| Store | Role |
|-------|------|
| PostgreSQL `dm_*` | Canonical |
| JSONL / JSON / PDF | Projection / import input / delivery pack |
| Weekly board JSON | DB-derived section in weekly pack when DSN set |

## Client isolation

- Every write/read requires `client_id`
- Triggers block action/outcome cross-client decision refs
- Queries always filter by `client_id`
- RLS not enabled in v1 (service + constraints + adversarial tests)

## Temporal integrity

| State | Use |
|-------|-----|
| PROSPECTIVE | Decision before outcome; strong future metrics only |
| HISTORICAL_UNVERIFIED | Backfill without proven order |
| OUTCOME_WITHOUT_PRIOR_DECISION | Outcome first |
| TEMPORAL_ORDER_UNKNOWN | Mixed naive/aware timestamps etc. |

## Compatibility

- Schema version: `decision-memory/1.0`
- Future migrations additive; supersession preferred over mutation
