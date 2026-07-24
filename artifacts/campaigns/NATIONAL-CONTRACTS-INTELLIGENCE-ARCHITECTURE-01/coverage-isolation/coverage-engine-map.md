# Coverage Engine Map — Dual Capability + Calculator

**Campaign:** NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01  
**Subagent:** C — Metrology & SC Coverage Isolation  
**As of:** 2026-07-22  
**Scope:** Read-only reverse map of denominators, numerators, and state buckets. No production code changes.

---

## 1. Authority stack (what is canonical)

| Layer | Path | Role | Gate authority? |
|-------|------|------|-----------------|
| **Canonical dual engine** | `scripts/coverage/dual_capability_coverage.py` (`ADAPTER_VERSION=dual_capability_coverage/1.2.0`) | `capability_monitoring_coverage(open_tenders \| historical_contracts)` with fail-closed set equality | **YES** (method of record for DoD dual gates) |
| **Universe authority** | `scripts/lib/universe.py` → `load_canonical_universe()` | Included set from seed spreadsheet sheet `Entes Públicos SC` | Membership + count stamp |
| **Source policy** | `config/source_applicability.yaml` via `scripts/coverage/source_policy.py` | Required source combinations; `status=active` + hash required for live measurement | Denominator formation blocked if not ready |
| **Evidence ledger** | `coverage_evidence` (+ view `v_dual_capability_evidence_latest` migration 058) | Latest observation per entity×source×capability | Numerator inputs only when validated |
| **States domain** | `scripts/coverage/states.py` | 9-state machine + `COVERED_STATES` = `{success_with_data, success_zero}` | Domain vocabulary |
| **Coverage contract catalog** | `scripts/coverage/coverage_contract.py` | Metric IDs; fixed historical denom stamp 1093 when seed matches | Catalog / session metrics (not dual spine) |
| **Legacy calculator** | `scripts/coverage/calculator.py` | `entity_coverage.is_covered` report | **NO** — forbidden as dual coverage |
| **Legacy readiness/truth** | `scripts/consulting_readiness.py`, `scripts/coverage_truth.py` | Older aggregated monitoring formulas | Superseded for dual gates; historical only |

**Forbidden as coverage methods** (engine constant `FORBIDDEN_METHODS`):

- `entity_coverage.any_row`
- `entity_coverage.is_covered`
- `any_row`
- `is_covered_undifferentiated`

Migration 058 comments table `entity_coverage` as LEGACY/DIAGNOSTIC only.

---

## 2. Dual pipeline (compute path)

```
seed spreadsheet (R-0 / fixture)
        │
        ▼
load_canonical_universe()  →  CanonicalUniverse.included  (target ~1093)
        │
        ▼
build_universe_identity()  →  count, seed_sha256, ordered ids sha, universe_version
        │
        ├─► load_source_policy(active)  ──fail→ SOURCE_POLICY_NOT_READY / dual_gate NOT_READY
        │
        ├─► build_applicability_resolutions(entity × required sources × capability)
        │         applicable | not_applicable | unknown | blocked
        │
        ├─► load evidence (DB) or inject observations_by_cap (pure tests)
        │         map DB entity_id → canonical entity_id
        │         unmapped/outsider evidence → DualCoverageError (fail closed)
        │
        ├─► load_data_presence (DB)  — DESCRIPTIVE ONLY
        │         pncp_raw_bids (open_tenders) / pncp_supplier_contracts|contracts (historical)
        │         map rows → universe entity_ids; never labels "coverage"
        │
        ├─► score_entity_capability() per included entity × capability
        │         observation_counts_as_covered() + freshness SLA
        │
        └─► aggregate_capability() per capability
                  applicable_denominator | covered_numerator | buckets | gate
```

Entry: `compute_dual_coverage(...)`. CLI/golden path emit dual capability blocks under `output/coverage/`.

---

## 3. Denominators

### 3.1 Universe count (stamp, not always A_C)

| Symbol | Definition | Source |
|--------|------------|--------|
| `U` / `universe_count` | `\|universe.included\|` = seed rows with `Raio 200km?` = SIM (or distance ≤ 200 km fallback) | `load_canonical_universe` → `build_universe_identity.entity_count` |
| Historical fixed stamp | `CANONICAL_UNIVERSE = 1093` / `FIXED_CANONICAL_DENOMINATOR = 1093` | **Compatibility only**; new code must derive from seed |

**Not denominators:**

