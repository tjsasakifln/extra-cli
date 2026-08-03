# Data model — dm_*

## Tables

### dm_decision_events
Immutable decision events. Unique `(client_id, idempotency_key)`.
Maps legacy ACCEPT/DEFER/REJECT → GO/REVIEW/NO_GO while preserving `legacy_decision`.

### dm_action_events
Actions linked to a decision of the **same** `client_id`.
Owner/due absence must be explicit (`owner_absent_reason` / `due_absent_reason`).
Completion via superseding COMPLETED event (append-only).

### dm_outcome_events
Observable outcomes with evidence_hash required. Missing outcome is not stored as LOSS.
`outcome_type` vocabulary versioned (WIN, LOSS, PROPOSAL_SUBMITTED, UNKNOWN, …).

### dm_identity_conflicts
Blocked ambiguous identity resolutions for human review.

### dm_import_runs
Audit of dry-run/apply import manifests and counts.

## Views

- `dm_decision_current` / `dm_action_current` / `dm_outcome_current` — latest non-superseded events.

## Migration

`db/migrations/068_decision_outcome_memory.sql`
