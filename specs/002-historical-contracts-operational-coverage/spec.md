# Feature Specification: Historical Contracts Operational Coverage

**Feature Branch**: `campaign/historical-contracts-operational-closure-01`  
**Spec dir**: `specs/002-historical-contracts-operational-coverage`  
**Created**: 2026-07-22  
**Status**: Active  
**Campaign**: `HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01`  
**Depends on**: `specs/001-dual-capability-coverage-truth/` (measurement spine — do not reopen without demonstrated failure)

## Input

Turn `historical_contracts` from correctly measured but operationally empty into a proven local consulting capability: full source applicability, ≥3y backfill, ≤7d incremental, entity `coverage_evidence`, dual gate ≥95%, weekly integration, idempotency/recovery proofs.

## Non-goals

- Replacing ADR-030 / dual measurement method
- open_tenders 95% closure
- VPS / LOCAL_READY / PROJECT_DONE claims
- Value-paid semantics, physical works tracking

## User Stories

### US1 — Applicability 100% (P0)

As an auditor, every included universe entity has a resolved applicability decision for `historical_contracts` (no silent unknown, no not_applicable to dodge collection).

**Acceptance**

1. Given the canonical seed (1093 included), when dual measurement runs, then `applicability_unknown_count=0` for historical_contracts.
2. Given multi-sphere natures (consórcio, SEM, EP, SSA), when attributes are derived, then esfera comes from nature/name/municipio rules with `source_of_esfera` justification — never hardcoding entity_id→esfera.
3. Given `pncp+contracts` combination, then semantic roles are documented: same official origin, two audit roles.

### US2 — Entity evidence adapter (P0)

As an operator, a completed crawl window set can be projected into nominal `coverage_evidence` per entity and required source role.

**Acceptance**

1. Given contracts in lake for entity CNPJ8 and complete window proof, then `success_with_data` rows exist for sources `pncp` and `contracts`.
2. Given zero contracts after complete proof, then `success_zero` only with pagination/window proof and ≥3y query window accepted by `contracts_backfill_ok`.
3. Given incomplete windows, then success_zero is not written.

### US3 — Live 90d pilot GO (P0)

Reuse `run_contracts_90d_pilot.py`; live integral pilot (not seal-only) authorizes 3y expansion.

### US4 — Backfill ≥3 years + incremental ≤7d (P0)

Partitioned, resumable, idempotent national contracts collection with artifacts; incremental with overlap and dual freshness SLA 168h.

### US5 — Weekly fail-closed (P1)

`make extra-weekly` does not exit 0 for full consultative package when contracts gate/backfill/incremental/freshness fail.

### US6 — Consulting product (P1)

Weekly package exposes contracts lists, rankings, freshness, limitations, claims/non-claims, provenance.

## Measurable gates (candidate SHA)

```
source_applicability_resolution(historical_contracts) = 100%
capability_monitoring_coverage(historical_contracts) >= 95%
historical_contracts_backfill_window >= 3 years
historical_contracts_incremental_age <= 7 days
identity_unresolved_count = 0
applicability_unknown_count = 0
unmapped_evidence_count = 0
failed_windows = 0
freshness_unknown_in_numerator = 0
stale_in_numerator = 0
partial_in_numerator = 0
```

## Decision: separate Spec 002

Spec 001 stabilizes **measurement**. Spec 002 owns **operational fill**. Dual engine changes only when measurement cannot bind real evidence (e.g. `canonical_entity_key` mapping) without weakening gates.

## Traceability

| Requirement | Task area | Implementation | Test | DOD |
|-------------|-----------|----------------|------|-----|
| Applicability 100% | T1 | source_policy + policy yaml 2.1 | test_source_policy_canonical | § dual 95% precond |
| Entity evidence | T2 | contracts_entity_evidence.py + mig 059 | test_contracts_entity_evidence | coverage_evidence spine |
| Pilot 90d | T3 | run_contracts_90d_pilot | pilot tests + live artifact | backfill precond |
| Backfill 3y | T4 | contracts_crawler modes | window/checkpoint tests + live | § backfill 3y |
| Incremental | T5 | canonical incremental command | recovery/idempotency | freshness ≤7d |
| Weekly | T6 | weekly_cycle preconditions | weekly tests | product package |
