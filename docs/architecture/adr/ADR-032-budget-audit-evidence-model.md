# ADR-032 — Budget Audit Evidence Model

**Status:** Proposed (campaign branch)  
**Date:** 2026-07-24  
**Campaign:** `ENGINEERING-BUDGET-COMPOSITION-BDI-AUDIT-01`  
**Deciders:** Extra Consultoria engineering / campaign implementer  

## Context

The product scope includes analysis of planilhas orçamentárias, composições and BDI when documents are available (`DOD.md`). Legacy competitive tooling (`scripts/lib/bid_simulator.py`) uses sector-generic BDI/margins and win-probability heuristics that must **not** feed automatic audit conclusions.

Parallel campaigns (consulting pack, entity linkage, edital triage, VPS soak) share the monorepo. Budget audit must run in a dedicated worktree with a hard fileset allowlist and **zero** database/VPS/migration touch.

## Decision

1. **File-based case store** is the canonical model for each audit case (JSON/JSONL/XLSX/PDF/HTML/MD + content-addressed originals by SHA-256).
2. **Evidence-first cells:** every finding cites document, sheet and cell when available. Formula and cached value are stored separately. Missing cache is `MISSING_CACHE` / `NOT_EVALUATED` — never coerced to zero.
3. **No invented economics:** BDI is not margin; no generic sector margins; no win probability; no optimal bid; official references require explicit manifests (system, month, locality, tax regime, sha256).
4. **Isolation guard** on every CLI entry: worktree lock, branch, allowlist, denylist, `production_touched=false`, `soak_touched=false`, `database_used=false`.
5. **Entry point:** `python3 -m scripts.budget_audit` with create/ingest/map/audit/compare/references/report/verify/run.
6. **Global exit states only:** `PASS` | `BLOCKED` | `FAIL`.
7. **Separation from bid_simulator:** analyze and document risk; do not import or reuse its constants in audit paths.

## Consequences

### Positive

- Auditable, replayable cases without DB coupling.
- Safe parallel execution with other campaigns.
- Clear human responsibility for legal/commercial conclusions.

### Negative / trade-offs

- Complex Excel formulas are not recalculated as Excel; rely on cached values.
- ODS/XLS/PDF support is limited or conversion-required.
- Full official SINAPI/SICRO distribution is not embedded; comparison requires user-supplied reference manifests.

## Compliance

- Does not modify `DOD.md` in this campaign; produces acceptance candidates in integration-handoff.
- Does not alter `scripts/lib/bid_simulator.py`.

## References

- Spec: `specs/008-engineering-budget-composition-bdi-audit/`
- Package: `scripts/budget_audit/`
- Campaign artifacts: `artifacts/campaigns/ENGINEERING-BUDGET-COMPOSITION-BDI-AUDIT-01/`
