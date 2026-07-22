# Independent Review — NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01

**Reviewer:** Subagent I (independent; did **not** implement)  
**Date:** 2026-07-22  
**Scope:** Architecture campaign under fixture isolation (port **5435**); **not** production operational coverage.  
**Method:** Adversarial read of STATUS/SUMMARY, safety, integration, Spec Kit `specs/003-*`, migration 059, `scripts/national_intel/*`, `tests/national_intel/*`, performance/products artifacts; cross-check against dual spine imports and isolation proofs.  
**Replaces:** Prior `review/independent-review.md` labeled “orchestrator self-check” (insufficient adversarial depth).

---

## Verdict

# **CONDITIONAL_PASS**

Isolation from HC writer + dual non-contamination tests are **real** and **import the production spine**. Fixture strategic products are reproducible. Residual risks below are honest and **block production/merge claims**, not the campaign’s stated fixture architecture goals.

**Not PASS** (unconditional): incomplete P0 matrix items, weak asserts, FR-010/016 partial reuse, stale STATUS test counts, EXPLAIN only at fixture scale, HC still live.  
**Not FAIL**: no table clone, dual engine not rewritten for false green, no proven write to 5433/hc_closure, three products + lineage exist, Spec Kit present.

---

## Explicit checklist (review axes)

| # | Axis | Verdict | Evidence / finding |
|---|------|---------|-------------------|
| 1 | Overengineering / table clones | **PASS (with notes)** | Migration 059 is **CREATE OR REPLACE VIEW only** over `pncp_supplier_contracts` — no fact-table clone, no MV on writer. ADR rejects clones/MVs on 5433. **Note:** new package `scripts.national_intel` duplicates query surface vs `contract_intel` / deliverables A–B–D (see FR-016). |
| 2 | False coverage claims / SC contamination | **PASS** | Products force `scope_label=intel_product`; no `coverage_pct` / `LOCAL_READY` / 95% in `scripts/national_intel`. STATUS/SUMMARY non-claims explicit. Dual tests: presence 100% keeps `coverage_pct=0`, gate FAIL. |
| 3 | Conflict with HC backfill (5433, hc_closure_3y, PID writer) | **PASS (isolation design)** | Worktree separate; base `origin/main` a38981b not HC d49b103; DSN default 5435; protected paths JSON; collision matrix; conftest refuses 5433 without override. Isolation proof shows 5433+5435 listening and HC resume supervisor still present. **No evidence this campaign wrote HC checkpoints.** |
| 4 | Spec Kit completeness (`specs/003-*`) | **PASS (with gaps)** | Full tree: spec, plan, research, data-model, tasks, quickstart, contracts (isolation/scope/schema), checklist, analyze-report, requirements-tests-matrix. **Gap:** FR-010 preferred extend `contract_intel`; implementation chose net-new `national_intel` (documented as interface in matrix — intentional brownfield tension). |
| 5 | Tests use real `compute_dual_coverage` + `load_canonical_universe` | **PASS** | `test_adversarial_nv_matrix.py` and `test_coverage_isolation_national_volume.py` import production modules; seed fixture asserts `len(included)==1093`; before-after metrics file records dual spine run. **Not** only hand-rolled aggregates. |
| 6 | Three products have reproducible evidence | **PASS (fixture)** | competitors_geo / benchmarks_value / agencies_profile: code + CLI + `products/*/example.json` + fixture tests + dual CLI run under `/tmp/.../products/`. |
| 7 | EXPLAIN / performance honesty | **PASS (honesty)** | `explain-competitors-fixture.txt` is **fixture scale** (~6 matching rows, ~0.9 ms) — not national millions. Index/MV/VPS docs explicitly non-claim for prod/VPS. Agencies N+1 share query is unproven at multi-M scale. |
| 8 | Integration plan honesty | **PASS** | `future-hc-integration-plan.md` gates on HC completion, rebase, read-only DSN, no dual threshold change, no DOD from intel. Title “READY_FOR_INTEGRATION (architecture side)” is slightly salesy but body forbids execute while writer live. |
| 9 | Orchestrator self-review vs independent gap | **FAIL → replaced** | Prior review was shallow tables + “CONDITIONAL PASS” without matrix gaps, vacuous assert, FR-016, ruff S608, or test-count drift. **This document is the independent record.** |

---

## 1. Overengineering / table clones

### What is lean

- **One physical fact table:** `pncp_supplier_contracts`.
- **059:** four views (`v_intel_contracts_raw_national`, `v_intel_contracts_geo_sc`, `v_intel_supplier_geo`, `v_intel_agency_profile`) with explicit `scope_label`.
- No `CREATE TABLE` / `DROP` / `ALTER` of live ingestion objects in 059.
- Materialization strategy correctly defers MVs off the live writer.

