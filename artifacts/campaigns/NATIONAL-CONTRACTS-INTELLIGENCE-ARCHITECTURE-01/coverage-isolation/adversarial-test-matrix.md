# Adversarial Test Matrix — SC Coverage vs National Volume

**Campaign:** NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01  
**Subagent:** C — Metrology  
**As of:** 2026-07-22  
**Status:** P0 implemented in `tests/national_intel/test_adversarial_nv_matrix.py` (compute_dual_coverage real path)  
**Engine under test:** `scripts/coverage/dual_capability_coverage.py`  
**Universe:** seed-included set (target 1093)

---

## 0. Test design principles

1. **Prefer pure fixtures** (`compute_dual_coverage` with injected `observations_by_cap` / `presence_by_cap` / tiny synthetic `CanonicalUniverse`) over live HC DB.  
2. **Optional PG** only on isolated DSN (`extra_national_intelligence_test:5435` or ephemeral); **never** write to HC closure paths or PID of `run_contracts_90d_pilot`.  
3. **No vacuous asserts** (`or True`, empty mocks that force green).  
4. Capture both **measurement_success** and **coverage_pct** — isolation can hold while gate remains FAIL.  
5. Existing related unit coverage: `tests/test_dual_capability_coverage.py` (success_zero validators, never_checked, presence separation). This matrix **extends** with national-volume adversaries.

---

## 1. Matrix — national volume isolation

| ID | Hypothesis under attack | Setup | Action | Expected | Priority |
|----|-------------------------|-------|--------|----------|----------|
| **NV-01** | Millions of non-SC rows raise SC coverage | Tiny U with N=3 applicable, 0 covered evidence; inject presence set empty | Simulate presence load from R with 2_000_000 synthetic non-SC CNPJs (unmapped) | `covered_numerator` unchanged (0); `coverage_pct` unchanged; `data_presence_numerator` unchanged or unmapped status; **not** PASS gate | P0 |
| **NV-02** | Millions of non-SC rows raise SC **presence %** mislabeled as coverage | Same as NV-01; assert report JSON | Output must not put national COUNT in `coverage_pct`; `method=dual_capability_coverage`; limitations contain presence≠coverage | P0 |
| **NV-03** | Removing national non-SC rows lowers SC coverage | Baseline dual report with fixed observations O* and presence P* for U; add then remove non-SC rows | Recompute with same O* | `covered_numerator`, `coverage_pct`, A_C identical before/after | P0 |
| **NV-04** | National rows for SC CNPJ inflate **coverage** without evidence | Entity e∈A_C has contracts in table but **no** coverage_evidence | Presence may true; `covered=false`; state `never_checked` or pending | P0 |
| **NV-05** | National rows with SC-matching CNPJ8 + ambiguous multi-entity root | Two seed entities same CNPJ8; contracts only by CNPJ8 | Must not first-wins cover both; identity unresolved or single resolved only; never silent double cover | P0 |
| **NV-06** | Outsider evidence from national organ DB id | Evidence row entity_id maps outside U | `DualCoverageError` / measurement_success=false | P0 |
| **NV-07** | Bulk national ingest updates `entity_coverage.is_covered` | Legacy flag true for many entities; dual observations empty | Dual `coverage_pct` stays 0; legacy calculator may differ — prove dual ignores flag | P0 |
| **NV-08** | Gate confuses national volume progress with 95% | Report marketing fields | No path sets `coverage_gate_pass=true` from row count alone | P1 |

---

## 2. Matrix — success_zero evidence rigor

| ID | Hypothesis under attack | Setup | Expected | Priority |
|----|-------------------------|-------|----------|----------|
| **SZ-01** | Label alone covers | `state=success_zero`, missing pages + completion | `validate_success_zero` false; not covered | P0 |
| **SZ-02** | supports_zero_proof metadata alone | flag true, no pages/completion | reject (`missing_pagination_proof`) | P0 |
| **SZ-03** | Zero with fetched/persisted ≠ 0 | records_fetched=1 | reject | P0 |
| **SZ-04** | Zero with error token in message | “timeout” / 429 / 5xx | reject `error_signal:*` | P0 |
| **SZ-05** | Zero without run_id or timestamps | incomplete obs | reject | P0 |
| **SZ-06** | Zero without evidence_reference | — | reject | P0 |
| **SZ-07** | Contracts zero without query window | capability historical_contracts | reject `missing_query_window` | P0 |
| **SZ-08** | Contracts zero window < 3 years | window 1y | `contracts_backfill_ok` false → not covered | P0 |
| **SZ-09** | Valid zero + fresh + complete | full proof fixture | covered; `success_zero_count` +1; presence may false | P0 |
| **SZ-10** | Valid zero but **stale** | completed_at > SLA | not covered; bucket stale | P0 |
| **SZ-11** | Valid zero on complementary source only | required={pncp,ciga}; only complementary zero | not covered | P1 |

*SZ-01..06 already partially covered by unit tests; matrix requires regression lock under national campaign CI profile.*

