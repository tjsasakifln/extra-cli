# SC Coverage Isolation Invariants

**Campaign:** NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01  
**Subagent:** C — Metrology  
**As of:** 2026-07-22  
**Purpose:** Invariants that **national** `pncp_supplier_contracts` volume must **not** inflate SC operational coverage.

---

## I0 — Scope of “SC coverage”

**SC operational coverage** means dual capability monitoring coverage over the **canonical target universe** (seed-included entities within 200 km of Florianópolis; historical size **1093** when seed matches):

- `capability_monitoring_coverage(open_tenders)`
- `capability_monitoring_coverage(historical_contracts)`

computed by `scripts/coverage/dual_capability_coverage.py` only.

It does **not** mean:

- national row volume in `pncp_supplier_contracts`
- commercial signal / opportunity counts
- legacy `entity_coverage.is_covered`
- multi-source session percentages with other denominators
- line-coverage pytest metrics

---

## I1 — Universe membership is seed-only

| Rule | Statement |
|------|-----------|
| I1.1 | Membership in U comes **only** from `load_canonical_universe()` (spreadsheet sheet `Entes Públicos SC`). |
| I1.2 | `sc_public_entities.raio_200km` is diagnostic, never the DoD denominator. |
| I1.3 | National organs without seed inclusion are **outside U**. |
| I1.4 | Soft FKs (migration 055) allow national upserts without SC parent; they must **not** expand U. |
| I1.5 | `entity_count` stamp must match `\|included\|`; optional `expected_entity_count=1093` fails closed on mismatch. |

**Source of truth chain:**

1. Private seed: `Extra - alvos de licitação. R-0.xlsx` (or `EXTRA_TARGET_SPREADSHEET`)  
2. Public fixture: `fixtures/canonical_universe_r0.xlsx`  
3. Derived export: `config/target_entities_200km.csv` (registry/build tools; not superior to seed)  
4. Constant `CANONICAL_UNIVERSE = 1093` = historical stamp only  

---

## I2 — Denominator isolation

| Rule | Statement |
|------|-----------|
| I2.1 | Gate denominator is **A_C** (applicable subset of U), not national entity count. |
| I2.2 | Inserting millions of non-SC contract rows must not change `\|U\|` or `\|A_C\|`. |
| I2.3 | Deleting non-SC rows must not change `\|U\|` or `\|A_C\|`. |
| I2.4 | Shrinking denominator to inflate % is forbidden (`coverage_contract`: never shrink denom). |
| I2.5 | `not_applicable` / `unknown` / `blocked` never pad the covered numerator; unknown/blocked block gate PASS. |

---

## I3 — Numerator isolation (evidence-only)

| Rule | Statement |
|------|-----------|
| I3.1 | Covered numerator counts **entities in A_C** with validated fresh evidence for **all** required sources — not contract row counts. |
| I3.2 | `COUNT(*)` / GB size of `pncp_supplier_contracts` is **not** an input to `coverage_pct`. |
| I3.3 | Rows that do not map to a canonical entity_id ∈ U contribute 0 to covered numerator. |
| I3.4 | Mapped national-identity collisions that resolve to e ∈ U may set **data_presence** only; presence ≠ covered. |
| I3.5 | Cross-capability compensation forbidden: open_tenders success never fills historical_contracts numerator (and vice versa). |
| I3.6 | Average of the two capability % must never be computed as a gate. |
| I3.7 | Complementary sources never replace required combinations. |

---

## I4 — Presence vs coverage

| Rule | Statement |
|------|-----------|
| I4.1 | `load_data_presence` for historical_contracts may scan `pncp_supplier_contracts` (or aliases) for DISTINCT entity keys. |
| I4.2 | Presence is labeled `data_presence_*` only — never “coverage”. |
| I4.3 | Engine limitations always include: *“Presence is descriptive and is never coverage.”* |
| I4.4 | Unmapped national keys increase `unmapped_count` / may fail measurement completeness; they do **not** increase covered_numerator. |
| I4.5 | Valid `success_zero` can cover with `has_data_presence=false`. |

---

## I5 — success_zero discipline

