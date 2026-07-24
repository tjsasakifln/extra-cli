# Tasks — 004 Extra Live Consulting Pack

## Phase 1 — Baseline
- [x] Worktree from origin/main; isolation DSN :5436
- [x] baseline.json classification
- [x] Verify dump SHA256; provision Postgres

## Phase 2 — Spec + schema
- [x] specs/004-*
- [x] Integrate national_intel; migration 060
- [x] Migrations apply on isolated DB

## Phase 3 — Product
- [x] live_consulting_pack orchestrator A–E
- [x] strategic_monthly_monitor --live-isolated
- [x] Makefile gates (no || true)
- [x] tests/test_live_consulting_pack.py

## Phase 4 — RC evidence
- [ ] Restore completes; population count matches export meta (or document delta)
- [ ] `live_consulting_pack run` PASS reconcile
- [ ] monthly two-cycle proofs
- [ ] workspace CLI smoke
- [ ] performance EXPLAIN sample
- [ ] independent review findings
- [ ] user-acceptance Tiago or BLOCKED_HUMAN
- [ ] result.json PASS|BLOCKED|FAIL

## Phase 5 — Integration
- [ ] Commit atomic; PR via @devops
- [ ] CI green; post-merge isolated reproof
- [ ] DOD sequential accept only with main+CI+evidence
