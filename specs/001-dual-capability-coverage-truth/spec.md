# Feature Specification: Dual Capability Coverage Truth

**Feature Branch**: `campaign/dual-capability-coverage-truth`  
**Spec dir**: `specs/001-dual-capability-coverage-truth`  
**Created**: 2026-07-21  
**Status**: Active  
**Input**: Canonical dual operational-coverage metrics for `open_tenders` and `historical_contracts` with independent 95% gates, auditable set-equality denominators, separated data presence, freshness in numerator, validated `success_zero`, no `any_row` / undifferentiated `is_covered` as general coverage, golden-path integration, errata for legacy 214/1093=19.5791%, honest DOD path.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Measure dual coverage honestly (Priority: P1)

As an operator, I need separate, auditable operational-coverage percentages for open tenders and historical contracts so I never confuse presence, freshness, or a single legacy admin flag with “coverage”.

**Why this priority**: Without correct measurement, every 95% gate and commercial claim is unreliable.

**Independent Test**: Run dual-coverage reproof on fixtures or DB; assert two capability blocks with independent denominators/numerators/gates and no average field.

**Acceptance Scenarios**:

1. **Given** a canonical universe of N included entities, **When** dual coverage is calculated, **Then** each capability reports `applicable_denominator`, `covered_numerator`, `coverage_pct`, `gate_status` independently.
2. **Given** an entity with tender evidence only, **When** both capabilities are calculated, **Then** it may contribute to `open_tenders` coverage but never to `historical_contracts` coverage.
3. **Given** measurement succeeds with coverage below 95%, **When** gate evaluation runs, **Then** `measurement_success=true`, `coverage_gate_pass=false`, and required gate mode exits non-zero.

---

### User Story 2 — Fail closed on universe integrity (Priority: P1)

As an auditor, I need calculations to refuse silent wrong denominators or numerators outside the applicable set.

**Why this priority**: 214/1093-style ambiguity came from counting rows without set equality to the planilha.

**Independent Test**: Inject duplicate IDs, hash mismatch, numerator outside universe, num>den — all fail closed.

**Acceptance Scenarios**:

1. **Given** seed hash or ordered-ids hash diverges from stamped identity, **When** calculation runs, **Then** status is fail with explicit reason.
2. **Given** numerator entity IDs not in applicable set, **When** calculation runs, **Then** fail closed (no silent drop).
3. **Given** missing seed/spreadsheet, **When** calculation runs, **Then** fail closed (no hardcoded 1093-only path).

---

### User Story 3 — Operator gap lists (Priority: P2)

As a consultant, I need nominal per-entity gap reports with next actions per capability.

**Why this priority**: Correct low % is useless without an actionable list.

**Independent Test**: Produce JSON summary + CSV/JSON nominal gaps with required fields.

**Acceptance Scenarios**:

1. **Given** dual calculation complete, **When** reports are written, **Then** each gap row includes entity_id, capability, applicability, covered, coverage_state, sources, freshness, blocker, next_action, evidence_reference.
2. **Given** `success_zero` without pagination proof, **When** scored, **Then** entity is not covered and state is partial/unknown (not covered).

---

### User Story 4 — Golden path dual mode (Priority: P1)

As a developer, I need golden path (and an isolated dual-only mode) to compute both capabilities, ledger fields, and exit codes that distinguish measurement vs gate vs pipeline success.

**Why this priority**: DOD §12.1 “calcula cobertura” must not mean the legacy single metric.

**Independent Test**: CLI `--execute-dual-coverage-only` and full path step both emit dual blocks.

**Acceptance Scenarios**:

1. **Given** DB + seed available, **When** dual-only mode runs, **Then** ledger records both capabilities and structured outputs under `output/coverage/`.
2. **Given** legacy `entity_coverage.is_covered` alone, **When** dual engine runs, **Then** it is never used as the covered numerator for either capability.

---

### Edge Cases

