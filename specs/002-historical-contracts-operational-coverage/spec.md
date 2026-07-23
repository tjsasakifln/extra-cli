# Feature Specification: Historical Contracts Operational Coverage

**Feature Branch**: `campaign/historical-contracts-operational-closure-01`  
**Spec dir**: `specs/002-historical-contracts-operational-coverage`  
**Created**: 2026-07-22  
**Updated**: 2026-07-23  
**Status**: Active  
**Campaign**: `HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01`  
**Depends on**: `specs/001-dual-capability-coverage-truth/` (measurement spine — do not reopen without demonstrated failure)

## Input

Turn `historical_contracts` from correctly measured but operationally empty into a **proven operational consulting capability on the VPS Netcup host**: full source applicability, ≥3y backfill with checkpoint proof chain, single writer, safe cutover, ≤7d incremental, entity `coverage_evidence` without fabricated `success_zero`, dual gate ≥95%, weekly integration, systemd operation, backup/restore, observability, soak, and honest DOD acceptance.

## Scope (authoritative)

### In scope

- Completion of national PNCP contracts backfill (≥1 098 days, planned windows exact)
- Checkpoint/manifest proof chain; resume without reprocessing completed windows
- Single writer invariant (laptop **or** VPS, never both)
- Export / transfer / restore / cutover to **VPS Netcup RS 2000** (Debian 13, PostgreSQL 17)
- Incremental contracts update with freshness ≤168h
- Projection of nominal `coverage_evidence` from verified proof only
- Dual capability coverage for `historical_contracts` only
- systemd units/timers for contracts cycle, health, alerts, metrics, backup
- Reproducible host config (Ansible minimum per ADR-008)
- Consulting package generation from VPS lake
- Off-site backup + separate-DB restore drill
- Observability, soak (7 consecutive days), CI, independent review
- Honest sequential DOD acceptance for items this capability unlocks

### Non-goals

- Replacing ADR-030 / dual measurement method without failing test proof
- `open_tenders` ≥95% closure
- Claims: `LOCAL_READY`, `VPS_OPERATIONAL`, `PROJECT_DONE`
- Integrating PR draft #121 (national contracts intelligence) before migration renumber
- Value-paid semantics, physical works tracking, web dashboard
- Distributed architecture (K8s/Kafka/Redis)
- Reimage OS for preference alone

## Host of record (runtime)

| Field | Value |
|-------|--------|
| Provider | Netcup RS 2000 G12 |
| OS | Debian 13 (trixie) |
| PostgreSQL | 17 |
| RAM | 16 GB |
| App path | `/opt/extra-consultoria` |
| SSH | `ssh ec-prod` (port 2222) |
| Canonical remote | `tjsasakifln/extra-cli` |

Documentation (README, ADR-007/008, DEVELOPMENT) must converge to this host; pending/32 GB/Ubuntu 24.04/PG16 language is obsolete for the operational path.

## User Stories

### US1 — Applicability 100% (P0)

As an auditor, every included universe entity has a resolved applicability decision for `historical_contracts`.

**Acceptance**

1. `applicability_unknown_count=0` for historical_contracts.
2. Multi-sphere natures derive esfera with justification — never hardcoding entity_id→esfera.
3. `pncp+contracts` semantic roles documented.

### US2 — Entity evidence adapter with proof (P0)

As an operator, a completed crawl window set projects into nominal `coverage_evidence` **only** with checkpoint/manifest proof.

**Acceptance**

1. `success_with_data` when contracts exist for entity CNPJ8 in period.
2. `success_zero` **only** when checkpoint proof validates all planned windows complete and pagination integrity — **not** from `--window-complete --pages-processed 1 --pages-expected 1` alone.
3. Incomplete windows never write `success_zero`.

### US3 — Live pilots authorize expansion (P0)

Live 7d/90d pilots (not seal-only) authorize 3y expansion; artifacts under campaign path.

### US4 — Backfill ≥3 years + incremental ≤7d (P0)

Partitioned, resumable, idempotent national contracts collection; single writer; incremental with overlap; dual freshness SLA 168h.

### US5 — Cutover & VPS operation (P0)

Fail-closed export/restore (SHA256SUMS mandatory, abort on migration/truncate/count mismatch); VPS becomes sole contracts writer after cutover; timers healthy with venv.

### US6 — Weekly fail-closed + consulting product (P1)

