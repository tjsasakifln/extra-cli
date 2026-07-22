# Research — National Contracts Intelligence Architecture

**Feature:** `003-national-contracts-intelligence-architecture`  
**Date:** 2026-07-22  
**Sources:** codebase on `origin/main` @ `a38981b`, inventory A/C/D/E, live HC observation (read-only)

---

## R1 — Physical home of national contracts

**Decision:** Keep `public.pncp_supplier_contracts` as the sole fact table for national contracts (Layer 1 physical). Do not create a parallel raw clone.

**Rationale:** Table already holds national rows (FK constraints dropped in 055/056), has provenance/window columns (051), indexes for UF/supplier/orgao/objeto, and is written by the live crawler. Cloning would double storage (~2.5GB+ mid-run) and break single-writer semantics.

**Alternatives rejected:**
- Separate `contracts_national_raw` table — storage duplication, dual upsert path risk
- JSON/object storage lake — loses SQL product path and existing indexes

---

## R2 — Layer mapping (logical → physical)

**Decision:**

| Layer | Logical | Physical |
|-------|---------|----------|
| L1 Raw National | All ingested PNCP contracts | `pncp_supplier_contracts` + view `v_intel_contracts_raw_national` (scope stamp) |
| L2 Curated SC geo | UF = SC filter | view `v_intel_contracts_geo_sc` |
| L2b Canonical operational | Coverage evidence over seed universe | **unchanged** dual engine + `coverage_evidence` (spec 001) — not a product view |
| L3 Extra Intelligence | Aggregations | views `v_intel_supplier_geo`, `v_intel_agency_profile` + parameterized SQL in `scripts/national_intel` |
| L4 Delivery | CLI/exports | `python -m scripts.national_intel` (+ optional thin wrappers); reuse deliverable A–E |

**Rationale:** Views + modules beat new schemas for V1 simplicity; schema `intel` deferred until volume of objects justifies namespace.

**Alternatives rejected:**
- Schema `intel` with table copies — premature
- Materialized views on live writer DB — refresh cost + HC collision
- Only application-layer filters without views — weaker discoverability/SQL contracts

---

## R3 — Coverage vs intelligence boundary

**Decision:** Dual coverage (`scripts/coverage/dual_capability_coverage.py`) remains the only operational coverage authority. Intelligence products stamp `scope_label ∈ {raw_national, geo_sc, intel_product}` and never `canonical_sc_operational` unless they literally invoke dual coverage.

**Rationale:** Spec 001 + invariants I0–I3; national volume already used only for descriptive `data_presence`, never numerator.

---

## R4 — Delivery surface

**Decision:** New package `scripts/national_intel` as the campaign’s strategic product CLI, reusing query patterns from `contract_intel` and deliverables B/D/A. Document as complementary to `contract_intel` (operational SC-first views) rather than forking a second SmartLic.

**Rationale:** `contract_intel/cli.py` is already 1200+ LOC with SC-oriented views (`v_contract_historical` joins). National products need UF-unconstrained aggregations and explicit scope stamps; a focused package reduces merge conflict risk with HC branch edits to crawl/coverage.

**Alternatives rejected:**
- Only new SQL files without CLI — weaker operator UX
- Heavy edits to contract_intel only — high conflict / accidental SC bias
- New top-level `extra intelligence` brand — entry-point proliferation

---

## R5 — Data for development

**Decision:** Fixture-first on isolated DB port 5435. No 3y backfill. Optional future read-only sample after HC completion (integration plan).

**Rationale:** Live `extra_test:5433` is mid-write (~2.2M rows); using it for DDL/tests risks I/O contention and accidental writes.

---

## R6 — Indexes

**Decision:** V1 ships **views only** (migration 059). Analytical composite indexes (UF+supplier, orgao8+data) documented in performance artifacts; apply only on isolated DB if fixture benchmarks require, never on live 5433 during backfill.

**Rationale:** Subagent E: dual GIN already heavy; new indexes on live writer dangerous mid-backfill.

---

## R7 — Claim epistemology

**Decision:** Every product row-level or report-level field that is not a direct column aggregation must carry `claim_class`: `fact` | `indicator` | `hypothesis`. Partnership/consortium/subcontract always `hypothesis` unless dedicated evidence table exists (it does not today → never assert).

**Rationale:** Product design D + campaign non-goals.

---

## R8 — Benchmark minimum sample

**Decision:** Default `min_sample=20` contracts for percentile benchmarks; below → `insufficient_sample` status. Configurable via CLI.

**Rationale:** Conservative default; avoids fake market prices.

---

## R9 — Column semantics

**Decision:** Use `valor_total` as stored global contracted value (from PNCP valorGlobal mapping). Never label as “preço praticado” or unit price without quantity.

**Rationale:** Inventory A + crawler transform notes.

---

## Open items closed by inspection

| Former ambiguity | Resolution |
|------------------|------------|
| Spec number | `003` (001 dual, 002 only on HC branch) |
| Base SHA | `origin/main` a38981b |
| Isolated DB | port 5435 / `extra_national_intelligence_test` |
| Canonical universe size | seed-driven; historical 1093 |
| Entry point name | `scripts.national_intel` |
