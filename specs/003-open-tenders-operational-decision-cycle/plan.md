# Plan 003 — Open Tenders Operational Decision Cycle

## Architecture

```
make extra-weekly
  → scripts.ops.weekly_cycle --strict
    → freshness (SLA 24h editais)
    → collect: run_pncp_open_monitoring (modalidades 1–19, one run)
         → persist opportunity_intel
         → project coverage_evidence (canonical key ON CONFLICT)
         → SourceSnapshotReconciler only if completed+scope_complete
    → process / quality / intelligence
    → delivery: pack + deliverable_e.json (live, operational audit)
```

## Entry points

| Role | Command |
|------|---------|
| Canonical weekly | `make extra-weekly` |
| Structural gate | `make campaign-gate-open-tenders-operational` |
| Release candidate | `make release-candidate-open-tenders` |
| Production verify | `make verify-open-tenders-production` |
| Snapshot integrity | `make snapshot-integrity` |
| Deliverable E live | `make deliverable-e-live` |

## Non-canonical (do not use for open-tenders decision cycle)

- `pncp-crawl-full` / `pncp-crawl-inc` alone as membership authority
- per-modalidade `PncpOpportunityCrawler.run()` as weekly parent
- fixture-only Deliverable E for operational ACCEPT

## Data contracts

- Parent `opportunity_runs` with `scope_complete` only when all required scopes finish
- Membership → `source_snapshot_membership`
- Reconcile never on partial/failed
- Profile PENDING capacity → REVIEW only

## Evidence layout

`artifacts/campaigns/OPEN-TENDERS-OPERATIONAL-DECISION-CYCLE-01/`
