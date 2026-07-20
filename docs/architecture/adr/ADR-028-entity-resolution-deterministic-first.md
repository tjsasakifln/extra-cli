# ADR-028 — Entity resolution: deterministic first; Splink deferred

- **Status:** ACCEPTED  
- **Date:** 2026-07-20  

## Decision

Keep deterministic identity (CNPJ-14, CNPJ-8 root, IBGE, official IDs, aliases).  
**Reject Splink production adoption** until a ≥300-pair residual gold corpus exists and auto-link precision ≥99% is proven.  
Probabilistic candidates must never silently override conflicting CNPJ roots.

## Evidence

`scripts/entity_identity/pncp_orgao_resolve.pick_match` root-guard + spike H benchmark.
