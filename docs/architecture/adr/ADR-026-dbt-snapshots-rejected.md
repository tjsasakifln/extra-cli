# ADR-026 — dbt snapshots rejected for operational core

- **Status:** ACCEPTED (REJECTED_SPIKE for production)  
- **Date:** 2026-07-20  
- **Campaign:** ARCH-RESET-2026-07-20  

## Decision

**Do not adopt dbt-core / dbt snapshots** as part of the operational Extra weekly pipeline or as a second migration/transform line.

## Context

Spike E evaluated SCD Type 2 for tender status history. Operational truth remains PostgreSQL migrations + application code.

## Forces

- Snapshot interval ≠ juridical event time  
- Sources without reliable `updated_at`  
- Dual truth if dbt models diverge from migrations  
- Single-maintainer cognitive load  

## Consequences

- History of status changes stays application/SQL-owned until a dedicated analytics warehouse is justified.  
- dbt may be reconsidered as **REFERENCE_ONLY** for a separate analytics schema with no product authority.