- `sc_public_entities.raio_200km` (diagnostic)
- Row counts in `pncp_supplier_contracts` / national volume
- Outside-radius seed rows (`within_radius=False`)
- Unresolved radius rows (not in `included`; may appear in conservative monitoring populations elsewhere)

### 3.2 Applicable denominator A_C (gate denominator)

```text
applicable_denominator = |{ e ∈ U | applicability(e, C) == "applicable" }|
```

| Applicability | In A_C? | Effect |
|---------------|---------|--------|
| `applicable` | **Yes** | Eligible for covered/pending/stale/… buckets |
| `not_applicable` | No | `not_applicable_count`; still listed in report |
| `unknown` | No | `applicability_unknown_count`; **blocks gate PASS** if > 0 |
| `blocked` | No | `applicability_blocked_count`; **blocks gate PASS** if > 0 |

**Invariant:**  
`applicable + not_applicable + unknown + blocked == universe_count`  
(reconciliation error if violated).

**Important:** Membership in U does **not** imply applicable. Missing esfera / unresolved policy ⇒ `unknown`, never silent applicable (FR-028).

### 3.3 Data presence denominator (descriptive)

When measurable:

```text
data_presence_pct = data_presence_numerator / applicable_denominator
```

Presence is **never** labeled coverage. Non-measurable presence (`table_absent`, `column_absent`, `query_failed`, `identity_unresolved`, `fully_unmapped`, `not_evaluated` in fail path) ⇒ `data_presence_pct=null`, `measurement_success=false`.

---

## 4. Numerators

### 4.1 Covered numerator (operational coverage)

```text
covered_numerator = |{ e ∈ A_C | covered(e, C) == true }|
coverage_pct      = 100 * covered_numerator / applicable_denominator   (0 if den=0)
```

Entity `covered` only when **all** required sources for capability C succeed:

```text
covered ⇔
  applicability == applicable
  ∧ required_sources non-empty
  ∧ every required source has observation that observation_counts_as_covered(...)
  ∧ missing_sources empty
```

`observation_counts_as_covered` requires:

1. State not in `{blocked, partial, error, stale, pending, not_investigated, never_checked}`
2. Freshness within SLA (`is_fresh_observation`)
3. Either validated `success_zero` **or** validated `success_with_data`
4. For `historical_contracts`: `contracts_backfill_ok` (≥ 3 years window + end within contracts SLA)

**SLAs** (`SLA_HOURS`):

| Capability | Freshness SLA | Extra window rule |
|------------|---------------|-------------------|
| `open_tenders` | 24 h | Pagination / snapshot proof on success states |
| `historical_contracts` | 7×24 h | `MIN_CONTRACT_BACKFILL_YEARS = 3` on queried_start/end |

**Gate PASS** additionally requires:

- `covered_numerator / applicable_denominator >= 0.95`
- `applicable_denominator > 0`
- zero applicability unknown & blocked
- zero unmapped evidence
- zero identity unresolved
- reconciliation OK
- presence measurement complete (when DB path)

---

## 5. State buckets (definitions)

### 5.1 Evidence / observation states (ledger)

| State | Meaning for numerators |
|-------|------------------------|
| `success_with_data` | Candidate for cover **if** `validate_success_with_data` + fresh |
| `success_zero` | Candidate for cover **if** `validate_success_zero` + fresh (+ contracts window) |
| `partial` | Not covered |
| `error` (+ subtypes) | Not covered |
| `blocked` | Not covered |
| `pending` / `running` | Not covered |
| `stale` | Not covered (even if previously success) |
| `not_applicable` | Outside A_C when entity-level |

### 5.2 Validators (hard requirements)

**`validate_success_zero`** (`dual_capability_coverage.py`):

- state == success_zero  
- applicability == applicable  
- entity_id, source, capability, run_id present  
- started_at & completed_at present  
- evidence_reference present  
- records_fetched == 0 and records_persisted == 0  
- no error tokens (403/429/5xx/timeout/schema/partial/auth/…)  
- pagination proof: pages_processed ≥ pages_expected **or** completion_rule + provenance  
- historical_contracts: queried_start & queried_end required  

**`validate_success_with_data`:**

- state == success_with_data  
- same identity/run/timestamp/reference rigor  
- records_fetched > 0 and records_persisted > 0  
- persisted ≤ fetched unless `allow_persisted_gt_fetched`  
- pagination/snapshot proof for open_tenders  
- query window for historical_contracts  

Invalid labeled success states fold to **partial/error** — **not covered**.

