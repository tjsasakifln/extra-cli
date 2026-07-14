---
story_id: B2G-INFRA-04
title: "Backup automatizado + restore testado"
status: ready
priority: P0
risk_level: HIGH-RISK
effort: M
agent: "@devops"
epic: EPIC-MASTER-B2G-READINESS
phase: 1
depends_on: [B2G-INFRA-02]
blocks: [B2G-OPS-03]
---

# Story B2G-INFRA-04: Backup Automatizado + Restore Testado

## Problema

`scripts/backup-database.sh` (410 linhas) e `scripts/restore-database.sh` (255 linhas) existem mas **nunca foram executados com Storage Box real**. Backup só é considerado pronto após restore testado.

Scripts têm bugs menores: dupla compressão (pg_dump --compress=9 + pipe gzip), notificação loga WARN mesmo sem comando configurado, restore não suporta `--table` (documentado no runbook mas não implementado).

## Escopo

**IN:** Configurar Storage Box BX11 (100GB), executar backup completo, restaurar em banco staging, validar integridade, configurar systemd timer `extra-db-backup.timer`, documentar RPO/RTO.
**OUT:** Disaster recovery completo (B2G-OPS-03).

## Acceptance Criteria

1. **AC1:** `backup-database.sh` executa sem erro — dump gerado no Storage Box
2. **AC2:** `restore-database.sh` executa em banco `pncp_datalake_staging` — todos os dados restaurados
3. **AC3:** Row counts entre original e staging idênticos para todas as tabelas
4. **AC4:** `extra-db-backup.timer` ativo e schedule documentado
5. **AC5:** Backup retention funcionando (7 diários + 4 semanais)
6. **AC6:** Documento `docs/ops/backup.md` atualizado com RPO (24h) e RTO (<2h)

## Tasks

- [ ] Task 1: Adquirir Hetzner Storage Box BX11 (100GB)
- [ ] Task 2: Configurar SSH key para Storage Box
- [ ] Task 3: Preencher `/etc/backup-database.conf` com credenciais reais
- [ ] Task 4: Executar primeiro backup completo
- [ ] Task 5: Criar banco staging e executar restore
- [ ] Task 6: Validar row counts
- [ ] Task 7: Corrigir bugs menores (dupla compressão, warn log, --table flag)
- [ ] Task 8: Habilitar `extra-db-backup.timer`

## Definition of Done

- [ ] Backup→restore ciclo completo executado e validado
- [ ] Row counts idênticos entre original e staging
- [ ] Timer de backup diário ativo
- [ ] RPO e RTO documentados
- [ ] Bugs corrigidos nos scripts

## Arquivos Afetados

- `scripts/backup-database.sh`
- `scripts/restore-database.sh`
- `/etc/backup-database.conf`
- `deploy/systemd/extra-db-backup.service`
- `deploy/systemd/extra-db-backup.timer`
- `docs/ops/backup.md`
