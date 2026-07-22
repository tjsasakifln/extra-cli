# Coverage invariants — dual capability, success states, universe

**Campaign:** NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01  
**Authorities:** ADR-030, `scripts/coverage/dual_capability_coverage.py`, `scripts/coverage/states.py`, `scripts/lib/universe.py`, DOD dual 95% sections  
**Base:** `origin/main` @ `a38981b`

---

## 1. Dual capabilities (no compensation)

| Capability | Primary data | Default required source | Freshness SLA |
|------------|--------------|-------------------------|---------------|
| `open_tenders` | Bids / opportunities (`pncp_raw_bids`, etc.) | `pncp` | 24 hours |
| `historical_contracts` | Contracts (`pncp_supplier_contracts`) | `pncp` | 7 days (168h) |

Aliases (normalize to above):

- open: `notices_or_bids`, `bids`, `editais`
- contracts: `contracts`, `contratos`, `historical_contracts`

**Forbidden:** average of the two percentages; using open-tender health as contract coverage or vice versa.

```
capability_monitoring_coverage(C) =
  |{ e ∈ A_C : required sources complete, validated success, fresh, no blocker }|
  / |A_C|
```

- `A_C` = applicable denominator for capability C  
- Gate threshold: **0.95** (`GATE_THRESHOLD`)  
- Adapter version stamp: `dual_capability_coverage/1.2.0`

---

## 2. Universe identity (denominator authority)

| Rule | Detail |
|------|--------|
| Authority | Seed spreadsheet via `load_canonical_universe` |
| Paths | Private `Extra - alvos de licitação. R-0.xlsx` or public `fixtures/canonical_universe_r0.xlsx` (env `EXTRA_TARGET_SPREADSHEET` / `TARGET_SPREADSHEET_PATH`) |
| Radius | 200 km of Florianópolis; seed flag SIM/NAO or distance fallback |
| Historical constant | `CANONICAL_UNIVERSE = 1093` — **back-compat only**; new code must use loader |
| DOD evidence | Denominator fixed at **1.093 entities** with set-equality stamps |
| Identity stamps | `entity_count`, `seed_path`, `seed_sha256`, `canonical_ids_sha256` (ordered IDs), radius metadata, git_sha, schema_version |
| Fail-closed | Set integrity violations → `DualCoverageError` / `measurement_success=false` |
| Non-authority | DB `sc_public_entities.raio_200km` alone is **diagnostic**, not dual denominator |

---

## 3. Applicability

| Status | Meaning |
|--------|---------|
| `applicable` | Source required for entity×capability; enters denominator when role is required |
| `not_applicable` | Terminal for that pair; not in numerator/denominator as covered need |
| `unknown` | Fail-closed pressure; inflates unknown counts; does not inflate coverage |
| `blocked` | Blocker present |

Source policy: `config/source_applicability.yaml` via `source_policy` is **canonical**.  
`DEFAULT_REQUIRED_SOURCES` in dual module is a **non-canonical stub** for migrations/tests only — using it without explicit fallback mark ⇒ `measurement_success=false`.

---

## 4. Coverage state machine (`scripts/coverage/states.py`)

Nine states:

| State | Covered? | Notes |
|-------|----------|-------|
| `not_applicable` | No (terminal) | Never transitions out without external action |
| `pending` | No | Applicable, not yet verified |
| `running` | No | In flight |
| `success_with_data` | Yes* | *only if validation + freshness pass |
| `success_zero` | Yes* | *only if pagination/completion proof + validation |
| `partial` | No | Incomplete pagination/timeout |
| `error` | No | Connection/auth/parse/transform/persist |
| `blocked` | No | Credential/dependency |
| `stale` | No | Was success; SLA expired |

`COVERED_STATES` at state-machine level = `{success_with_data, success_zero}` — dual engine **further restricts** with validators + freshness + contracts window.

DB enum `evidence_state` also includes granular failure subtypes: `connection_failed`, `auth_failed`, `parse_failed`, `transform_failed`, `persist_failed`, `not_investigated`, `success` (legacy), etc.

---

## 5. What counts as covered (`observation_counts_as_covered`)

An observation counts only if:

1. State is not blocked/partial/error/stale/pending/never_checked  
2. **Freshness OK** for capability SLA (`is_fresh_observation`)  
   - Explicit `stale|unknown|overdue|never|incomplete` ⇒ not fresh  
   - Else age(`completed_at`) ≤ SLA hours  
