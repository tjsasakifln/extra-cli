# HANDOFF — HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01

**Escrito:** 2026-07-23T22:30Z  
**Resultado da campanha:** **BLOCKED** (só soak 7d)  
**Não declara:** `LOCAL_READY`, `VPS_OPERATIONAL`, `PROJECT_DONE`, open_tenders ≥95%

---

## 1. Resumo executivo

O backfill de contratos históricos PNCP (**≥3 anos, 37/37 janelas**) está **concluído e materializado na VPS Netcup** (`pncp_supplier_contracts` ≈ **4 438 393** linhas). Cutover, dual coverage 100%, incremental com timer, backup **off-site NFS** (Netcup Storagespace) e 8 itens DOD ACCEPTED em `main` estão feitos.

**Único bloqueio restante:** observação de **soak 7 dias consecutivos** (hoje **dia 1/7**). Timer `extra-contracts-soak.timer` armado.

---

## 2. Estado revalidado (encerramento)

| Item | Valor |
|------|--------|
| Repo | `tjsasakifln/extra-cli` |
| `origin/main` (última observ.) | `2f22fa0`+ (DOD accepts); VPS app ainda pode estar em `5f92211` se não redeploy |
| VPS host | `ec-prod` · `159.195.18.88` · Debian 13 · PG 17 |
| Contratos VPS | **4 438 393** |
| Checkpoint 3y | **37/37** · span 20230720→20260723 (≥1098 d) |
| Dual historical_contracts | **PASS 100%** (1093/1093) |
| Incremental | timer `pncp-contracts` Mon/Wed/Fri 06:00 · last success |
| Off-site | NFS `46.38.248.210:/voln1116040a1` → `/mnt/storage-box` · dump 403 MiB + sha256 |
| Failed units | **0** |
| Soak | **1/7** · `extra-contracts-soak.timer` active |

---

## 3. Backfill — prova

- Checkpoint: `data/contracts_checkpoints/hc_closure_3y/contracts_full.json` (espelhado em `/var/lib/extra-consultoria/checkpoints/hc_closure_3y/`)
- Cutover: `cutover.json` (SHA256 + count match)
- Dual: `dual-coverage.json`
- Incremental: `incremental.json` + journal `pncp-contracts.service`
- Claims: `HISTORICAL_CONTRACTS_BACKFILL_37_WINDOWS`, `CUTOVER_RESTORE_OK`, `VPS_INCREMENTAL_TIMER_EXECUTED`

**Single writer:** VPS `pncp-contracts` (laptop pilot parado).

---

## 4. Off-site (desbloqueado nesta sessão)

| Campo | Valor |
|-------|--------|
| Produto | Netcup Storagespace 250 GB (`voln1116040a1`) |
| Export | `46.38.248.210:/voln1116040a1` |
| Mount | `/mnt/storage-box` (fstab hard NFS) |
| Conf host | `/etc/backup-database.conf` (não versionar) |
| Vault laptop | `~/.config/extra-consultoria/netcup-storagespace.env` |
| Dump | `…/daily/pncp_datalake-2026-07-23.dump.gz` · 421 985 469 B |
| SHA256 | `72d8866e9f78e3c2c9b4442ee07d659a37239763f202e2ad6061f2e79cde358c` |
| Status | `backup-offsite.json` → **ok** |
| Docs | `storagespace-provisioned.md` |

Código local a integrar se ainda não em main: `scripts/backup-database.sh`, `scripts/ops/campaign_offsite_backup_status.py` (NFS + stage local).

---

## 5. DOD (main)

Oito itens ACCEPTED e pushados (ver `dod-accepts.md`), entre eles:

- backfill ≥3y / datas / dual 95% / coleta / incremental / no-restart windows

**Não aceitar ainda:** soak 7d, `VPS_OPERATIONAL`, `PROJECT_DONE`, reboot completo de host, open_tenders.

---

## 6. O que a próxima sessão deve fazer

1. **Deixar soak rodar** (timer diário ~00:04). Após 7 dias:
   ```bash
   ssh ec-prod 'cd /opt/extra-consultoria && python3 -m scripts.ops.campaign_soak_tracker --campaign HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01'
   # jq .complete artifacts/.../soak.json  → true
   ```
2. **Opcional:** restore drill a partir do dump NFS (DB separado) se quiser reforçar §22.
3. **Opcional:** redeploy VPS para SHA main com scripts NFS (já aplicados em runtime via scp).
4. **Só então:** `python3 -m scripts.ops.campaign_verify_production` → se verde, `result.json=PASS` e accepts DOD de soak/ops contínuos **um a um**.
5. **Não** mergear PR #121 até renumerar migration 059.

---

## 7. Comandos úteis

```bash
# Contagem VPS
ssh ec-prod "sudo -u postgres psql -d pncp_datalake -tAc 'select count(*) from pncp_supplier_contracts'"

# Off-site
ssh ec-prod 'python3 -m scripts.ops.campaign_offsite_backup_status'
ssh ec-prod 'ls -lah /mnt/storage-box/backups/postgresql/daily/'

# Incremental manual
ssh ec-prod 'systemctl start pncp-contracts.service'

# Soak
ssh ec-prod 'systemctl list-timers extra-contracts-soak.timer'
```

---

## 8. Claims autorizados vs non-claims

**Claims:** backfill 37/37, dual PASS, cutover OK, restore drill local OK, incremental timer, off-site NFS backup OK.

**Non-claims:** `LOCAL_READY`, `VPS_OPERATIONAL`, `PROJECT_DONE`, open_tenders≥95%, soak_7d_complete, campaign **PASS** (ainda BLOCKED por calendário).

---

## 9. Resultado final desta sessão

| Campo | Valor |
|-------|--------|
| Campanha | HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01 |
| Resultado | **BLOCKED** |
| Bloqueio | `SOAK_7D_IN_PROGRESS` (wall-clock; timer armado) |
| Backfill contratos | **UP na VPS** — operação incremental ativa |
| Owner próximo | Automação soak + revalidação humana pós-D7 |

**Encerramento:** handoff completo; não iniciar nova campanha. Soak é duração real, não abandono.