---

## 3. Matrix — unqueried ≠ success_zero

| ID | Hypothesis under attack | Setup | Expected | Priority |
|----|-------------------------|-------|----------|----------|
| **UQ-01** | No observation row | applicable entity, required sources, empty obs map | `coverage_state=never_checked`; `covered=false`; `never_checked_count` includes entity | P0 |
| **UQ-02** | DB has national contracts but no evidence ledger | presence true, obs empty | never_checked; not success_zero | P0 |
| **UQ-03** | Pending / running state | state pending | not covered; not success_zero | P0 |
| **UQ-04** | not_investigated | legacy evidence_state | not covered (observation_counts_as_covered false) | P1 |
| **UQ-05** | Partition: all never_checked | A_C=N, zero obs | never_checked_count=N; covered=0; recon ok | P0 |
| **UQ-06** | Partial pagination empty | pages_processed < pages_expected, zero records | partial not success_zero | P0 |

---

## 4. Matrix — denominator & set equality

| ID | Hypothesis under attack | Setup | Expected | Priority |
|----|-------------------------|-------|----------|----------|
| **DE-01** | Hardcoded 1093 without seed | missing seed, no fixture | fail closed; no silent den | P0 |
| **DE-02** | expected_entity_count mismatch | seed included ≠ 1093 when expected set | DualCoverageError | P1 |
| **DE-03** | Numerator entity outside A_C | force covered id not applicable | DualCoverageError | P0 |
| **DE-04** | Result set ≠ U | missing entity in results | DualCoverageError incomplete | P0 |
| **DE-05** | Unknown applicability shrinks A_C without blocking gate | unknown>0 | gate FAIL/NOT_READY; measurement may true only if other recon ok — unknown blocks PASS | P0 |
| **DE-06** | Independent dens per capability | open_tenders A_C=3, historical A_C=2 | both reported; no average field | P0 |

---

## 5. Matrix — capability independence

| ID | Hypothesis under attack | Setup | Expected | Priority |
|----|-------------------------|-------|----------|----------|
| **CI-01** | Tender evidence covers contracts | only open_tenders success | historical never_checked/pending | P0 |
| **CI-02** | Contract presence covers tenders | only historical presence | open_tenders not covered | P0 |
| **CI-03** | Average gate | compute both | no `average_coverage` in summary | P0 |

---

## 6. Suggested pure-Python fixtures (no DB)

```text
U = {e1, e2, e3}  # all applicable via entity_applicability inject
as_of = fixed UTC

Case NV-01/03:
  observations_by_cap = {open_tenders: {}, historical_contracts: {}}
  presence_by_cap = {historical_contracts: set()}  # ignore national R
  assert covered_numerator == 0 for both
  re-run identical after "deleting R" → same report hashes for capability blocks

Case SZ-09:
  obs e1 pncp historical_contracts success_zero with full proof + 3y window + fresh
  required sources satisfied
  assert covered e1 historical; open_tenders still never_checked

Case UQ-01:
  applicable e1, no obs → never_checked
```

For **DB-level NV-01** (isolated only):

```sql
-- conceptual: insert bulk non-SC orgao_cnpj into pncp_supplier_contracts
-- freeze coverage_evidence for U
-- run compute_dual_coverage(dsn=isolated)
-- assert coverage_pct equal to pre-insert snapshot
-- DELETE non-SC batch
-- assert coverage_pct still equal
```

**Do not** run this against `extra_test` while HC backfill owns the table.

---

## 7. Acceptance criteria for SC_COVERAGE_ISOLATION_PASS

| # | Criterion |
|---|-----------|
| A1 | NV-01, NV-03, NV-04, SZ-01, SZ-09, UQ-01 documented with executable plan (this file) and, when implemented, green tests |
| A2 | Written invariants I1–I8 committed under `coverage-isolation/` |
| A3 | Engine map lists dual vs legacy calculator and presence path |
| A4 | Campaign STATUS continues to forbid “national volume ⇒ SC 95%” claims |
| A5 | No test mutates HC checkpoints or restarts protected containers |

Implementation of the matrix is a **follow-up story** after Spec Kit; this artifact is the contract for that story.

---

## 8. Traceability to existing tests

| Matrix ID | Existing test (if any) |
|-----------|------------------------|
| SZ-01..06 | `test_invalid_success_zero_missing_pagination`, `test_success_zero_rejects_*` |
| SZ-09 | `test_coverage_without_presence_via_success_zero` |
| UQ-01, UQ-05 | never_checked assertions in dual tests (~lines 221, 511–526) |
| CI / dens | `test_different_denominators_per_capability` (spec tasks) |
| DE / unknown | `test_obs_unknown_does_not_inflate_by_leaving_denominator` |
| NV-* | **gap** — national volume adversaries not yet specialized |

---

## 9. Non-goals

- Proving live SC coverage ≥95%  
- Re-running national 3y backfill  
- Changing dual engine formulas in this metrology wave  
- Touching `data/contracts_checkpoints/hc_closure_*`  
