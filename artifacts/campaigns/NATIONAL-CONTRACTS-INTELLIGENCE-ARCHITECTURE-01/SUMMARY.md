# SUMMARY — NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01

## 1. Executive summary

This campaign designed and implemented an **isolated** architecture that treats national PNCP contracts as a **strategic intelligence asset**, while keeping SC operational dual coverage (spec 001) as the only path for monitoring gates. Work ran on a dedicated worktree and Postgres (port **5435**), without interrupting the live HC 3y backfill on **5433**.

## 2. Strategic thesis validated

**Accepted (refined):** Four logical layers over one physical fact table.

| Layer | Implementation |
|-------|----------------|
| L1 Raw National | `pncp_supplier_contracts` + `v_intel_contracts_raw_national` |
| L2 Geo SC | `v_intel_contracts_geo_sc` (UF=SC only; **not** coverage) |
| L2b Operational SC | Unchanged dual coverage engine |
| L3 Intelligence | `v_intel_supplier_geo`, `v_intel_agency_profile` + `scripts.national_intel` |
| L4 Delivery | CLI JSON envelope with lineage |

## 3–4. Architecture & alternatives rejected

See `architecture/ADR-national-intel-layers.md` and `specs/003/.../research.md`.

Rejected: table clones, MV on live writer, second SmartLic platform, re-running 3y backfill.

## 5–7. Layers, flow, objects

Flow: PNCP → crawler (HC owns live write) → `pncp_supplier_contracts` → intel views/CLI (read) vs dual coverage evidence (operational).

## 8–9. Strategic products delivered (fixture)

1. **competitors_geo** — rankings + UF footprint + entrant **hypothesis**
2. **benchmarks_value** — percentiles with `min_sample` gate
3. **agencies_profile** — volume + top supplier share **indicator**

Examples under `products/*/example.json`.

## 10–11. Limitations & SC coverage protection

- Keyword ≠ technical equivalence  
- valor_total ≠ unit price  
- National completeness not claimed  
- Adversarial tests: presence can be 100% while coverage_pct stays 0  

## 12–14. Benchmarks, storage, VPS

See `performance/*`. Planning envelope ~3–7M rows / tens of GB with indexes. VPS backup scripts exist; national dump not proven here.

## 15. SmartLic / CONFENGE

No duplication of SmartLic platform. Integration remains future/read-only after HC completion.

## 16. Key files changed

- `db/migrations/059_national_contracts_intelligence_layers.sql`
- `scripts/national_intel/**`
- `tests/national_intel/**`
- `specs/003-national-contracts-intelligence-architecture/**`
- `artifacts/campaigns/NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01/**`

## 17. Commits

Local commits on `campaign/national-contracts-intelligence-architecture-01` (see git log).

## 18. Tests

`pytest tests/national_intel/ --no-cov` → **26+ passed (adversarial NV matrix + products)**

## 19. Review

`review/independent-review.md` — CONDITIONAL PASS (fixture isolation)

## 20. Residual risks

HC merge drift; fixture vs full national data; deferred indexes.

## 21. Final state

Gates: PARALLEL_ISOLATION_PASS, SPEC_KIT_PASS, BASELINE_INVENTORY_PASS, ARCHITECTURE_DECISION_PASS, ISOLATED_IMPLEMENTATION_PASS (fixture), STRATEGIC_PRODUCTS_PASS (fixture), SC_COVERAGE_ISOLATION_PASS (unit adversarial).

## 22. Integration condition with HC campaign

Only after HC 3y windows complete + entity projection + dual ≥95% evidence: optionally point read-only analytics at production national table; rebase this branch on accepted main; never claim coverage from intel products.
