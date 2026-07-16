# L1.7 — Backup e restore local (re-prova)

**Data:** 2026-07-16

## Método

1. `pg_dump -Fc` de `pncp_datalake` via container
2. `pg_restore` em DB throwaway `restore_drill`

## Resultado

| Check | Valor |
|-------|--------|
| Dump size | ~515 KB (amostra local) |
| Restore exit | **0** |
| Tables public | **60** |
| `pncp_raw_bids` | **346** |
| `target_universe_entities` | **2085** |

Capture: `gate1-backup-restore.log`.

## Nota

- Storage Box remoto / `backup-database.sh` completo **não** exercitado (requer `BACKUP_STORAGE_BOX_SSH`).
- Drill local prova dump→restore do schema+dados no Postgres do compose.
