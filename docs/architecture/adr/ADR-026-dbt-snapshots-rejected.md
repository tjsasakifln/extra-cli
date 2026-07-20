# ADR-026 — dbt snapshots: rejected without experiment

- **Status:** ACCEPTED (`REJECTED_WITHOUT_EXPERIMENT`)  
- **Date:** 2026-07-20  
- **Campaign:** ARCH-RESET-2026-07-20  
- **Supersedes:** any prior wording of this ADR that claimed a completed dbt evaluation  

## Decision

**Do not adopt dbt-core / dbt snapshots** in the operational Extra weekly pipeline or as a second migration/transform line.

**Honest status:** This rejection is **`REJECTED_WITHOUT_EXPERIMENT`**. No dbt project was installed or executed against a ≥200 opportunity temporal corpus in this campaign. A synthetic 5-dict “benchmark” is **not** experimental evidence of SCD2 correctness.

## Context

Operational truth remains PostgreSQL migrations + application code. Research suggested dbt snapshots for tender status history; that remains a hypothesis.

## Forces

- Snapshot interval ≠ juridical event time  
- Sources without reliable `updated_at`  
- Dual truth if dbt models diverge from migrations  
- Single-maintainer cognitive load  
- Lack of isolated experiment / gold temporal corpus in this campaign  

## Re-open criteria (only path to ADOPT)

1. Isolated Postgres schema (non-production authority)  
2. Dataset ≥200 opportunities with gold status transitions  
3. Measured concordance on that corpus  
4. Explicit ADR superseding this decision with experiment artifacts  

## Consequences

- No `dbt-core` in production requirements.  
- Status history remains application/SQL-owned until a real experiment re-opens the case.  

## Evidence

- `docs/ops/campaigns/ARCH-RESET-2026-07-20/spikes/DBT/DECISION.md`  
- Evaluator (remediation): `scripts.architecture.spike_e_dbt_honest` when present on branch #62  
