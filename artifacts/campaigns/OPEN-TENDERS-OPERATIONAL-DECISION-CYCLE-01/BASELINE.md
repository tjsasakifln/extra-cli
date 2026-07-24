# OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01 — Baseline

**Generated:** 2026-07-23 (inspection)  
**SHA:** `3e04728e4277320454e5bf218cc008e5000b970f` (`origin/main`)  
**Worktree:** `.worktrees/open-tenders-odc-01` (clean, isolated from dirty historical-contracts tree)  
**Machine artifact:** `baseline.json`

## Confirmed facts

| Area | State |
|------|--------|
| Dual open_tenders coverage | universe 1093, applicable 946, covered 0, unknown applicability 147, gate FAIL |
| DOD Controller | 1361 items, 25 ACCEPTED, next OPEN: *integridade do snapshot ativo 100%* |
| Weekly entry | `make extra-weekly` / `scripts.ops.weekly_cycle` exists |
| Aggregated PNCP path | `run_pncp_open_monitoring` + reconciler in `pncp_audit` |
| Weekly collect path | per-modalidade `PncpOpportunityCrawler` **without** parent reconcile |
| Deliverable E | fixture/audit path; empty report can pass audit |
| Profile Extra | critical capacity fields `PENDING` |
| CIGA SLA in policy | 48h (conflicts with DOD ≤24h for editais) |
| Weekly PNCP SLA default | 48h (conflicts with DOD) |
| systemd | no `extra-weekly` timer; concurrent PNCP units exist |
| HC campaign | advanced; release-candidate still HC-coupled |

## Largest gap

**Open tenders operational cycle is coverage-zero.** Historical contracts must not be reopened. This campaign converges the weekly path onto the existing aggregated monitoring + reconciler and proves live Deliverable E.

## Canonical path chosen

1. `make extra-weekly` → `python -m scripts.ops.weekly_cycle --strict`
2. Collect open tenders via `run_pncp_open_monitoring` (19 modalidades, one logical run)
3. Reconcile only complete aggregated runs via `SourceSnapshotReconciler`
4. Deliverable E from live `opportunity_intel` snapshot (fail-closed if empty)
5. Freshness SLA for editais: **24h** (DOD prevails over prior 48h defaults)

## Not treated as proof

Unit tests, fixtures, handoffs, PR merges, or presence of code alone.
