# Netcup Storagespace — provisioned (option A)

**As of:** 2026-07-23T22:26Z  
**Campaign:** HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01

## Ordered via CCP (Playwright)

| Field | Value |
|-------|--------|
| Volume | `voln1116040a1` |
| Storage host | `46.38.248.210` |
| Export | `46.38.248.210:/voln1116040a1` |
| Status | Started |
| Plan | 250 GB / 5,00 € excl. VAT (+ usage overage) |
| VPS IP allowlisted | `159.195.18.88` |

## VPS configuration (not in git)

- `/etc/backup-database.conf`: `BACKUP_NFS_EXPORT`, `BACKUP_STORAGE_BOX_SSH=nfs://…`, mount `/mnt/storage-box`
- `fstab` NFS hard mount
- Local vault: `~/.config/extra-consultoria/netcup-storagespace.env`

## First off-site backup proof

| Field | Value |
|-------|--------|
| Path | `/mnt/storage-box/backups/postgresql/daily/pncp_datalake-2026-07-23.dump.gz` |
| Size | 421 985 469 bytes (~403 MiB) |
| gzip -t | OK |
| SHA256 | `72d8866e9f78e3c2c9b4442ee07d659a37239763f202e2ad6061f2e79cde358c` |
| `campaign_offsite_backup_status` (on VPS) | **ok** |

## Code changes

- `scripts/backup-database.sh` — NFS + stage-local-then-copy + retention fix
- `scripts/ops/campaign_offsite_backup_status.py` — NFS/export aware

## Residual

- Separate-DB **restore from NFS package** still recommended as formal drill (local separate-DB already done earlier).
- Soak 7d still incomplete → campaign remains **BLOCKED** on soak only.