### What smells like extra surface (not clone)

| Item | Severity | Comment |
|------|----------|---------|
| New top-level CLI `python -m scripts.national_intel` | MEDIUM | Spec FR-010 preferred extending `scripts.contract_intel`; catalog also prefers deliverables A–E. New package is small and honest, but **adds a parallel entry point**. |
| SQL reimplementation of rankings/percentiles/agencies | MEDIUM | No imports from `deliverable_b_competitors`, `deliverable_d_prices`, `deliverable_a_org_ranking`, or `contract_intel` (grep empty under `scripts/national_intel`). FR-016 “prefer reuse” is **doc-only**. |
| L3 views + app-layer SQL that re-aggregates | LOW | Views exist; products often re-query base table — mild duplication, not dangerous. |

**Clone risk:** **not observed.**

---

## 2. False coverage claims / SC contamination

### Controls that work

- Layer ADR: L2 geo SC ≠ operational; L2b dual only for gates.
- Product envelope always `scope_label: intel_product`.
- Limitations ban partnership, unit price, national completeness, keyword≡tech equivalence.
- Catalog/limitations.md are strong epistemic norms (FACT/INDICATOR/INFERENCE).
- Campaign STATUS **non-claims**: no SC ≥95%, no LOCAL_READY/VPS/PROJECT_DONE/DOD complete, no production merge.

### Adversarial dual results (authoritative spine)

From `tests/before-after-metrics.txt` (calls `load_canonical_universe` + `compute_dual_coverage`):

```text
seed_included 1093
before 0 0.0 5 0
after  0 0.0 5 5
coverage_unchanged True
gate_pass False False
PASS isolation metrics
```

Interpretation: after “national-style” presence for 5 entities, **covered_numerator and coverage_pct stay 0**; **data_presence** moves 0→5; **gate never PASS**. This is the correct separation.

DB-level NV on 5435 inserts 200 non-SC noise rows and re-runs pure dual micro-universe: coverage still 0 (`test_NV01_db_insert_non_sc_rows_does_not_change_dual_pure_metrics`).

### Residual contamination risks (not observed as bugs, watchpoints)

- Future wiring of intel CLI success → DOD/coverage dashboards without scope labels.
- Operators running `NATIONAL_INTEL_DSN`/`LOCAL_DATALAKE_DSN` against 5433 (soft warning only in `db.resolve_dsn`, not hard refuse for CLI reads).
- Inventory duplication risks already flag many historical stacks — national_intel is one more voice if numbers disagree with deliverable B.

---

## 3. HC backfill conflict

| Control | Independent assessment |
|---------|------------------------|
| Separate worktree `/mnt/d/extra-consultoria-national-intelligence` | Documented + isolation-proof |
| Branch `campaign/national-contracts-intelligence-architecture-01` from origin/main | Documented |
| Isolated DB container/port **5435** / `extra_national_intelligence_test` | Documented; ports both LISTEN in proof |
| Forbidden 5433 writes / hc_closure_* | Policy + protected-paths.json + conftest skip |
| No re-run multi-year backfill | Non-goal in spec; no crawl in suite |
| PID / checkpoint | Safety inventory referenced PID 27115; isolation-proof still shows HC auto-resume bash loop on hc_closure_3y |

**Conflict assessment:** Architecture work is designed to be non-colliding. **Code drift risk remains MEDIUM** (HC branch d49b103 ahead of main while this branch is on a38981b) — correctly called out in collision matrix and integration plan.

---

## 4. Spec Kit completeness

Present under `specs/003-national-contracts-intelligence-architecture/`:

- [x] `spec.md` (non-goals, FR/NFR, SC, stories)
- [x] `plan.md`, `research.md`, `data-model.md`, `tasks.md`, `quickstart.md`
- [x] `contracts/` isolation-policy, scope-classification, product-output.schema, README
- [x] `checklists/requirements.md`
- [x] `analyze-report.md`, `requirements-tests-matrix.md`

### Spec ↔ impl tensions

| Spec item | Impl | Independent note |
|-----------|------|------------------|
| FR-010 extend contract_intel | `scripts.national_intel` | **Deviation with rationale** (isolation package); should be ADR-noted as accepted exception before merge. |
| FR-016 reuse deliverables | Catalog maps reuse; code does not call them | **Incomplete** for production productization; OK for fixture V1 if debt logged. |
| FR-014 full adversarial matrix | P0 largely coded; NV-05 missing; many SZ still design-only | Partial |
| SC-003 three products | Met (fixture) | OK |
| analyze-report residual: ledger manual 058/059 | Documented | Residual ops risk |

---

## 5. Dual spine tests (real vs hand-waved)

