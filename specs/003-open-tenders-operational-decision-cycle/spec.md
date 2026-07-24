# Spec 003 — Open Tenders Operational Decision Cycle

**Campaign:** `OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01`  
**Status:** active  
**Base SHA at creation:** `3e04728e4277320454e5bf218cc008e5000b970f`  
**Authority:** `DOD.md` > ADR > code > handoff narrative

## Problem

Editais abertos are the central recurring decision capability. Dual coverage for
`open_tenders` was measured at 0% covered / many never-checked. The weekly cycle
exists but did not compose an aggregated snapshot or call reconciliation on the
canonical path. Deliverable E accepted fixtures. Freshness defaults (48h) conflicted
with DOD (≤24h).

## Goals

1. Single canonical weekly entry: `make extra-weekly` / `scripts.ops.weekly_cycle`.
2. Collect via `run_pncp_open_monitoring` (aggregated 1–19 modalities, one logical run).
3. Reconcile only complete aggregated runs (`SourceSnapshotReconciler`).
4. Snapshot integrity measurable and fail-closed.
5. Deliverable E from live DB; empty dataset cannot pass operational audit.
6. Profile PENDING critical capacity cannot yield `PARTICIPAR`/`GO`.
7. Editais freshness SLA = 24h (DOD prevails over CIGA doc 48h and weekly default 48h).
8. Campaign-specific gates without breaking HC `release-candidate` / `verify-production`.
9. systemd unit/timer for weekly cycle versioned in repo.

## Non-goals

- Reopen dual-coverage ADR-030 / specs/001.
- Reopen historical contracts operational closure soak as this campaign’s core.
- Invent a fifth PNCP pipeline.
- Invent client capacity values still PENDING elicitation.

## Acceptance (campaign gates)

| Gate | Criterion |
|------|-----------|
| G1 entry | `extra-weekly` is sole canonical operational weekly entry |
| G2 collect | Weekly collect uses `run_pncp_open_monitoring` (not orphan per-modalidade only) |
| G3 reconcile | Reconcile only when parent run completed + scope_complete |
| G4 sla | PNCP open-tenders freshness SLA in weekly path = 24h |
| G5 ciga | Policy `ciga_ckan.sla_hours` ≤ 24 for editais capability alignment |
| G6 deliverable-e | Live path exists; operational audit fails on EMPTY |
| G7 profile | PENDING critical capacity forces REVIEW (never GO) |
| G8 integrity | Snapshot integrity module measures and fails closed |
| G9 campaign-gate | `make campaign-gate-open-tenders` does not break HC targets |
| G10 unit | `extra-weekly.service` + `.timer` present under `deploy/systemd/` |

Operational PASS of the full campaign additionally requires live VPS soak, coverage ≥95%,
and DOD ACCEPTED evidence — tracked outside unit gates.
