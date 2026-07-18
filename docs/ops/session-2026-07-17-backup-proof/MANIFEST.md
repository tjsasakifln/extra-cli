# Local backup/restore proof — §14

**Story:** ROI-cand-local-backup-restore-proof  
**Date:** 2026-07-18 (clean rebuild on main)

## Proven

| Claim | Evidence |
|-------|----------|
| Script de backup existe | scripts/backup-database.sh |
| Script de restore existe | scripts/restore-database.sh |
| Formato restaurável (pg_dump -Fc custom + gzip ↔ pg_restore) | format-notes.txt / scripts |
| Retenção mínima definida e aplicada | RETENTION_DAILY=7 WEEKLY=4 prune loops |
| Fail-closed basics | set -euo pipefail; DSN required; gzip integrity check |

## NOT proven (remain open)

| Claim | Status |
|-------|--------|
| Existe backup local do PostgreSQL | no live dump file in this environment |
| Arquivo de backup possui data | blocked without real dump |
| Integridade do backup verificada | blocked without real dump |
| Restore testado em banco separado | BLOCKED_EXTERNAL (no local PG) |
| Restore recompõe migrations/dados | BLOCKED_EXTERNAL |
| Tempo de recuperação conhecido | not measured |

## Authorized flips: exactly 3

See proposed-flips.txt. Do not convert "script exists" into "restore proven".