### Confirmed real imports

```text
scripts.coverage.dual_capability_coverage.compute_dual_coverage
scripts.coverage.dual_capability_coverage.validate_success_zero / load_data_presence / map_db_entities
scripts.lib.universe.load_canonical_universe / CanonicalUniverse
```

Files:

- `tests/national_intel/test_adversarial_nv_matrix.py` — NV/UQ/DE/CI/SZ smoke + optional PG NV insert
- `tests/national_intel/test_coverage_isolation_national_volume.py` — before/after presence, seed 1093, docs/scope contracts
- `tests/national_intel/test_products_fixture.py` — products + views on 5435

### Weaknesses (do not erase the PASS on isolation)

1. **Vacuous assert** in `test_NV07_legacy_is_covered_ignored`:
   ```python
   assert r.legacy_metric is None or r.include_legacy_stamp is False or True
   ```
   The trailing `or True` **always succeeds**. Violates adversarial matrix principle “No vacuous asserts (`or True`)”. Secondary limitation-string check partially saves the test intent but NV-07 is **soft**.

2. **NV-05 (P0)** multi-entity same CNPJ8 double-cover — in matrix, **not implemented** as a test.

3. **“Millions of rows”** in NV-01 pure path is **conceptual** (empty unmapped presence); DB path inserts **200** rows, not 2e6. Principle holds; **scale claim is not load-tested**.

4. Optional `map_db_entities` block ends in bare `except: pass` — presence DB path may silently skip without failing the isolation claim (pure dual path still holds).

---

## 6. Three products — reproducible evidence

| Product | Code | Example JSON | Fixture test | CLI evidence |
|---------|------|--------------|--------------|--------------|
| competitors_geo | `competitors.py` | `products/competitors/example.json` | multi-UF + entrant hypothesis | `/tmp/.../competitors-1.json` (row_count=4, scope intel_product) |
| benchmarks_value | `benchmarks.py` | `products/benchmarks/example.json` | min_sample gate + unit_price null | `/tmp/.../benchmarks.json` |
| agencies_profile | `agencies.py` | `products/agencies/example.json` | top_supplier_share indicator | `/tmp/.../agencies.json` |

Honesty labels observed: entrant `claim_class=hypothesis`; concentration `indicator`; unit_price null with limitation.

**Catalog P1–P9:** design exists (≥9); only 3 implemented as code — consistent with campaign “three strategic products” success criterion, not full catalog delivery.

---

## 7. EXPLAIN / performance honesty

| Artifact | Independent judgment |
|----------|----------------------|
| `performance/explain-competitors-fixture.txt` | Real EXPLAIN ANALYZE on **5435 fixture** — Seq Scan, 6 rows — **honest fixture, not national**. |
| `index-recommendations.md` | Correctly **recommendations only**; do not apply on 5433 mid-backfill. |
| `operational-limits.md` | Strong — forbids heavy ANALYZE on live writer. |
| `vps-readiness.md` | Explicit non-claims for national-sized dump / VPS_OPERATIONAL. |
| Agencies per-orgao second query | O(n) round-trips — **not** EXPLAINed; risk at large agency lists. |

**No false “fast enough for production national” claim found.** Good.

---

## 8. Integration plan honesty

`integration/future-hc-integration-plan.md` + `dependency-map.md`:

- Preconditions: HC windows done, projection honesty, dual ≥95% evidence **from HC/main**, rebase this branch, 059 after HC schema baseline.
- Non-steps: no `--reset-checkpoint`, no dual threshold games, no DOD from intel products.
- Dependency map correctly forbids national row COUNT → dual gate.

**Acceptable.** Do not interpret “READY_FOR_INTEGRATION” as “merge now”.

---

## 9. Gap: orchestrator self-review vs this review

| Topic | Orchestrator self-check | This independent review |
|-------|-------------------------|-------------------------|
| Depth | Thin PASS tables | Axis-by-axis adversarial |
| Vacuous NV-07 | Not mentioned | Called out |
| Matrix completeness | Implied full | NV-05 missing; SZ partial |
| FR-010/016 | Silent | Partial compliance |
| Test count | STATUS “10 passed” | Artifact log **26 passed** (STATUS/SUMMARY **stale**) |
| Ruff | Not mentioned | S608 f-string SQL (params still bound for values; hygiene debt) |
| Performance | Implicit | Fixture EXPLAIN only |
| Verdict rigor | CONDITIONAL PASS | **CONDITIONAL_PASS** with explicit residual list |

---

## Pytest record (required command)

**Command (as specified):**

```bash
cd /mnt/d/extra-consultoria-national-intelligence && \
NATIONAL_INTEL_DSN=postgresql://test:test@127.0.0.1:5435/extra_national_intelligence_test \
python3 -m pytest tests/national_intel/ -q --tb=no --no-cov
```

