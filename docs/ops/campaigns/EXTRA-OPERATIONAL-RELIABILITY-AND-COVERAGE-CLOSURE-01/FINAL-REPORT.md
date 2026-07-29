# FINAL-REPORT — EXTRA-OPERATIONAL-RELIABILITY-AND-COVERAGE-CLOSURE-01

**terminal_state:** `OPERATIONAL_READY_SOAK_IN_PROGRESS`  
**as_of:** 2026-07-29T15:20:00Z  
**PR:** https://github.com/tjsasakifln/extra-cli/pull/171  
**deployed_sha (VPS):** `762f799c` (campaign branch tip at deploy)

## Baseline

| Item | Value |
|------|-------|
| origin/main at start | `d91fdc5967314b46858b0f154b807ccbab7ed515` |
| Failed units before | pncp-contracts, extra-weekly, extra-contracts-soak |
| Contracts root cause | `checkpoint run_id mismatch` on every timer fire |

## Implemented

1. **Checkpoint contract v2** (`scripts/crawl/contracts_checkpoint_contract.py`)
   - `logical_job_id` stable (`pncp-contracts-incremental`)
   - `attempt_run_id` per execution (mirrored as `meta.run_id`)
   - diagnose / migrate / repair with archive backup
2. **Shared writer lock** (`scripts/crawl/contracts_writer_lock.py`)
   - `/run/lock/extra-contracts-writer.lock`
   - exit 75 = busy (SuccessExitStatus on unit)
3. **Incremental path** rebinds same logical job without foreign hard-fail
4. **weekly** defaults to lake reuse; optional incremental uses same checkpoint+lock
5. **Soak tracker fail-closed** (UTC, no `data_publicacao` freshness, requires success+run_id)
6. **systemd** units versioned and installed on VPS
7. **PR #170** docs incorporated; **#168** docs extracted (no code merge)

## Production proof (VPS)

| Check | Result |
|-------|--------|
| Checkpoint migrate | archived + v2 identity |
| First incremental after fix | **success** |
| attempt_run_id | `contracts-90d-20260729T145807Z-d20199cb7c` |
| previous | includes `contracts-90d-20260723T201229Z-4da85aaee0` |
| pages / inserted | 96 pages, 2331 inserted, 0 page_errors |
| windows | `20260716_20260723`, `20260722_20260729` |
| service Result | success, ExecMainStatus=0 |
| pncp-contracts.timer | enabled + active |
| extra-contracts-soak.timer | enabled |
| Second-attempt rebind (in-memory) | OK without clearing windows |

## Explicit non-claims

- **Not** 7 consecutive soak days complete (time must pass)
- **Not** dual coverage ≥95% without post-deploy dual measurement on full universe
- **Not** all edital source timers enabled (phased; SLA 24h still incomplete for multi-source)
- **Not** DOD promotion of unproven items
- **Not** inventing soak days from legacy artifacts

## Residual risks / next ops

1. Complete 7 UTC soak days with daily `extra-contracts-soak.timer`
2. Phase-enable edital crawlers (PNCP → CIGA CKAN → SC) with measurement gates
3. Run dual capability coverage single invocation after lake warm
4. Merge PR #171 when CI green; close #168 as superseded; keep #170 history via docs in #171
5. Alert webhook wiring if still missing

## Kill switches

- `systemctl stop pncp-contracts.timer`
- Checkpoint archive via `contracts_checkpoint_contract repair`
- Never delete checkpoint without `.bak.*`
