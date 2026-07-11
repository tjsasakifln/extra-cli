# Deploy — Tasks

| # | Tarefa | Fonte | Confiança |
|---|--------|-------|-----------|
| T-DP01 | Script provision-vps.sh: 10 steps idempotentes | `provision-vps.sh:1-405` | 🟢 |
| T-DP02 | Criar 20 systemd service+timer pairs com schedule correto | `deploy/systemd/*` | 🟢 |
| T-DP03 | Template OnFailure: POST JSON webhook | `onfailure@.service` | 🟢 |
| T-DP04 | Hardening: ufw + fail2ban + pg_hba | `deploy/hardening/*` | 🟢 |
| T-DP05 | Backup script: pg_dump + gzip + sshfs + retention | `backup-database.sh` | 🟢 |
| T-DP06 | Restore script: full, schema-only, data-only, list | `restore-database.sh` | 🟢 |
| T-DP07 | Health check script: DB, API keys, disco, crawlers | `healthcheck.py` | 🟢 |
| T-DP08 | Métricas + alertas: collect-metrics, check-alerts | `collect-metrics.py`, `check-alerts.py` | 🟢 |

**Estimativa:** 3-4 dias (8 tarefas)
