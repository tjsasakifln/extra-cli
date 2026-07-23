# Implementation Plan — 002 Historical Contracts Operational Coverage

**Campaign**: HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01  
**Updated**: 2026-07-23

## Strategy

1. **Foundation on branch** (code + tests + Spec): proof-gated success_zero, fail-closed export/restore, systemd/venv/calendars, weekly contracts strict tests, Spec convergence — **before** final cutover.
2. **Finish or migrate backfill** with single writer (local PID until 37/37 or explicit cutover then VPS-only resume).
3. **Cutover**: stop local writer → export (SHA256) → restore fail-closed → validate counts → VPS sole writer.
4. **Project evidence** from verified checkpoint only → dual ≥95% or nominal gaps.
5. **Ops**: health/alerts/metrics/backup off-site → restore drill → reboot/failure simulation.
6. **Product + soak 7d** on VPS SHA.
7. **Release**: CI green → independent review → merge main → sequential DOD accept.

## Technical approach

- Pure proof validation (`load_checkpoint_window_proof`, `assert_success_zero_proof`) unit-tested without VPS.
- I/O paths (crawl, pg_dump, systemd) fail-closed with JSON results under `artifacts/campaigns/HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/`.
- Host config: minimal Ansible under `deploy/ansible/` re-applying units/timers idempotently (ADR-008).
- PR #121 isolated; migration 059 of this campaign wins.

## Risks

| Risk | Mitigation |
|------|------------|
| PNCP 422/503 partial windows | never seal incomplete; resume |
| Dual writers | timers off on VPS until cutover; kill local before restore |
| Off-site credentials missing | complete local backup + document BLOCKED_CREDENTIAL |
| Dual <95% after full backfill | nominal gaps; operational fix; no fabrications |
| Soak duration | persistent monitor; not a token/context blocker |

## Phases → tasks

See `tasks.md`. Gates: `make campaign-gate-historical-contracts-vps`, `make release-candidate`, `make verify-production` (wrappers to be added if missing).
