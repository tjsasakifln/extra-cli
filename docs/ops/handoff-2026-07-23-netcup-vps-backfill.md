# Handoff — Netcup VPS + migração backfill histórico

| Campo | Valor |
|-------|--------|
| **UTC** | 2026-07-23T13:27:42Z |
| **Branch** | `campaign/historical-contracts-operational-closure-01` @ `dc71b72` |
| **Campanha** | HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01 |
| **YAML** | `.aiox/handoffs/handoff-2026-07-23-netcup-vps-backfill.yaml` |

---

## 1. Objetivo da sessão

1. Organizar e provisionar a assinatura **Netcup RS 2000 G12 · MNZ**.  
2. Deixar a VPS pronta para receber o **backfill de contratos históricos** que roda no laptop.  
3. Migrar um **snapshot** (não cutover final) e documentar o restante.

---

## 2. Infra (Netcup)

| Item | Valor |
|------|--------|
| Conta CCP | Tiago Sasaki **397766** |
| Produto | RS 2000 G12 ip iv MNZ · **24,88 €/mês** |
| SCP id | `902196` · account `v2202607385716487230` |
| IPv4 | **159.195.18.88**/22 |
| DNS | `v2202607385716487230.happysrv.de` |
| DC | Manassas (US) |
| HW | 8 cores · 16 GB · 512 GB NVMe |
| SO | **Debian 13 (trixie)** (default Netcup) |
| PG | **17.10** + `vector` / `pg_trgm` |
| App | `/opt/extra-consultoria` · user `extra-consultoria` |
| SSH | `ssh ec-prod` → root@IP **:2222** · chave `~/.ssh/extra-consultoria-prod` |

**Segredos (não git):**  
- Local: `~/.config/extra-consultoria/netcup-rs2000.env`  
- VPS: `/root/.extra-pg-credentials`

**Ubuntu 24.04:** tentativa de reimage no SCP pediu **reauth** (senha conta Netcup) — não concluída.

---

## 3. O que está feito

### VPS
- [x] Acesso SSH key-only porta 2222 + alias `ec-prod`  
- [x] UFW (22+2222), fail2ban, swap 4G, timezone America/Sao_Paulo  
- [x] App clonado + venv + migrations + pgvector  
- [x] **Timers PNCP desligados** (`pncp-crawl-inc`, `extra-crawl-pncp`, full/contracts/enrich)  
- [x] Timers ativos: `extra-health-check`, `extra-check-alerts`, `extra-db-backup`  
- [x] Staging: `/var/lib/extra-consultoria/{incoming,backups,checkpoints,backfill}`  
- [x] Dump local diário: `/usr/local/bin/extra-local-pg-dump.sh`  
- [x] Scripts de migração no repo e na VPS  

### Backfill snapshot → VPS
| | |
|--|--|
| Package | `artifacts/migration/backfill-vps/pkg-20260723T131251Z` (~302 MB) |
| Restore | **OK** |
| **VPS count** | **3 337 776** (= manifest do dump) |
| Checkpoint VPS | **26/37** janelas em `/var/lib/extra-consultoria/checkpoints/hc_closure_3y` |

### Docs
- `docs/ops/vps-backfill-migration.md` — runbook cutover  
- `docs/ops/netcup-inventory-live.md` — inventário live  
- `docs/ops/vps-access.md` / `v6.2-…` / `netcup-phase0-activate.md`  
- `docs/baseline/v6.2-pncp-from-vps.md` — PNCP alcançável de MNZ (sem 403 geo)  
- `deploy/provision-vps.sh` — profile rs2000-16g  

---

## 4. Estado agora (fonte de verdade operacional)

### Writer canônico = **laptop** (ainda)

```text
PID 11008  run_contracts_90d_pilot.py --days 1099 --allow-cross-run-resume
DSN        postgresql://test:test@127.0.0.1:5433/extra_test
checkpoint data/contracts_checkpoints/hc_closure_3y/
log        .../backfill/live-3y-resume-20260723T115016Z.log
```

| Métrica (≈ handoff) | Local | VPS |
|---------------------|------:|----:|
| `pncp_supplier_contracts` | **~3 421 049** | **3 337 776** |
| Janelas completas (ckpt) | **27**/37 | **26**/37 |
| current_window | `20250907` | (ckpt snapshot `20250808`) |

**Drift esperado:** local avançou depois do dump. Não resumir pilot na VPS enquanto o local escrever.

**Regra:** um único writer de contratos PNCP por vez.

---

## 5. Próximas ações (ordem)

### A — Enquanto o local roda
1. Não reativar timers PNCP na VPS.  
2. Monitorar pilot:
   ```bash
   ps -p 11008 -o etime,pcpu,cmd
   tail -f artifacts/campaigns/HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/backfill/live-3y-resume-20260723T115016Z.log
   python3 -c "import json;d=json.load(open('data/contracts_checkpoints/hc_closure_3y/contracts_full.json'));print(len(d['completed_windows']),'/37',d.get('current_window_start'))"
   ```

### B — Cutover final (quando `completed_windows==37` **ou** decisão de parar local)

```bash
# 1) parar pilot local
kill <PID>

# 2) re-export + upload
export LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/extra_test
bash scripts/ops/export_backfill_for_vps.sh --upload

# 3) restore
ssh ec-prod 'bash /opt/extra-consultoria/scripts/ops/restore_backfill_on_vps.sh \
  /var/lib/extra-consultoria/incoming/pkg-<STAMP>'

# 4) validar counts == manifest
# 5) se ainda faltarem janelas: resume SÓ na VPS (ver runbook §4)
```

### C — Pós-cutover (campanha)
1. Entity projection + dual capability coverage (STATUS da campanha).  
2. Backup **off-site** (hoje só disco da VPS).  
3. Corrigir `extra-collect-metrics.timer` (`*:0/60:00` inválido).  
4. (Opcional) Ubuntu 24.04 com senha Netcup reauth.  
5. Snapshot SCP pós-restore estável.  
6. Remover UFW porta 22 após dias estáveis em 2222.

### D — Não fazer
- Claim `VPS_OPERATIONAL` / 95% / `PROJECT_DONE`  
- Dois pilots (local + VPS) ao mesmo tempo  
- `--reset-checkpoint` no resume  

---

## 6. Comandos úteis

```bash
ssh ec-prod
ssh ec-prod 'systemctl list-timers --all | grep -E "extra|pncp"'
ssh ec-prod 'source /root/.extra-pg-credentials && psql "$LOCAL_DATALAKE_DSN" -c "SELECT count(*) FROM pncp_supplier_contracts;"'
```

---

## 7. Arquivos-chave

| Path | Uso |
|------|-----|
| `docs/ops/vps-backfill-migration.md` | Runbook migração |
| `docs/ops/netcup-inventory-live.md` | Inventário Netcup |
| `scripts/ops/export_backfill_for_vps.sh` | Dump local |
| `scripts/ops/restore_backfill_on_vps.sh` | Restore VPS |
| `artifacts/migration/backfill-vps/` | Packages (gitignored) |
| `artifacts/campaigns/HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/STATUS.md` | Campanha 3y |
| `.aiox/handoffs/handoff-2026-07-23-netcup-vps-backfill.yaml` | Handoff máquina |

---

## 8. Blockers

1. Senha Netcup para reauth/reimage Ubuntu  
2. Off-site backup  
3. Pilot 3y incompleto + drift snapshot  
4. `prometheus_client` não está no `requirements.txt` (instalado manual na VPS)  

---

**Próxima sessão:** ler este handoff + YAML → checar se PID local ainda vive → ou cutover B se 37/37.