3. If `success_zero` → `validate_success_zero` OK  
4. If `success_with_data` → `validate_success_with_data` OK  
5. If capability is `historical_contracts` → `contracts_backfill_ok`  
   - Requires `queried_start` / `queried_end`  
   - Span ≥ **`MIN_CONTRACT_BACKFILL_YEARS` (3)**  
   - Window end still within contracts SLA of `as_of`

`stale`, `unknown` freshness, `partial`, unvalidated zeros, and incomplete windows **never** enter the numerator.

---

## 6. `success_zero` validation (strict)

All required:

| Check | Rule |
|-------|------|
| State | `success_zero` |
| Applicability | `applicable` |
| Identity | entity_id, source, capability, run_id present |
| Timestamps | started_at and completed_at present |
| Evidence ref | non-empty `evidence_reference` |
| Counts | records_fetched == 0 and records_persisted == 0 |
| Error tokens | no 403/429/5xx/timeout/schema/rate_limit/auth signals in error/metadata |
| Pagination proof | pages_processed ≥ pages_expected (>0), **or** completion_rule ∈ {http_204_complete, true, pagination_complete, complete} with provenance |
| Contracts | queried_start + queried_end required |

Incomplete pagination ⇒ not covered (partial-like).

---

## 7. `success_with_data` validation (strict)

| Check | Rule |
|-------|------|
| State | `success_with_data` |
| Applicability | `applicable` |
| Identity / timestamps / evidence | same class as zero |
| Records | fetched > 0 and persisted > 0 |
| Persist ≤ fetch | unless metadata `allow_persisted_gt_fetched` |
| Tenders | pagination or snapshot proof |
| Contracts | query window required (+ 3y rule at cover time) |

---

## 8. Data presence vs coverage

| Concept | Role |
|---------|------|
| `data_presence` | Descriptive: rows exist for entity mapping |
| Statuses | measured_rows_present, measured_no_rows, table_absent, identity_unresolved, … |
| Labeling | **Must not** be sold as `capability_monitoring_coverage` |

Reported alongside dual report (`data_presence_numerator`, `data_presence_pct`) but independent of gate numerator.

---

## 9. Three success flags (do not conflate)

| Flag | Meaning |
|------|---------|
| `measurement_success` | Engine ran; identity OK; no silent fail-open schema errors |
| `coverage_gate_pass` | Both (or selected) capabilities ≥ 95% under dual definition |
| `pipeline_success` | Broader golden-path / pipeline outcome |

Empty evidence with valid universe → **0% covered**, `measurement_success` can still be true.

---

## 10. Forbidden methods / claims

From dual module `FORBIDDEN_METHODS` / `claims_forbidden`:

- `entity_coverage.any_row` as coverage  
- `entity_coverage.is_covered` as general / dual coverage  
- Averaging open_tenders + historical_contracts  
- Labeling data_presence as coverage  
- Legacy single metric **214/1093 = 19.5791%** as canonical dual coverage  
- Live 95% without dual-definition proof  
- Silent unmapped evidence counted as zeros that inflate coverage  
- Fail-open empty sets on schema/query errors  

Migration 058 re-comments `entity_coverage` as LEGACY/DIAGNOSTIC and adds `v_dual_capability_evidence_latest`.

---

## 11. Mapping / identity failure modes

- Evidence `entity_id` / CNPJ8 must map into canonical universe IDs.  
- Unmapped evidence: counted in `unmapped_evidence_count`; **must not** silently inflate coverage.  
- `identity_unresolved_count > 0` pressures measurement honesty / gate readiness.  
- Schema modes: modern / legacy / unknown compatibility handling in dual engine.

---

## 12. Operational evidence snapshots (DOD, historical — not re-proven here)

Documented in `DOD.md` (may lag live DB):

- Dual engine method acceptance with `dual_capability_coverage/1.2.0` + source_policy v2  
- Live dual gate often **FAIL** (not 95%) while measurement may succeed  
- success_zero probes for `historical_contracts` with `http_204_complete`  
- Freshness packs: editais vs contracts separate JSON under `output/coverage/`  
- Ops proxy style metrics (e.g. SZ counts) are **not** dual gate substitutes unless dual definition holds  

**This inventory does not re-run measurements or claim current live %.**

---

## 13. Implications for national contracts architecture

1. National row volume in `pncp_supplier_contracts` **≠** dual coverage.  
2. Coverage remains **entity-universe × evidence**, not “how many contracts downloaded”.  
3. 3-year window requirement means national backfill must leave **per-entity** evidence with full query windows + pagination proof, not only bulk inserts.  
4. SC product analytics (200 km views) can use lake joins; dual gates still use seed universe + evidence.  
5. Concurrent HC bulk load must not corrupt evidence semantics (run_id, windows, zero proof).
