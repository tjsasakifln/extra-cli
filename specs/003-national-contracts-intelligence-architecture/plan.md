# Implementation Plan: National Contracts Intelligence Architecture

**Branch**: `campaign/national-contracts-intelligence-architecture-01` | **Date**: 2026-07-22 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/003-national-contracts-intelligence-architecture/spec.md`

## Summary

Organize existing national PNCP contracts (`pncp_supplier_contracts`) into explicit analytical layers (raw national → geo SC → intelligence products → delivery) without re-running backfill, without writing the HC campaign database, and without allowing national volume to contaminate dual SC operational coverage (spec 001). Deliver three fixture-backed products (competitors geo, benchmarks, agency profiles) via `scripts.national_intel`, additive SQL views (migration 059), and adversarial coverage-isolation tests.

## Technical Context

**Language/Version**: Python 3.11+ (project standard)  
**Primary Dependencies**: psycopg/psycopg2 as used by existing scripts; pytest; PostgreSQL 16  
**Storage**: PostgreSQL — isolated `extra_national_intelligence_test` @ 5435 for this campaign; fact table `pncp_supplier_contracts`  
**Testing**: pytest unit + real Postgres on isolated DSN  
**Target Platform**: Linux local / Docker Postgres / future VPS  
**Project Type**: CLI + SQL analytics on existing datalake  
**Performance Goals**: Fixture products < 5s; document EXPLAIN on fixture scale; no live 5433 heavy scans during HC write  
**Constraints**: Additive migrations only; no HC path writes; no dual-coverage regression; no new 3y crawl  
**Scale/Scope**: Design for 3–7M national contracts eventually; implement/test with fixtures (~100–1000 rows)

## Constitution Check

*GATE: pass before research; re-check after design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I Merge/CI integrity | PASS design | Tests required for coverage isolation; no skip/xfail to hide |
| II Architecture impact discipline | PASS | Smallest delta: views + new package; no parallel platform |
| III DOD/ADR handoffs | PASS plan | ADR in `artifacts/.../architecture/`; DOD not falsely marked |
| IV Parallel work safety | PASS | Isolation artifacts; exclusive file ownership table below |

**Post-design re-check:** Still PASS — no destructive DDL; dual engine untouched; HC resources protected.

## Project Structure

### Documentation (this feature)

```text
specs/003-national-contracts-intelligence-architecture/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
├── checklists/requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
db/migrations/059_national_contracts_intelligence_layers.sql

scripts/national_intel/
├── __init__.py
├── lineage.py          # output envelope + scope stamps
├── competitors.py      # supplier geo / rankings
├── benchmarks.py       # value distributions
├── agencies.py         # org profiles
└── cli.py              # argparse entry

tests/national_intel/
├── test_coverage_isolation_national_volume.py
├── test_products_fixture.py
└── conftest.py         # isolated DSN fixtures

artifacts/campaigns/NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01/
├── safety/             # Phase 0
├── inventory/          # Phase 2
├── architecture/       # ADRs
├── products/           # product design + example outputs
├── coverage-isolation/
├── performance/
└── STATUS.md
```

## File ownership (subagents / tracks)

| Track | Responsibility | Allowed writes | Forbidden |
|-------|----------------|----------------|-----------|
| Spec/coord | Spec kit, STATUS, integration | `specs/003/**`, `artifacts/.../STATUS.md`, architecture ADRs | HC paths |
| F SQL | Migration 059 | `db/migrations/059_*.sql` | crawlers, dual_capability |
| G CLI | national_intel package | `scripts/national_intel/**` | `scripts/crawl/**`, HC artifacts |
| H Tests | pytest | `tests/national_intel/**` | weakening dual tests |
| I Review | review only | `artifacts/.../review/**` | implementation |

## Phase mapping

| Campaign phase | Spec kit / work | Gate |
|----------------|-----------------|------|
| 0 Isolation | safety/* | PARALLEL_ISOLATION_PASS |
| 1 Spec kit | this plan + tasks | SPEC_KIT_PASS |
| 2 Inventory | inventory/* (done) | BASELINE_INVENTORY_PASS |
| 3 Architecture | ADR + data-model | ARCHITECTURE_DECISION_PASS |
| 4 Implementation | migration + package | ISOLATED_IMPLEMENTATION_PASS |
| 5 Products | 3 products | STRATEGIC_PRODUCTS_PASS |
| 6 Coverage proof | adversarial tests | SC_COVERAGE_ISOLATION_PASS |

## Implementation approach

1. **Migration 059** creates thin scope views + supplier geo + agency aggregate views over `pncp_supplier_contracts` (additive, `CREATE OR REPLACE VIEW`).
2. **`scripts.national_intel`** implements three products with JSON envelope (contracts/product-output.schema.json).
3. **Fixtures** seed isolated DB with SC + non-SC rows and synthetic coverage_evidence for dual isolation tests.
4. **Adversarial tests** assert dual coverage metrics invariant under national volume insert/delete (or pure unit mock of calculator inputs if dual requires full seed — prefer real dual with fixture universe subset documented).
5. **No crawler changes.** No HC checkpoint interaction.

## Complexity Tracking

| Violation | Why needed | Simpler alternative rejected because |
|-----------|------------|--------------------------------------|
| New package vs only SQL | Operator CLI + lineage required by FR-010/015 | SQL-only lacks envelope/lineage automation |
| Three product modules | Clear ownership / testability | One mega-module harder to review |

## Risks & mitigations

See spec Risks + `artifacts/.../safety/collision-matrix.md` + coverage-isolation risks.