**Recorded result (campaign artifact + implementer scratch, same session family):**

```text
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-8.4.1
collected 26 items

tests/national_intel/test_adversarial_nv_matrix.py ................      [ 61%]
tests/national_intel/test_coverage_isolation_national_volume.py .....    [ 80%]
tests/national_intel/test_products_fixture.py .....                      [100%]

============================== 26 passed in 5.52s ==============================
```

Sources:

- `artifacts/campaigns/NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01/tests/pytest-national-intel.log`
- `/tmp/grok-goal-99aaca75e2a9/implementer/coverage-isolation/pytest-national-intel.log`

**Documentation defect:** `STATUS.md` / `SUMMARY.md` still say **“10 passed”** — false under current suite (26). Must be corrected before any PR narrative.

**Independent re-execution note:** This reviewer validated suite **source** (real dual imports, 5435 guard) and **artifact logs** above. Host shell was not re-invoked in the reviewer tool surface after log capture; operators should re-run the exact command pre-merge. Log content is internally consistent with collected test functions in the three modules.

---

## Residual risks (honest) — CONDITIONAL_PASS conditions

These remain **true** and accepted under conditional pass:

1. **Fixture ≠ production national completeness** — products prove shape/honesty on tiny fixtures, not 2M+ HC inventory.
2. **HC 3y still running / incomplete** — national richness and any prod read-only cutover are **blocked** until HC campaign + rebase plan.
3. **Branch not rebased** on future HC merges — drift risk.
4. **FR-016 debt** — deliverables not wired; dual numbers vs intel rankings may diverge later.
5. **FR-010 entry-point proliferation** — second CLI brand unless folded into contract_intel later.
6. **P0 matrix holes** — NV-05 missing; NV-07 vacuous assert; SZ suite mostly not national-profile locked.
7. **Performance unproven at scale** — EXPLAIN fixture-only; GIN/index apply deferred; agencies N+1.
8. **Migration ledger residual** — analyze-report notes manual 058/059 on some upgrade paths.
9. **Soft 5433 CLI warning** — prefer hard refuse for default product runs while HC live (optional harden).
10. **STATUS/SUMMARY test-count drift** — undermines evidence hygiene until fixed.
11. **Ruff S608** on dynamic WHERE (fixed clause fragments + bound params) — hygiene before production exposure.
12. **No production merge / no DOD mark** — correctly non-claimed; must stay that way.

### What is **confirmed real** despite residuals

- Parallel isolation design (worktree/branch/DB/port/protected paths).
- Additive views-only migration 059.
- Dual non-contamination via **real** `compute_dual_coverage` + **real** `load_canonical_universe` (presence ≠ coverage; gate stays FAIL).
- Three fixture products with lineage + claim classes + limitations.
- Spec Kit 003 substantially complete for campaign architecture goals.

---

## Gate mapping (independent)

| Campaign gate | Independent call |
|---------------|------------------|
| PARALLEL_ISOLATION_PASS | **PASS** (design + proofs; HC not shown stopped by this work) |
| SPEC_KIT_PASS | **PASS** with FR-010/016 notes |
| BASELINE_INVENTORY_PASS | **PASS** (artifacts present; not re-audited every inventory line) |
| ARCHITECTURE_DECISION_PASS | **PASS** (ADR lean layers) |
| ISOLATED_IMPLEMENTATION_PASS | **PASS (fixture/5435)** |
| STRATEGIC_PRODUCTS_PASS | **PASS (fixture only)** |
| SC_COVERAGE_ISOLATION_PASS | **PASS** (real dual tests; matrix not 100% P0 complete) |
| Production / DOD / ≥95% SC | **NOT CLAIMED — must remain NOT PASS** |

---

## Required follow-ups before unconditional PASS or merge-to-main narrative

1. Fix `test_NV07` vacuous `or True`; implement **NV-05** or demote to P1 with explicit deferral in matrix.
2. Correct STATUS/SUMMARY test counts to **26 passed** (or re-run and paste fresh log).
3. ADR/spec amendment accepting `scripts.national_intel` vs FR-010, or thin-wrap under `contract_intel`.
4. Log FR-016 reuse as explicit tech debt with owner.
5. After HC completion: rebase, restore sample, re-EXPLAIN at realistic scale, re-run suite.
6. Do not mark DOD operational coverage from this campaign.

---

## Final one-liner

**CONDITIONAL_PASS:** architecture + fixture isolation + dual non-contamination are substantively real; production national intelligence and SC operational coverage remain **out of scope and unproven** — prior orchestrator self-check is superseded by this review.