| Rule | Statement |
|------|-----------|
| I5.1 | Label `success_zero` without validator pass **does not cover**. |
| I5.2 | Required: applicable, run_id, timestamps, evidence_reference, zero records, no error tokens, pagination/completion proof, provenance. |
| I5.3 | historical_contracts also requires query window + ≥3y backfill + freshness of window end. |
| I5.4 | Missing / unqueried entity ⇒ `never_checked` (or pending), **never** auto-`success_zero`. |
| I5.5 | HTTP/empty without proof ⇒ partial/error, not success_zero. |

---

## I6 — Freshness and stale

| Rule | Statement |
|------|-----------|
| I6.1 | Stale or unknown freshness excludes observation from covered numerator. |
| I6.2 | open_tenders SLA 24h; historical_contracts SLA 7d (plus backfill window). |
| I6.3 | National bulk ingest timestamps do not refresh SC entity coverage without entity-scoped evidence rows. |

---

## I7 — Fail-closed integrity

| Rule | Statement |
|------|-----------|
| I7.1 | Evidence entity outside U ⇒ `DualCoverageError` (outsider). |
| I7.2 | Unmapped evidence ⇒ fail closed (cannot drop silently). |
| I7.3 | Numerator ID ∉ A_C ⇒ fail closed. |
| I7.4 | num > den ⇒ fail closed. |
| I7.5 | Draft/missing source policy ⇒ `measurement_success=false`, `dual_gate_status=NOT_READY`, no valid denominator. |
| I7.6 | Identity ambiguity (CNPJ8 first-wins) forbidden; unresolved identity blocks gate. |

---

## I8 — National volume claims (campaign non-claims)

Aligned with campaign `STATUS.md`:

| Claim type | Allowed? |
|------------|----------|
| “We ingested N million national contracts” | Yes (ingestion progress) |
| “SC operational coverage is X% because N is large” | **No** |
| “SC coverage ≥95%” without dual evidence reproof | **No** |
| “National volume isolation preserved SC dual metrics” | Yes **if** adversarial matrix holds |

---

## I9 — Partition equalities (must hold every reproof)

For each capability C:

```text
|U| = applicable_den + not_applicable + applicability_unknown + applicability_blocked

|A_C| = covered + pending + never_checked + stale + partial + error + source_blocked
        (mutual-exclusive bucket sum)

covered_numerator = success_with_data_count + success_zero_count
                    (both counted among covered only)
```

Violation ⇒ `reconciliation_ok=false` ⇒ measurement/gate fail path.

---

## I10 — Implementation surface that must respect invariants

| Surface | Must obey |
|---------|-----------|
| National architecture / products on isolated DB | I1–I4 |
| Additive schema for national intelligence | I1.3–I1.4, I3 |
| Future crawl of national windows | I3, I5, I6 — write `coverage_evidence` only for scoped entity×capability runs with proof |
| Reporting / dashboards | Never plot national COUNT(*) as SC coverage % |
| Golden path / DoD | Only dual method + evidence packs |

---

## Proof sketch (national volume orthogonality)

Let `R` = set of rows in `pncp_supplier_contracts`.

Define projection:

```text
P(R) = { canonical_entity_id(r) | r ∈ R ∧ map(r) ∈ U }
```

Then:

```text
data_presence_numerator ⊆ A_C ∩ P(R)     # descriptive
covered_numerator ⊆ A_C ∩ ValidEvidence  # independent of |R|

∂ coverage_pct / ∂ |R \ mapped_to_U| = 0
∂ |U| / ∂ |R| = 0
```

Any code path where `∂ coverage_pct / ∂ |R_national| ≠ 0` is a **defect**.

---

## References

- `scripts/coverage/dual_capability_coverage.py`  
- `scripts/lib/universe.py`  
- `scripts/coverage/states.py`  
- `scripts/coverage/coverage_contract.py`  
- `specs/001-dual-capability-coverage-truth/spec.md`  
- `db/migrations/055_drop_orgao_entity_fk_national_pncp.sql`  
- `db/migrations/058_dual_capability_coverage_views.sql`  