### 5.3 Aggregate buckets on applicable set (mutually exclusive)

From `_mutual_exclusive_bucket` over A_C:

| Bucket field | When |
|--------------|------|
| `covered` → feeds `covered_numerator` | `r.covered` |
| `stale_count` | stale state or freshness_status stale |
| `partial_count` | partial / invalid success folds |
| `error_count` | error |
| `blocked_count` / `source_blocked_count` | blocked among applicable |
| `never_checked_count` | no evidence for required sources (`never_checked`) |
| `pending_count` | residual action-needed without never_checked exclusive |
| `success_zero_count` | **among covered only** with coverage_state success_zero |
| `success_with_data_count` | **among covered only** with coverage_state success_with_data |
| `unknown_count` / `applicability_unknown_count` | entities **outside** A_C with applicability unknown |

**Entity fold when no observations for required sources:**

```text
coverage_state = never_checked
next_action = run_required_sources
covered = false
```

**Unqueried entity ≠ success_zero** (critical isolation rule).

### 5.4 Data presence statuses (not coverage)

`measured_rows_present | measured_no_rows | table_absent | column_absent | query_failed | identity_unresolved | partially_unmapped | fully_unmapped | not_evaluated` (+ legacy aliases `no_rows`/`rows_present`/`unmapped_rows`).

---

## 6. Identity mapping

- Canonical `entity_id` = `extra-{sha256(identity_key)[:20]}` from seed  
- DB `sc_public_entities.id` mapped multi-key (CNPJ14 / identity_key / unique CNPJ8) — **no first-wins on ambiguous CNPJ8**  
- Evidence with unmapped DB entity_id → fail closed (`unmapped_evidence_count`)  
- Evidence mapping to entity outside U → fail closed (`outsider_evidence_count`)  

---

## 7. Legacy calculator (`scripts/coverage/calculator.py`)

```sql
-- conceptual
COUNT(DISTINCT e.id) total
COUNT(DISTINCT CASE WHEN ec.is_covered THEN e.id END) covered
FROM sc_public_entities e
LEFT JOIN entity_coverage ec ...
WHERE e.is_active
GROUP BY e.raio_200km
```

| Aspect | Dual engine | Legacy calculator |
|--------|-------------|-------------------|
| Denominator | Seed included / A_C | Active DB rows × raio flag |
| Numerator | Validated evidence + freshness + required combo | `is_covered` flag |
| Capabilities | Split open_tenders / historical_contracts | Undifferentiated |
| National contracts volume | Presence only; not numerator | Not consulted |
| Status | **Canonical for 95% gates** | Diagnostic / forbidden |

---

## 8. National contracts volume touchpoints

| Table / artifact | Used by dual engine? | How |
|------------------|----------------------|-----|
| `pncp_supplier_contracts` | Yes, **presence only** | `load_data_presence` for historical_contracts; DISTINCT entity keys mapped into U |
| `pncp_raw_bids` | Yes, **presence only** | open_tenders presence |
| `coverage_evidence` | Yes, **coverage numerator** | Must map into U; capability-scoped |
| National row count (millions) | **Never** | No formula uses `COUNT(*)` of national rows as coverage % |

Migration **055** dropped hard FKs so national organs can land without SC parent — soft join only. That enables volume without forcing universe membership.

---

## 9. Spec / DoD anchors

- Spec: `specs/001-dual-capability-coverage-truth/spec.md` (FR-001…FR-032)  
- Formulas baseline (pre-dual gaps): `docs/baseline/c2-coverage-formulas.md`  
- Domain: spreadsheet sole membership authority; DB radius never denominator  

---

## 10. Quick formula card (copy for audits)

```text
U  = included(seed, raio 200 km)                    # target 1093 when seed matches
A_C = {e ∈ U | appl(e,C)=applicable}
N_C = {e ∈ A_C | all required sources validated success_* ∧ fresh ∧ window_ok}
coverage_pct(C) = |N_C| / |A_C|                     # independent per C
data_presence(C) = |{e ∈ A_C | has rows}| / |A_C|   # descriptive
gate(C) = coverage_pct>=0.95 ∧ unknown=0 ∧ blocked=0 ∧ recon_ok ∧ presence_measurable ∧ identity_ok
```

**Never:**

```text
coverage_pct ≠ COUNT(pncp_supplier_contracts) / anything
coverage_pct ≠ AVG(open_tenders, historical_contracts)
coverage_pct ≠ entity_coverage.is_covered rate as dual gate
success_zero ≠ missing evidence
```
