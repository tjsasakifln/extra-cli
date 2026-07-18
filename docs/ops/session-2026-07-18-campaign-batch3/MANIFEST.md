# Campaign batch-3 — operational config & backup evidence

**Date:** 2026-07-18  
**Branch:** extra-roi/campaign-dod-50-20260718T003950Z  

## Reproduced commands (exit 0)

| Command | Exit |
|---------|------|
| `python3 scripts/golden_path.py --help` | 0 |
| `python3 scripts/local_datalake.py --help` | 0 |
| `python3 scripts/crawl/monitor.py --help` | 0 |
| `bash scripts/backup-database.sh --help` | 0 |
| `bash scripts/restore-database.sh --help` | 0 |

## Static proofs

| Claim | Proof |
|-------|-------|
| Backup has date in artifact | `date`/`%Y`/timestamp patterns in `scripts/backup-database.sh` |
| Backup integrity | `gzip -t` in backup script |
| No hardcoded backup secret | env DSN; password scan clean |
| Config centralized | `scripts/crawl/config.py` |
| Domain constants | `scripts/lib/constants.py` |
| Timeouts configurable | config timeout keys |
| Retries configurable | `scripts/lib/retry.py` + config |
| Freshness windows | freshness modules + config |
| Coverage thresholds | `.coveragerc` `[coverage_gate] threshold=80` |
| Schema via migrations | 7 files under `supabase/migrations/` |
| Code ≠ ready capability | PRE-VPS truth-gate vocabulary |
| Old data ≠ current | `scripts/crawl/freshness.py` / freshness gate |

## Flips

See `flipped.json` (13 items).
