# CONFENGE contact discovery terminal outcomes

Date: 2026-08-25
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

## Exact official-registry trust boundary

`company_registry` is a projection label, not proof by itself. It is promoted
to the trusted `REAL_REGISTRY` root only when the route carries a `MATCHED`
Receita Federal observation for the same canonical CNPJ, an identical official
release ID in the contact and source-provenance blocks, a source reference, an
observation timestamp and the explicit company-association verdict. A copied
label, a cross-CNPJ route or an incomplete tuple remains provenance-invalid and
cannot become controlled-eligible or preferred during reranking.

The next full production cohort completed on 2026-08-25 with all 8,637 accounts
terminal: 8,625 `SUCCEEDED`, 12 `DLQ`, 6,666 `EMAIL_ROUTE_READY` and 1,971
`BLOCKED_WITH_REASON`; the terminal equation held with zero integrity failures.
Its projection hash is
`73b2d40f9995ea0b8afc253a92e276eb719850701aacf7cb2e7eca7bda2c066e`.