- Entity with admin row in `entity_coverage` but no capability evidence → not covered.
- Valid `success_zero` + fresh → covered without data presence.
- Stale success → not covered; presence may still be true.
- `not_applicable` with justification → excluded from denominator; still visible in reports.
- `unknown` applicability → not in A_C denominator; counted in unknown; gate readiness fails if unresolved unknowns exist for required pairs when `--strict-applicability`.
- Complementary source success cannot replace required source.
- Average of the two coverage percentages is never computed or exported as a gate input.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST compute `capability_monitoring_coverage(open_tenders)` and `capability_monitoring_coverage(historical_contracts)` independently.
- **FR-002**: Universe MUST come exclusively from `load_canonical_universe()` / canonical spreadsheet; calculation MUST stamp count, seed_sha256, ordered canonical_ids_sha256, radius rule, as_of, git_sha, schema_version.
- **FR-003**: Denominator for capability C MUST be A_C = applicable entities only; not_applicable requires justification+evidence; unknown and blocked remain visible.
- **FR-004**: Covered numerator MUST require complete required source combination, validated state (`success_with_data` or validated `success_zero`), freshness within SLA, no blocker, persisted run proof, entity ID ∈ A_C.
- **FR-005**: Freshness SLAs: open_tenders ≤24h complete; historical_contracts ≥3y backfill window proof + ≤7d incremental; stale/unknown/partial never enter numerator.
- **FR-006**: `success_zero` MUST pass explicit validators (applicable, full period, pagination complete, no 403/429/5xx/timeout unresolved, no schema/partial error, persisted run_id + start/end + provenance, fresh, auditable).
- **FR-007**: System MUST compute descriptive `data_presence` per capability separately and MUST NOT label presence as coverage.
- **FR-008**: System MUST NOT use `entity_coverage.any_row` or undifferentiated `is_covered` as canonical coverage numerator.
- **FR-009**: System MUST NOT average or compensate across capabilities.
- **FR-010**: Golden path MUST record dual metrics, gates, limitations, blockers; dual-only CLI mode supports open_tenders | historical_contracts | both.
- **FR-011**: Fail-closed on duplicate entity, unresolved identity required for gate, hash divergence, unexpected denominator, numerator ID outside A_C, missing seed, version ambiguity, numerator > denominator.
- **FR-012**: Emit structured summary (JSON) and nominal gaps (JSON/CSV) with required field sets from the campaign contract.
- **FR-013**: Distinguish `measurement_success`, `coverage_gate_pass`, `pipeline_success` in outputs and exit codes.
- **FR-014**: Legacy claim 214/1093=19.5791% MUST be preserved historically with errata/supersession and removed as proof of canonical coverage.
- **FR-015**: DOD updates MUST only claim dual coverage measurement where evidence allows; never claim live 95% without live proof under this definition.

### Key Entities

- **CanonicalUniverse**: seed-derived included entity set with identity stamps.
- **ApplicabilityRecord**: entity_id × source × capability → applicable|not_applicable|unknown|blocked + justification + validated_at + evidence_reference.
- **CapabilityCoverageSummary**: per-capability aggregates and gate result.
- **EntityCoverageRow**: per-entity nominal status for gap reports.
- **LegacyEntityCoverageMetric**: non-canonical historical `is_covered` count for errata only.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Two independent coverage percentages are produced on every dual reproof run.
- **SC-002**: Unit tests prove no any_row path and no cross-capability average; adversarial cases fail closed.
- **SC-003**: Golden path dual mode records both gates and exits non-zero when a required gate fails while measurement can still succeed.
- **SC-004**: Errata artifact exists for 19.5791% and active claims scan finds no undifferentiated use of that number as canonical dual coverage.
- **SC-005**: `NEXT-DOD-PATH.md` lists proven dual metrics (even if low) and critical next operational actions.

## Assumptions

- Minimal required source combination defaults to PNCP for both capabilities unless registry overrides; complementary sources never silent-replace required ones.
- Default entity-level applicability for both capabilities is `applicable` for included radius entities; explicit not_applicable must carry evidence.
- Capability names in evidence may also appear as `notices_or_bids` / `contracts` (freshness spine); dual engine maps those aliases to `open_tenders` / `historical_contracts`.
- Live 95% is out of scope for declaring campaign success; correct measurement is the goal.
