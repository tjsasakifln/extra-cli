# CONFENGE-PRODUCTION-CLOSEOUT-01 — extra-cli baseline

Approval: `OWNER_CONDITIONAL_PREAPPROVAL_CONFENGE_PRODUCTION_CLOSEOUT_01`

Measured: 2026-08-17T12:36Z (revalidated; not an inherited SHA claim).

## Git

| Field | Value |
|---|---|
| origin/main | `2d68272dbe4680c6285b9a35a43f6e4f9076e966` |
| Worktree | `.worktrees/production-closeout-01` |
| Branch | `campaign/CONFENGE-PRODUCTION-CLOSEOUT-01` |
| Dirty checkout (original) | untracked `.campaign/`, `.venv/`, artifacts — preserved, not used as source |

## Consumed from main (not reimplemented)

- `#423` PNCP national backfill classifier (`scripts.ops.audit_pncp_national_backfill`)
- `#416` named consumers
- `#417` national claims gate (tables **absent** on live lake)
- `#418` / `#415` comparables + official canary
- `#419` / `#414` publication candidates + evidence packs

## Live lake

| Field | Evidence class | Value |
|---|---|---|
| Host | LIVE_PROVEN | Netcup VPS via SSH identity (PRESENTE) |
| Database | LIVE_PROVEN | `pncp_datalake.pncp_supplier_contracts` |
| COUNT(*) | LIVE_PROVEN | 4 573 257 |
| Publication span | LIVE_PROVEN | 2023-07-20 → 2026-08-17 |
| in 3y span | LIVE_PROVEN | 4 439 372 |
| after backfill end | LIVE_PROVEN | 133 885 |
| Checkpoint `hc_closure_3y` | LIVE_PROVEN | 37/37 completed, sha256 `17ff50a4d47dc6d5e17541940f95325efbd76c80a0c1bd07c481d240e9312bf8` |
| Auditor ×2 | CODE_PROVEN + LIVE_PROVEN | `BACKFILL_COMPLETO` (reports equal sans `as_of`) |
| Incremental today | LIVE_PROVEN | timer fired 2026-08-17 06:03-03; unit **failed** `source_population_drift` (44515→44517) after inserting 261; `max(ingested_at)` today |

Token: `BACKFILL_BASELINE_ACCEPTED`. Incremental is **fresh** but **not clean success**. Not `INCREMENTAL_HEALTHY`.

## Credentials (presence only)

| Item | State |
|---|---|
| Netcup SSH identity | PRESENTE (connect OK) |
| `LOCAL_DATALAKE_DSN` on VPS | PRESENTE (`127.0.0.1:5432/pncp_datalake`) |
| Laptop env DSN | AUSENTE (tunneled) |
| `#302` persist tables | AUSENTE |

## Open PRs / issues

- Open PR: `#413` only (out of path).
- `#302` `#400` `#414` `#415` remain OPEN.
