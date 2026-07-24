# ADR: National Contracts Intelligence Layers

**Status:** Accepted (campaign-local)  
**Date:** 2026-07-22  
**Campaign:** NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01

## Context

National PNCP contracts land in `pncp_supplier_contracts` while SC operational coverage is measured by dual capability over a seed universe (~1093). Without explicit layers, operators may confuse row volume with coverage.

## Decision

1. **L1 physical** = existing `pncp_supplier_contracts` (no clone).
2. **L2 geo SC** = SQL view filter `uf = 'SC'` — not operational coverage.
3. **L2b operational** = dual coverage engine only (spec 001) — unchanged.
4. **L3** = aggregation views + `scripts.national_intel` products.
5. **L4** = CLI JSON exports with lineage envelope.
6. **No MVs in V1** on writer DB; no indexes applied to live HC DB during backfill.

## Consequences

- Simple, additive, reversible (`DROP VIEW` only if needed).
- Must discipline product naming (`scope_label`) to prevent false coverage claims.
- Full national analytics richness depends on HC backfill completion (soft dependency).

## Alternatives rejected

| Alternative | Why rejected |
|-------------|--------------|
| Separate raw table | Duplication + dual write path |
| Schema `intel` copies | Premature complexity |
| MVs on 5433 now | Collides with live backfill I/O |
| New SmartLic-like app | Out of scope / YAGNI |
