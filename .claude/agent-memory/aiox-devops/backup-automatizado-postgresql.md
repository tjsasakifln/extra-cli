---
name: backup-automatizado-postgresql
description: PostgreSQL backup system with pg_dump, Hetzner Storage Box, retention 7+4
metadata:
  type: project
---

Backup automatizado do PostgreSQL DataLake implementado e versionado (Story TD-0.1).

**O que foi criado:**
- `scripts/backup-database.sh` -- pg_dump --format=custom + gzip, sshfs mount to Hetzner Storage Box, retention 7 diarios + 4 semanais, log estruturado JSON, notificacao em falha, lock file, dry-run
- `scripts/restore-database.sh` -- pg_restore com modos completo/schema-only/data-only/list, criacao automatica de database
- `docs/ops/backup.md` -- documentacao completa: arquitetura, instalacao, systemd service/timer templates, retention policy, restore procedure, monitoramento, FAQ
- `.env.example` -- adicionadas variaveis BACKUP_*

**Systemd files (no servidor, templates na doc):**
- `extra-db-backup.service` -- Type=oneshot, Nice=19, Restart=on-failure (3 tentativas, 5min intervalo)
- `extra-db-backup.timer` -- OnCalendar=06:00 UTC (03:00 BRT), RandomizedDelaySec=300

**ACs implementados:** 9/9
**Status:** InReview (pendente deploy no servidor + primeiro backup manual)

**Why:** TD-DB-15 CRITICAL -- ausencia total de backup strategy. Risco de perda total do DataLake com 2+ anos de crawling.

**How to apply:** Referenciar ao configurar backup em novos ambientes. Usar scripts em scripts/ para operacoes manuais. Ver docs/ops/backup.md para procedimento completo de instalacao.
