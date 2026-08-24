# CONFENGE contact discovery terminal outcomes

Date: 2026-08-24  
Owner: `extra-cli`  
Scope: durable contact discovery projection for `TARGET_CONFIRMED`

## Contract

Every account in the immutable cohort denominator must be projected exactly
once as one of:

- `EMAIL_ROUTE_READY`
- `NO_PUBLIC_EMAIL_FOUND`
- `BLOCKED_WITH_REASON`

`SUCCEEDED` jobs require a verified output pointer, matching canonical payload
hash, account and job identity, plus an explicit enrichment terminal. Any
integrity failure remains fail-closed and prevents publication.

`BLOCKED`, `DLQ` and `CANCELLED` jobs are themselves durable terminal evidence.
They are projected as `BLOCKED_WITH_REASON` from the job's reason code, even if
an earlier attempt left a valid but partial output file. A contact artifact is
not required to prove that a provider failure is a blocker.

Publication is allowed only when the population count, job denominator,
terminal projection count and distinct terminal account count are equal, with
zero integrity failures.

## Production reproduction that closed the gap

The full 2026-08-24 cohort reached 8,614 terminal jobs: 8,606 `SUCCEEDED` and 8
`DLQ`. Before this repair, the exporter correctly refused promotion but reported
`OUTPUT_ENRICHMENT_TERMINAL_MISSING=8`, because the eight DLQ rows retained
partial outputs from earlier attempts. The regression test reproduces that
exact state and proves a complete blocker projection without weakening output
integrity for successful jobs.

Runtime deployment, rerun identifiers and consumer reconciliation evidence are
recorded on `extra-cli#469`; this handoff defines the durable code contract only.
