# Tasks — 002 Historical Contracts Operational Coverage

**Updated**: 2026-07-23 — reconciled with live STATUS/handoff (prior `[x]` without evidence corrected).

## Phase A — Baseline & Spec
- [x] T0 Baseline artifacts under `artifacts/campaigns/HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/` (baseline.json 2026-07-23 revalidated)
- [x] T0b Spec 002 skeleton
- [x] T0c Spec 002 expanded: VPS/cutover/soak/backup in scope + converge-report
- [ ] T0d Doc convergence: README, ADR-007/008, DEVELOPMENT, remote extra-cli

## Phase B — Applicability 100%
- [x] T1.1 derive_esfera for consórcio/SEM/EP/SSA
- [x] T1.2 policy 2.1.0 historical_contracts wildcard
- [x] T1.3 decide/select without inventing sphere when wildcard applies
- [x] T1.4 unit tests policy multi-nature + wildcard
- [ ] T1.5 dual reproof artifact: applicability_unknown_count=0 on **current** policy + lake (post-projection)

## Phase C — Evidence adapter
- [x] T2.1 migration 059 aggregate unique fix
- [x] T2.2 dual load via canonical_entity_key
- [x] T2.3 `scripts/coverage/contracts_entity_evidence.py`
- [x] T2.4 tests adapter + dual mapping
- [x] T2.5 forbid success_zero without checkpoint proof (adversarial tests)

## Phase D — Pilot 90d live
- [x] T3.1 audit pilot GO criteria
- [x] T3.2 live pilot execution
- [x] T3.3 GO/NO-GO artifact (go_no_go_3y=GO)

## Phase E — Backfill + single writer + incremental
- [x] T4.1 3y window plan + resume armed (37×30d / 1098–1099d)
- [ ] T4.2 live backfill to completion (checkpoint 28/37 in progress; PID writer local)
- [ ] T4.3 project evidence with **verified** checkpoint proof (not manual flags)
- [ ] T4.4 single-writer proof artifact
- [x] T5.1 incremental command + overlap
- [ ] T5.2 idempotency + interrupt/resume proofs on VPS writer

## Phase F — Cutover / export-restore
- [x] T6.0 export/restore scripts fail-closed (SHA256, truncate, migration, counts)
- [ ] T6.1 final export after local writer stop
- [ ] T6.2 restore on VPS + count match
- [ ] T6.3 cutover date + rollback path recorded

## Phase G — systemd / host
- [x] T7.1 units: venv, OnCalendar hourly, StartLimit in [Unit], OnFailure webhook guard
- [x] T7.2 validate_systemd detects real defects
- [ ] T7.3 apply units on host; required units not failed
- [ ] T7.4 minimal Ansible playbook (ADR-008)

## Phase H — Weekly + product + backup + soak
- [x] T8.1 weekly fail-closed contracts in strict mode (tests fixed)
- [ ] T8.2 consulting package from VPS lake
- [ ] T9.1 off-site backup + integrity
- [ ] T9.2 restore separate DB drill
- [ ] T9.3 reboot + simulated failure recovery
- [ ] T9.4 soak 7 consecutive days

## Phase I — Close
- [ ] T10 tests/CI/security/perf on candidate SHA
- [ ] T11 independent review
- [ ] T12 merge main
- [ ] T13 DOD honest sequential accept
- [ ] T14 final report PASS|BLOCKED|FAIL
