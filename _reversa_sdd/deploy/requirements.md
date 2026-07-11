# Deploy — Requirements

> Gerado pelo Writer em 2026-07-11T22:30:00Z | doc_level: completo | Base: e9729e1

Provisionamento VPS Hetzner CX22, 20 systemd timers, hardening, backup automatizado.

## Requisitos Funcionais

| ID | Descrição | Prioridade | Fonte |
|----|----------|-----------|-------|
| RF-DP01 | Provisionar VPS: 10 steps (pacotes, usuário, SSH, firewall, PG tuning, clone, migrations, timers) | Must | `provision-vps.sh:1-405` |
| RF-DP02 | 20 systemd timer/service pairs: crawlers, reports, backup, health, métricas | Must | `deploy/systemd/*` |
| RF-DP03 | OnFailure webhook: POST JSON para WEBHOOK_URL em falha | Must | `onfailure@.service`, `extra-onfailure@.service` |
| RF-DP04 | PG tuning CX22: shared_buffers=1GB, effective_cache=2GB, work_mem=64MB | Must | `provision-vps.sh:step6` |
| RF-DP05 | SSH hardening: porta 2222, root key-only, sem password/X11 | Must | `provision-vps.sh:step3` |
| RF-DP06 | Firewall: UFW deny incoming, allow SSH + node exporter + trusted IPs | Must | `ufw-rules.sh:1-177` |
| RF-DP07 | Fail2ban: jail PostgreSQL 54399, maxretry=5, bantime=3600s | Must | `fail2ban-jail.conf:1-90` |
| RF-DP08 | pg_hba: scram-sha-256, hostssl localhost, reject externo | Must | `pg_hba.conf:1-106` |
| RF-DP09 | Backup diário: pg_dump custom + gzip + Storage Box + retention 7+4 | Must | `backup-database.sh` |
| RF-DP10 | Escalonamento crawlers: offsets 30min, RandomizedDelaySec=300 | Should | systemd timer files |

🟢 CONFIRMADO — 42 arquivos deploy lidos.
