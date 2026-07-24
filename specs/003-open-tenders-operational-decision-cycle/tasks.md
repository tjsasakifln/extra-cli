# Tasks 003 — Open Tenders ODC

## Done

- [x] T01 Baseline inspection + baseline.json
- [x] T02 Spec skeleton
- [x] T03 weekly_cycle → run_pncp_open_monitoring
- [x] T04 SLA 24h weekly + CIGA policy
- [x] T05 Deliverable E live + PENDING degradation + empty fail-closed
- [x] T06 snapshot_integrity module
- [x] T07 extra-weekly systemd units
- [x] T08 campaign-gate-open-tenders (+ operational alias)
- [x] T09 Fix coverage_evidence ON CONFLICT for canonical keys
- [x] T10 release-candidate-open-tenders script + Makefile
- [x] T11 verify-open-tenders-production script + Makefile

## In progress / remaining

- [ ] T12 Push branch + PR + CI green
- [ ] T13 Full PNCP collect scope_complete on real DB
- [ ] T14 Regenerate dual-coverage / freshness / applicability (≥95%, 0 unknown)
- [ ] T15 Deploy extra-weekly.timer on VPS
- [ ] T16 Soak evidence ≥7d
- [ ] T17 DOD ACCEPTED only with main+CI+evidence

## Traceability

| Task | FR | Test | Evidence | DOD theme |
|------|----|------|----------|-----------|
| T03–T04 | collect+freshness | test_weekly_cycle | campaign-gate, RC | freshness ≤24h |
| T05 | Entregável E | test_deliverable_e | deliverable_e.json | Entregável E |
| T06 | snapshot 100% | test_open_tenders | snapshot-integrity.json | integridade snapshot |
| T10–T11 | gates | makefile targets | release-candidate.json, verify-production.json | VPS/recurrence |
