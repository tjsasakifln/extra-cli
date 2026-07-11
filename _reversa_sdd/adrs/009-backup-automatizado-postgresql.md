# ADR-009: Backup Automatizado PostgreSQL com Hetzner Storage Box

**Status:** ✅ Implementado
**Data:** 2026-07-11
**Epic:** EPIC-TD-001 / Story TD-0.1
**Commit:** `12887a5`

## Contexto

O banco de dados PostgreSQL contém:
- ~199K licitações (pncp_raw_bids) — insubstituível, fonte é API externa com rate limit
- ~3.69M contratos históricos (pncp_supplier_contracts) — dados de inteligência competitiva
- 2.085 entes públicos SC (sc_public_entities) — catálogo curado manualmente

Perder esses dados significaria weeks de re-crawling e perda de histórico de cobertura. Não existia mecanismo de backup além do storage da VPS.

## Decisão

**Backup diário via pg_dump custom format + rsync para Hetzner Storage Box**, orquestrado por systemd timer.

**Estratégia de retenção 7+4:**
- 7 backups diários (última semana)
- 4 backups semanais (último mês, domingos)

**Tecnologia:**
- `pg_dump --format=custom --compress=0` (compressão externa com gzip para melhor controle)
- Montagem Storage Box via `sshfs` (mesmo datacenter Hetzner, latência <1ms)
- Lock file para evitar concorrência entre execuções
- Notificação em falha (webhook + systemd OnFailure)

## Evidência

🟢 CONFIRMADO — `db/backup-database.sh` com pg_dump, gzip, sshfs mount, retention logic.
🟢 CONFIRMADO — `deploy/systemd/extra-db-backup.service` + `.timer` (diário 06:00 UTC).
🟢 CONFIRMADO — `docs/ops/backup.md` documenta arquitetura, restore, troubleshooting.

## Alternativas Consideradas

- **pg_dump plain SQL:** Rejeitado — mais lento para restore, sem compressão paralela.
- **WAL-G / pgBackRest:** Rejeitado — complexidade excessiva para single-instance single-DB.
- **Supabase managed backups:** Rejeitado — projeto usa PostgreSQL self-hosted, sem dependência de cloud provider.
- **Cron em vez de systemd timer:** Rejeitado — systemd já é o scheduler padrão do projeto (37 timers).

## Consequências

- **Positivo:** RPO de 24h (backup diário). RTO estimado < 30min (restore local).
- **Positivo:** Storage Box é externo à VPS — sobrevive a falha completa do servidor.
- **Negativo:** sshfs pode desconectar. Mitigação: remount automático no script + alerta em falha.
- **Risco:** Backup em andamento durante crawler pesado pode afetar performance. Mitigação: horário 06:00 UTC, antes dos crawlers principais (pre-PNCP full às 05:00, pós-backup às 07:00+).
