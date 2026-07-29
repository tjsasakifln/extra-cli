# STATUS — EXTRA-OPERATIONAL-RELIABILITY-AND-COVERAGE-CLOSURE-01

| Field | Value |
|-------|-------|
| baseline_sha | d91fdc5967314b46858b0f154b807ccbab7ed515 |
| branch | campaign/extra-operational-reliability-coverage-closure-01 |
| as_of | 2026-07-29 |

## Delivered in code

- Checkpoint v2: logical_job_id + attempt_run_id (`scripts/crawl/contracts_checkpoint_contract.py`)
- Incremental rebind without false foreign-run fail
- Canonical contracts writer lock `/run/lock/extra-contracts-writer.lock`
- weekly default: reuse lake (no dual writer); optional incremental uses same checkpoint+lock
- Soak tracker fail-closed (UTC, no data_publicacao freshness, requires run_id + success)
- Systemd units updated (pncp-contracts, extra-weekly, extra-contracts-soak)
- PR #170 docs incorporated; PR #168 docs extracted (no full merge)

## Terminal state (session target)

`OPERATIONAL_READY_SOAK_IN_PROGRESS` when deploy + first successful incremental + soak armed.

## Not claimed

- 7-day soak complete
- 95% dual coverage without live dual run after deploy
