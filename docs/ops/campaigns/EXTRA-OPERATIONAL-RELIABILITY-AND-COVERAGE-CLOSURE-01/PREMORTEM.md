# PREMORTEM — EXTRA-OPERATIONAL-RELIABILITY-AND-COVERAGE-CLOSURE-01

**Frozen at:** 2026-07-29T14:40:46Z (VPS) / baseline SHA `d91fdc5967314b46858b0f154b807ccbab7ed515`  
**Branch:** `campaign/extra-operational-reliability-coverage-closure-01`  
**Worktree:** `/mnt/d/extra-cli-wt-op-reliability-01`  
**Host de record:** Netcup `ec-prod` / `v2202607385716487230` (≠ selo `VPS_OPERATIONAL`)

## Baseline freeze (evidence)

| Item | Value |
|------|-------|
| origin/main | `d91fdc5967314b46858b0f154b807ccbab7ed515` |
| Deployed SHA (VPS) | `d91fdc5967314b46858b0f154b807ccbab7ed515` |
| Working tree campaign | clean at branch create |
| Main CI | green on latest main push |
| Failed units | `pncp-contracts`, `extra-weekly`, `extra-contracts-soak` |
| Active crawl processes | none |
| Locks present | `extra-cli-production-mutation`, `extra-crawl-pncp`, `extra-weekly` (idle files) |
| Disk / mem | 4% of 503G; ~11Gi available |
| Last reboot | 2026-07-23 08:59 (~6d uptime) |
| PR #168 | OPEN CONFLICTING (docs+code drift) — not merge-as-is |
| PR #170 | OPEN MERGEABLE docs audit `SCHEDULERS_FAILED` |

## Observed production failure (contracts)

```
ValueError: checkpoint run_id mismatch:
  existing='contracts-90d-20260723T201229Z-4da85aaee0'
  current='contracts-90d-20260729T090256Z-98168e293a'
```

Path: `data/contracts_checkpoints/incremental/contracts_full.json`  
Timer fires → new `run_id` → loader rejects → unit fails indefinitely.

## Risks (frozen)

| # | Risk | Kill switch |
|---|------|-------------|
| 1 | Checkpoint bound to attempt run_id rejects every timer fire | Stop `pncp-contracts.timer`; archive checkpoint; do not delete without backup |
| 2 | Dual writers (`pncp-contracts.lock` vs `extra-weekly.lock`) | Disable one writer; shared `/run/lock/extra-contracts-writer.lock` only |
| 3 | Editais timers disabled / SLA 24h impossible | Do not claim open_tenders PASS; phase enable only |
| 4 | HTTP 429 PNCP | Reduce concurrency; circuit open; never SUCCESS_ZERO |
| 5 | Soak tracker false green (`health_ok` without contracts success) | Fail-closed soak code; exit 2 if incomplete |
| 6 | Freshness via `data_publicacao` | Use ingestion/observation timestamps only |
| 7 | VPS units diverge from repo | Deploy only versioned units; inventory first |
| 8 | Units only-installed on host | Back up + remove or version |
| 9 | Alerting without webhook | Mark alerts DEGRADED; do not claim OPERATIONAL |
| 10 | Simultaneous crawler stampede | One family per source; phased enable |
| 11 | SUCCESS_ZERO without ledger | Audit zeros; reject promotion |
| 12 | Dual coverage from different runs | Single dual runner invocation |
| 13 | CI fail from PR #168 side-code | No full merge of #168; selective reimplement |
| 14 | DOD promotion without proof | Only ACCEPTED with gates + evidence |
| 15 | Fake soak (retro fill) | UTC day observations only; no backfill days |

## Kill switches (global)

1. `systemctl stop pncp-contracts.timer extra-weekly.timer extra-contracts-soak.timer`
2. Env: `EXTRA_CRAWL_DISABLED=1` (if wired)
3. Lock domain: nonblock flock → exit 75 (SuccessExitStatus), not source FAIL
4. Checkpoint repair: `python -m scripts.crawl.repair_contracts_checkpoint --archive` only
5. Never `rm` checkpoint without `.bak.<ts>`

## Authority decisions (campaign)

| Topic | Decision |
|-------|----------|
| Incremental contracts writer | `pncp-contracts.timer` sole recurring authority |
| Weekly contracts | **reuse lake** by default; if `--contracts-incremental`, same job + same lock + same checkpoint dir |
| Checkpoint model | `logical_job_id` stable; `attempt_run_id` per fire |
| Dual coverage | `scripts.coverage.dual_capability_coverage` single invocation |
| Soak | fail-closed; 7 real consecutive UTC days; no invention |

## Out of scope this session

- SaaS / dashboard product scope
- Relaxing municipal `pncp + ciga_ckan` policy without ADR
- Inventing 7 soak days in artifacts
- Merging PR #168 wholesale