`make extra-weekly` / `weekly_cycle --strict` does not exit 0 when contracts gate fails; package exposes contracts lists, rankings, freshness, claims/non-claims, provenance from **VPS data**.

### US7 — Backup, restore, observability, soak (P0)

Off-site backup with integrity; restore on separate DB; health/metrics/alerts; reboot + simulated failure recovery; 7 consecutive days with contracts SLA.

### US8 — Release & DOD (P0)

Integrated on `main` with green CI; independent review without open critical/high; DOD items ACCEPTED only with evidence + main + CI (one at a time).

## Measurable gates (candidate SHA)

```
source_applicability_resolution(historical_contracts) = 100%
capability_monitoring_coverage(historical_contracts) >= 95%
historical_contracts_backfill_window >= 1098 days
historical_contracts_planned_windows_complete = all
historical_contracts_incomplete_as_complete = 0
single_writer = true
historical_contracts_incremental_age <= 168h
identity_unresolved_count = 0
applicability_unknown_count = 0
unmapped_evidence_count = 0
failed_windows = 0
freshness_unknown_in_numerator = 0
stale_in_numerator = 0
partial_in_numerator = 0
export_restore_sha256_verified = true
backup_offsite_integrity_ok = true
restore_separate_db_ok = true
systemd_required_units_not_failed = true
consulting_package_from_vps = true
soak_7d_contracts_sla = true
ci_green_on_candidate_sha = true
```

If dual honest coverage <95%: produce nominal gap list; fix operational causes; **never** fabricate coverage. Source impossibility → FAIL or BLOCKED_EXTERNAL with proof.

## Decision: separate Spec 002

Spec 001 stabilizes **measurement**. Spec 002 owns **operational fill + VPS cutover**. Dual engine changes only when measurement cannot bind real evidence without weakening gates.

## Traceability (living)

| Requirement | Task | Implementation | Test | Evidence / gate | DOD | State |
|-------------|------|----------------|------|-----------------|-----|-------|
| Applicability 100% | T1 | source_policy 2.1 + derive_esfera | test_source_policy_* | dual JSON | §2 dual precond | IMPLEMENTED |
| Entity evidence + proof | T2 | contracts_entity_evidence.py + mig 059 | test_contracts_entity_evidence (adversarial) | entity-projection.json | §9.3 | IMPLEMENTED (proof harden) |
| Pilot 90d | T3 | run_contracts_90d_pilot | live artifact | pilot/ | §9.1 | VERIFIED |
| Backfill 3y | T4 | pilot --days 1098/1099 + checkpoint | window tests + live | backfill/ | §2.2 §9.1 | OPEN (in progress ~28/37) |
| Single writer | T4b | ops discipline + cutover runbook | single-writer.json | cutover.json | §20 | OPEN |
| Incremental | T5 | run_contracts_incremental | recovery tests | incremental.json freshness.json | §2.2 | IMPLEMENTED |
| Weekly strict contracts | T6 | weekly_cycle compute_exit_code | test_weekly_cycle | weekly report | §12 | IMPLEMENTED |
| Export/restore fail-closed | T7 | export_backfill_for_vps.sh restore_backfill_on_vps.sh | bash -n + restore drill | migration.json | §20 §22 | IMPLEMENTED (code) / OPEN (drill) |
| systemd/runtime | T8 | deploy/systemd + validate_systemd | test_local_resilience | systemd.json | §21 §23 | IMPLEMENTED (repo) / OPEN (host) |
| Consulting product | T9 | weekly_cycle / reports | product fields tests | consulting-package/ | §34 | OPEN |
| Backup off-site | T10 | backup units + offsite | restore separate DB | backup.json restore.json | §22 | OPEN |
| Soak 7d | T11 | timers + monitor | soak.json | soak.json | §24 | OPEN |
| CI + review + DOD | T12 | gates + dod_controller | suite | result.json | sequential | OPEN |

## Migration collision

- This campaign: `059_coverage_evidence_canonical_entity_unique.sql` (precedence)
- PR #121: `059_national_contracts_intelligence_layers.sql` → renumber on rebase after merge; remain draft

## Claims / non-claims

**Authorized only after all gates:** `HISTORICAL_CONTRACTS_OPERATIONAL_COVERAGE_PASS` (campaign PASS)

**Forbidden until separate full gates:** `LOCAL_READY`, `VPS_OPERATIONAL`, `PROJECT_DONE`, `open_tenders≥95%`
