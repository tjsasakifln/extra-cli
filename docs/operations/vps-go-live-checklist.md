# VPS Go-Live Checklist — Extra Consultoria

**Versão:** 1.0 | **Data:** 2026-07-15 | **Classificação:** `NO_GO`

---

## Condições para GO

Nenhum item pode ser UNKNOWN ou FAIL. CONCERNS requer justificativa documentada.

| # | Condição | Status | Evidência necessária |
|---|----------|--------|---------------------|
| 1 | Fresh install Ubuntu 24.04 LTS | UNKNOWN | `provision-vps.sh` executado do zero, exit 0 |
| 2 | PostgreSQL 17 com 42 migrations | **FAIL** | `SELECT count(*) FROM _migrations` = 42 |
| 3 | Seeds idempotentes | PASS | `db/seed/001_sc_entities.py` → 2.085 entes |
| 4 | Crawl PNCP mínimo (7 dias SC) | UNKNOWN | Log mostra X registros, 0 erros |
| 5 | Briefing gerado com dados reais | UNKNOWN | `output/readiness/*.json` com timestamps recentes |
| 6 | Reconciliação contra planilha | UNKNOWN | `target-reconciliation.csv` com recall > 0% |
| 7 | Systemd services ativos | PASS | `systemctl is-active pncp-crawl-full.service` |
| 8 | Systemd timers ativos | PASS | `systemctl list-timers 'extra-*'` |
| 9 | Browser headless funcional | UNKNOWN | `python scripts/crawl/selenium_smoke_test.py` → PASS |
| 10 | Backup executado | UNKNOWN | Arquivo .dump em Storage Box, timestamp < 24h |
| 11 | Restore executado | UNKNOWN | `pg_restore --list` mostra tabelas, integridade OK |
| 12 | Reboot e recuperação | UNKNOWN | Após reboot: services UP, crawl retoma |
| 13 | Health check | PASS | `extra-health-check.service` → exit 0 |
| 14 | Alertas configurados | PASS | Webhook OnFailure configurado, teste de disparo |
| 15 | Firewall ativo | PASS | `ufw status` → portas 22, 5432 (localhost), 80/443 |
| 16 | Usuário não-root | PASS | Services rodam como `extra-consultoria` |
| 17 | Secrets fora do repo | PASS | `.env` não rastreado, `.env.example` sem valores reais |
| 18 | Rollback documentado | **FAIL** | Apenas 1/42 migrations com rollback SQL |
| 19 | Smoke test end-to-end | UNKNOWN | Script `smoke-test-vps.sh` executado, exit 0 |
| 20 | Timezone UTC | PASS | `timedatectl` → Time zone: Etc/UTC |

---

## Sequência de Go-Live

```bash
# 1. Provisionar VPS (Hetzner CX22 ou equivalente)
ssh root@<vps-ip> 'bash -s' < deploy/provision-vps.sh

# 2. Copiar código e config
rsync -avz --exclude '.git' --exclude '__pycache__' --exclude 'data/' \
  ./ extra-consultoria@<vps-ip>:/opt/extra-consultoria/

# 3. Configurar .env
scp .env extra-consultoria@<vps-ip>:/opt/extra-consultoria/.env

# 4. Executar migrations
ssh extra-consultoria@<vps-ip> \
  'cd /opt/extra-consultoria && bash scripts/apply-migrations.sh'

# 5. Seed
ssh extra-consultoria@<vps-ip> \
  'cd /opt/extra-consultoria && python db/seed/001_sc_entities.py'

# 6. Habilitar timers
ssh extra-consultoria@<vps-ip> \
  'sudo systemctl enable --now pncp-crawl-inc.timer'

# 7. Primeiro crawl
ssh extra-consultoria@<vps-ip> \
  'sudo systemctl start pncp-crawl-full.service'

# 8. Verificar
ssh extra-consultoria@<vps-ip> \
  'cd /opt/extra-consultoria && python scripts/opportunity_intel/cli.py coverage'

# 9. Smoke test
ssh extra-consultoria@<vps-ip> \
  'cd /opt/extra-consultoria && bash tests/smoke/smoke-test-vps.sh'

# 10. Backup inicial
ssh extra-consultoria@<vps-ip> \
  'sudo systemctl start extra-db-backup.service'
```

---

## Verificações Pós-Deploy (24h)

- [ ] Crawl incremental executou 3x sem erro
- [ ] Número de oportunidades > baseline (298)
- [ ] Nenhum alerta de OnFailure
- [ ] Backup diário concluído
- [ ] Logs sem ERROR ou CRITICAL
- [ ] Uso de disco < 50%
- [ ] Uso de memória < 80%
- [ ] Load average < 2.0

---

## Rollback

```bash
# Desabilitar timers
ssh extra-consultoria@<vps-ip> 'sudo systemctl disable --now extra-*.timer'

# Restaurar banco (se necessário)
ssh extra-consultoria@<vps-ip> \
  'pg_restore -U extra -d pncp_datalake /backup/latest.dump'

# Rollback de código
ssh extra-consultoria@<vps-ip> \
  'cd /opt/extra-consultoria && git checkout <commit-estável>'
```

---

*VPS Go-Live Checklist v1.0 — 2026-07-15*
