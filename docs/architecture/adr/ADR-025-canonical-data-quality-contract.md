# ADR-025 — Canonical data quality contract (Python/SQL)

- **Status:** ACCEPTED  
- **Date:** 2026-07-20  
- **Campaign:** ARCH-RESET-2026-07-20 · PR F  

## Decision

Adopt a **single quality contract** defined in `scripts/quality/canonical_checks.py` (check IDs + pure evaluators + SQL stubs). Existing gates remain engines to be unified gradually.

**Reject for now:** Soda Core and dbt tests as parallel production quality systems.

## Rationale

Lowest total cost given existing Python/SQL quality surface; avoids dual DSL; fail-closed fixture suite without DB.

## Consequences

- New checks must register a `check_id` in CRITICAL_CHECKS.  
- Future dbt/Soda only as optional engines behind the same IDs after separate spikes.  
