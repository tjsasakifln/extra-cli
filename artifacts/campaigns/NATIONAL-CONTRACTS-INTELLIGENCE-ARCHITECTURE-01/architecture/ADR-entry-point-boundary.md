# ADR: Boundary between `contract_intel` and `national_intel`

**Status:** Accepted  
**Date:** 2026-07-22  
**Campaign:** NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01  
**Final HEAD at decision:** (updated on close)

## Context

Two surfaces exist:

| Surface | Role |
|---------|------|
| `python -m scripts.contract_intel` | Operational / SC-universe analytics (`historico`, `fornecedores`, `manifesto`, …); dual backends; target universe views |
| `python -m scripts.national_intel` | Strategic national products with `scope_label`, claim classes, isolation DSN default |
| `scripts/ops/deliverable_{a,b,d}_*` | DoD package deliverables (ranking, competitors, prices) — batch reports, not interactive CLI |

Duplication risk: ranking/percentiles appear in multiple places.

## Decision

1. **Single product engine** for the three strategic products lives in `scripts/national_intel/*` (queries + envelope).
2. **Canonical discoverability** for operators is extended on `scripts.contract_intel` via facade subcommands:
   - `national-competitors`
   - `national-benchmarks`
   - `national-agencies`  
   which **only** call `national_intel` (no second SQL implementation).
3. `python -m scripts.national_intel` remains a **supported alias** for the same engine (tests, campaign scripts, NATIONAL_INTEL_DSN workflows).
4. Deliverables A/B/D stay **batch DoD artifacts**; they are not reimplemented here. Reuse is by documentation and future shared helpers, not by silent dual engines in this PR.
5. Dual coverage remains exclusively `scripts.coverage.dual_capability_coverage` — neither CLI computes operational coverage %.

## Why not fold everything into contract_intel only

- `contract_intel` is large, SC-view-oriented, sqlite+pg dual path; stuffing national strategic semantics increases merge conflict risk with HC campaign and blurs operational vs strategic scope.
- Isolation campaign requires a package that defaults to `NATIONAL_INTEL_DSN` and never implies dual gate.

## Why not keep only national_intel without facade

- Prefer one place operators look (`contract_intel`) per discoverability; facade prevents second “unknown” CLI family.

## Alternatives rejected

| Alternative | Why rejected |
|-------------|--------------|
| Full rewrite of deliverable_b into national_intel | Out of scope; DoD package stability |
| Delete national_intel; reimplement in contract_intel only | High conflict risk; loses isolation-focused package |
| Two independent SQL engines forever | Divergent truth |

## Maintenance rule

Any change to ranking/benchmark/agency **logic** must land in `scripts/national_intel/` first; facade and `python -m scripts.national_intel` stay thin.
