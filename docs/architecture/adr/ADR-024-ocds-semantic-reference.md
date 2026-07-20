# ADR-024 — OCDS as semantic interoperability reference

- **Status:** ACCEPTED  
- **Date:** 2026-07-20  
- **Campaign:** ARCH-RESET-2026-07-20 · spike PR D  
- **Baseline commit:** `d6d9e1984e348d64a669546613e192e4ebf610cd`

## Context

Extra operational data is PNCP/portal-centric in PostgreSQL. Open Contracting Data Standard (OCDS) 1.1.x offers a common vocabulary for tender/award/contract. A thin bridge already exists (`scripts/ocds_bridge/mapping.py`).

## Decision

**`ADOPT_AS_REFERENCE` + optional export layer** — **not** physical model replacement.

1. Keep PostgreSQL operational schema as source of truth.  
2. Maintain OCDS-inspired mapping for export/interoperability and documentation.  
3. Do **not** adopt Kingfisher or full OCDS warehouse.  
4. Document Brazilian gaps (status vocab, party schemes, missing awards/documents/items).  
5. Extension fields under `extra:*` (provenance, value_semantics) are allowed for project honesty.

## Consequences

### Positive
- Shared vocabulary for buyers/suppliers/tenders/contracts.  
- Explicit “contracted ≠ paid” semantics preserved.  
- Round-trip tests for essential bid fields.

### Negative
- Strict OCDS JSON Schema validation fails when `extra:*` and local status strings remain.  
- Incomplete mapping (awards, documents, items, amendments).

### Rejected alternatives
- Full OCDS physical tables — cost high, dual truth risk.  
- Kingfisher ingestion pipeline — second orchestrator risk without net gain proven.

## Evidence

- Field matrix: `docs/ops/campaigns/ARCH-RESET-2026-07-20/spikes/OCDS/FIELD-MATRIX.md`  
- Sample package + validation: `docs/ops/campaigns/ARCH-RESET-2026-07-20/spikes/OCDS/`  
- Tests: `tests/test_ocds_bridge_mapping.py`, `tests/test_ocds_spike_validate.py`

## Rollback

Remove spike docs and leave thin mapping as-is; no production default path depends on OCDS warehouse.
