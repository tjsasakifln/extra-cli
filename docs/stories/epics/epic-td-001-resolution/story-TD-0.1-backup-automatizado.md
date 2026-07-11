# Story TD-0.1: Setup Backup Automatizado

**Status:** InReview
**Epic:** EPIC-TD-001
**Executor:** @devops
**Quality Gate:** @architect
**Quality Gate Tools:** [coderabbit]
**Fase:** 0 -- Emergencia
**Estimativa:** 4 horas
**Prioridade:** P1

## Description

Implementar backup automatizado do banco PostgreSQL (4.1 GB, Hetzner VPS) que atualmente nao possui nenhum mecanismo de backup. Este e o debito mais critico do sistema -- risco de perda total do DataLake com 2+ anos de crawling.

Criar script de pg_dump com formato custom, agendar via systemd timer, configurar retention de 7 backups diarios + 4 semanais, e armazenar em Hetzner Storage Box.

## Business Value

Backup automatizado e a unica barreira contra perda total do DataLake com 2+ anos de dados de crawling de fornecedores. Sem backup, qualquer falha de hardware no VPS, erro humano ou corrupcao de dados resulta em perda irreversivel de dados insubstituiveis. Impacto estimado: meses de trabalho perdidos e impossibilidade de recuperar historico de licitacoes.

## Acceptance Criteria

- [x] AC1: Dado que o script backup-database.sh esta instalado no servidor, Quando executado manualmente ou via timer, Entao deve produzir um dump custom do PostgreSQL com formato --format=custom
- [x] AC2: Dado que o dump foi gerado, Quando o script finalizar a compressao, Entao o arquivo deve estar comprimido com gzip e nomeado com timestamp no formato YYYY-MM-DD
- [x] AC3: Dado que o systemd timer esta configurado, Quando atingir o horario agendado (03:00 BRT), Entao o servico de backup deve ser executado automaticamente
- [x] AC4: Dado que existem mais de 7 backups diarios no diretorio, Quando a rotina de retention for executada, Entao deve manter apenas os 7 backups diarios mais recentes
- [x] AC5: Dado que existem mais de 4 backups semanais no diretorio, Quando a rotina de retention for executada, Entao deve manter apenas os 4 backups semanais mais recentes
- [x] AC6: Dado que a Hetzner Storage Box esta montada via sshfs, Quando o backup for concluido, Entao o arquivo deve ser copiado para o diretorio de destino na Storage Box
- [x] AC7: Dado que um backup foi executado, Quando o processo terminar (sucesso ou falha), Entao deve ser gerado um log com status, tamanho do arquivo e duracao da operacao
- [x] AC8: Dado que ocorreu uma falha no backup, Quando o script detectar o erro, Entao deve emitir notificacao via mecanismo definido (integravel com alertas futuros)
- [x] AC9: Dado que o script restore-database.sh existe no repositorio, Quando executado com um arquivo de backup valido, Entao deve restaurar o banco conforme documentacao

## Scope

### IN
- Script de backup com pg_dump
- Systemd service + timer
- Configuracao de retention
- Montagem da Storage Box
- Script de restore basico

### OUT
- Backup para cloud (S3, Backblaze, etc.)
- PITR (Point-in-Time Recovery)
- Replicacao de banco (standby)
- Teste automatizado de restore (manual por enquanto)

## Dependencies

- Bloqueado por: NONE
- Bloqueia: TD-2.1 (backup como pre-requisito para migracao de schema), TD-0.2 (deve ser feito primeiro ou em paralelo)
- Acesso ao Hetzner VPS e Storage Box necessario

## Risks

| Risco | Probabilidade | Impacto | Mitigacao |
|-------|---------------|---------|-----------|
| Backup corrompido sem deteccao por falta de teste de restore automatizado | MEDIA | ALTO | Teste manual de restore conforme DoD; automatizar na expansao |
| Storage Box indisponivel durante janela de backup | BAIXA | MEDIO | Script deve logar falha e tentar novamente; notificacao para acao manual |
| Espaco em disco insuficiente para retention 7+4 | BAIXA | BAIXO | Estimar tamanho total (~11-22 GB), monitorar uso e alertar |

## Technical Notes

Referencia ao assessment: TD-DB-15 (CRITICAL) -- Ausencia total de backup strategy
- Metodo: pg_dump --format=custom (compressao nativa, restore seletivo)
- Retention: 7 diarios + 4 semanais (total ~11 dumps)
- Storage: Hetzner Storage Box via sshfs ou rsync over SSH
- Timer: systemd diario, horario sugerido 03:00 BRT
- Tamanho estimado por dump: 1-2 GB (comprimido)

## Definition of Done

- [x] Script de backup criado e versionado
- [ ] Systemd timer registrado no servidor (pendente — deploy manual)
- [ ] Primeiro backup executado com sucesso (pendente — execucao no servidor)
- [x] Script de restore documentado
- [ ] Verificacao manual do arquivo de backup (pendente — apos primeiro backup)

## File List

- `scripts/backup-database.sh` (novo)
- `scripts/restore-database.sh` (novo)
- `/etc/systemd/system/extra-db-backup.service` (no servidor)
- `/etc/systemd/system/extra-db-backup.timer` (no servidor)
- `docs/ops/backup.md` (novo) -- documentacao do procedimento

## Change Log

| Data | Mudanca | Autor |
|------|---------|-------|
| 2026-07-11 | Story criada | @pm |
| 2026-07-11 | 1.0.1 | Validated GO (10/10) — Revalidated Ready — Adicionados: Executor, Quality Gate, Prioridade, Business Value, Risks; ACs convertidas para GWT | @po |
| 2026-07-11 | Implementacao: backup-database.sh, restore-database.sh, docs/ops/backup.md, config .env.example. Status: Ready → InReview. 9/9 ACs implementados. | @devops |
