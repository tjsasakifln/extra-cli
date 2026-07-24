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
- [x] Makefile gates (no || true; workspace+golden_path+full suite/CI evidence)
- [x] tests/test_live_consulting_pack.py

## Phase 4 — RC evidence
- [x] Restore completes; population SC eligible = 1_179_237 (FULL_ELIGIBLE_POPULATION)
- [x] `live_consulting_pack run` PASS reconcile (run `live-pack-20260724-162325-f4d6894d` on product tip `fa66dd7`)
- [x] monthly two-cycle proofs FULL_WINDOW 57238 (not silent 5000)
- [x] workspace CLI smoke (today/competitors/expiring/prices)
- [x] performance EXPLAIN sample + query_seconds under 60s
- [x] independent review findings PASS_TECHNICAL + skeptic-audit-10-gaps
- [x] user-acceptance BLOCKED_HUMAN (decision=null; agent_fill_in_forbidden; no auto-ACCEPT)
- [x] result.json terminal BLOCKED (BLOCKED_HUMAN + dual isolated residual)

## Phase 5 — Integration
- [x] Commit atomic; PR #130 open on campaign branch
- [ ] CI green on tip + post-merge isolated reproof (CI tip may re-run after docs commits)
- [ ] DOD sequential accept only with main+CI+evidence **and** verifiable Tiago ACCEPT

## Blocked (human / post-merge)
- Tiago inspects pack-rc and sets decision ACCEPT|REJECT|findings
- DevOps merge PR #130 after ACCEPT
- Dual operational ≥95% on isolated restore (currently GATE_FAIL_0% with empty coverage_evidence) OR keep non-claim
