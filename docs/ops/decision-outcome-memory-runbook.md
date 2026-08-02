# Runbook — Decision & Outcome Memory v1

## Prerequisites

```bash
export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}"
python3 -m scripts.ops.apply_migrations --dsn "$LOCAL_DATALAKE_DSN"
```

Ensure migration `068_decision_outcome_memory.sql` is applied (creates `dm_*` tables).

## CLI (generic)

```bash
python3 -m scripts.decision_memory --client-id extra decision record \
  --opportunity-key '...' --decision GO --actor tiago --justification '...'

python3 -m scripts.decision_memory --client-id extra decision list
python3 -m scripts.decision_memory --client-id extra decision show EVENT_ID
python3 -m scripts.decision_memory --client-id extra decision history OPP_KEY

python3 -m scripts.decision_memory --client-id extra action record \
  --decision-event-id UUID --opportunity-key '...' --description '...' \
  --actor tiago --owner alice --due-at 2026-08-10T00:00:00Z

python3 -m scripts.decision_memory --client-id extra action complete EVENT_ID \
  --actor alice --evidence-hash '...'

python3 -m scripts.decision_memory --client-id extra outcome record \
  --opportunity-key '...' --outcome-type WIN --source pncp \
  --evidence-hash '...' --actor tiago

python3 -m scripts.decision_memory --client-id extra import-run \
  --path path/to/human-decisions.jsonl --actor importer          # dry-run
python3 -m scripts.decision_memory --client-id extra import-run \
  --path path/to/human-decisions.jsonl --actor importer --apply

python3 -m scripts.decision_memory --client-id extra weekly-board
python3 -m scripts.decision_memory --client-id extra metrics
python3 -m scripts.decision_memory --client-id extra integrity verify
```

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Operational failure / not ok |
| 2 | Validation / usage error |
| 3 | Database unavailable / persistence failure |

## Extra review integration

```bash
# Canonical (PG then JSONL projection) when LOCAL_DATALAKE_DSN is set
python3 -m scripts.ops.extra_decision_review --run-dir RUN decide OPP \
  --decision ACCEPT --reason '...' --actor tiago

# Explicit non-canonical local ledger only
python3 -m scripts.ops.extra_decision_review --run-dir RUN --artifact-only decide OPP \
  --decision ACCEPT --reason '...' --actor tiago
```

If PG fails, exit 3 with `PERSISTENCE_FAILED` — do **not** treat as accepted.

## Recovery

| Situation | Action |
|-----------|--------|
| PG committed, JSONL projection failed | Status `CANONICAL_PERSISTED_PROJECTION_PARTIAL`; re-run decide with same payload (idempotent) or re-project from `decision show` |
| Duplicate import | Expected; counts.duplicate increases; zero new rows |
| Wrong decision recorded | Record superseding decision with `--` correction fields / `supersedes_event_id`; never UPDATE |
| Cross-client mistake | Blocked by trigger; fix client_id and re-record |
| Orphan predictive migration 068 on local DB | If `dm_*` missing but version 068 present from PR #197, apply `068_decision_outcome_memory.sql` content and update `_migrations.name` |

## Privacy

- Always pass explicit `--client-id`.
- Do not commit real Extra private decisions/outcomes in fixtures.
- Public artifacts must not embed private payload fields.

## Non-claims

Missing outcome = UNKNOWN, not LOSS. Metrics do not prove causal influence.
