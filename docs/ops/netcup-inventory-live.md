# Inventário live — Netcup RS 2000 G12 (MNZ)

**Data:** 2026-07-23  
**Status:** **SERVER_UP · PROVISIONED_PARTIAL**  
**Não declara:** `VPS_OPERATIONAL` / `PROJECT_DONE`

## Identidade

| Campo | Valor |
|-------|--------|
| Conta CCP | Tiago Sasaki (397766) |
| Account-Name | `v2202607385716487230` |
| Produto | RS 2000 G12 ip iv MNZ |
| Custo | 24,88 €/mês (1 mês mínimo) |
| Próximo statement | 23.08.2026 |
| DC | Manassas, USA |
| SCP server id | 902196 |
| SCP | https://www.servercontrolpanel.de/ |
| IPv4 | **159.195.18.88**/22 |
| Gateway | 159.195.16.1 |
| IPv6 | `2a0a:4cc0:101:1f21::/64` |
| MAC | 96:ed:59:bc:b7:04 |
| Hostname DNS | `v2202607385716487230.happysrv.de` |
| Hardware | 8 cores · 16 GiB RAM · 512 GiB NVMe |

## SO e runtime (estado real)

| Item | Valor |
|------|--------|
| SO instalado | **Debian GNU/Linux 13 (trixie)** — default Netcup |
| Ubuntu 24.04 | Tentativa de reimage no SCP bloqueada por **reauth** (senha conta Netcup) |
| Python | 3.13 (venv em `/opt/extra-consultoria/.venv`) |
| PostgreSQL | **17.10** (Debian) + extensions: plpgsql, pg_trgm, uuid-ossp, **vector** |
| App path | `/opt/extra-consultoria` |
| App user | `extra-consultoria` |
| Timezone | America/Sao_Paulo |
| Swap | 4 GiB |

## Acesso SSH (local)

```sshconfig
Host ec-prod
    HostName 159.195.18.88
    Port 2222
    User root
    IdentityFile ~/.ssh/extra-consultoria-prod
    IdentitiesOnly yes
```

- Chave: `~/.ssh/extra-consultoria-prod` (ed25519)
- Password auth: desabilitada (key-only)
- UFW: 22 + 2222 abertos (22 pode ser removido após validação estável)
- Credenciais PG: `/root/.extra-pg-credentials` na VPS (0600) — vault local: `~/.config/extra-consultoria/netcup-rs2000.env`

## Timers (Onda A)

| Timer | Estado |
|-------|--------|
| `extra-health-check` | enabled |
| `extra-db-backup` | enabled |
| `pncp-crawl-inc` | enabled |
| `extra-crawl-pncp` | enabled |
| `extra-check-alerts` | enabled |
| `extra-collect-metrics` | **broken unit** — calendar `*:0/60:00` inválido no systemd Debian |

## Migrations

- `scripts.ops.apply_migrations` rodou; ledger reportou **migrations_ok**
- 014 (hnsw/vector) falhou na 1ª passagem (sem `vector`); extensão instalada depois (`postgresql-17-pgvector`)

## Config fechada para receber backfill (2026-07-23)

| Item | Estado |
|------|--------|
| Timers PNCP (`pncp-crawl-inc`, `extra-crawl-pncp`, …) | **disabled** (não competir com pilot local) |
| Health / check-alerts / db-backup timer | ativos |
| Staging | `/var/lib/extra-consultoria/{incoming,backups,checkpoints,backfill}` |
| Export script | `scripts/ops/export_backfill_for_vps.sh` |
| Restore script | `scripts/ops/restore_backfill_on_vps.sh` (também em `/opt/extra-consultoria/…`) |
| Dump local diário na VPS | `/usr/local/bin/extra-local-pg-dump.sh` → `…/backups/postgresql/` |
| Runbook | `docs/ops/vps-backfill-migration.md` |
| Pilot local 3y | **ainda rodando** — export snapshot em paralelo (re-export no cutover) |

## Pendências

1. **Upload + restore** do package `artifacts/migration/backfill-vps/pkg-*` quando dump terminar  
2. **Cutover final:** parar pilot local → re-export → restore → resume janelas faltantes **só na VPS**  
3. **Backup off-box** (S3/rsync remoto) — dump local em disco ainda não é off-site  
4. Corrigir `extra-collect-metrics.timer` OnCalendar  
5. Reimage Ubuntu 24.04 (opcional) — reauth Netcup  
6. Remover UFW porta 22 após estabilidade  
7. Snapshot SCP “post-restore”  

## Comandos

```bash
ssh ec-prod
ssh ec-prod "systemctl list-timers --all | grep -E 'extra|pncp'"
# migração
bash scripts/ops/export_backfill_for_vps.sh          # local
bash scripts/ops/export_backfill_for_vps.sh --upload
ssh ec-prod 'bash /opt/extra-consultoria/scripts/ops/restore_backfill_on_vps.sh /var/lib/extra-consultoria/incoming/pkg-…'
```
