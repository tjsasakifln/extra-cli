# Story 001.1: Systemd Timers — 7 Faltantes

> **Story:** 001.1 | **Epic:** EPIC-001 | **Status:** InReview
> **Prioridade:** P1 | **Estimativa:** 4h
> **Executor:** @devops | **Quality Gate:** @architect | **Quality Gate Tools:** systemd, journalctl, bash

## Objetivo

Criar e ativar os 7 systemd timers faltantes para automação completa da ingestão de dados.

## Contexto

3/10 timers já existem em `deploy/systemd/`:
- `pncp-crawl-full.service` + `.timer` ✅
- `pncp-crawl-inc.service` + `.timer` ✅
- `coverage-report.service` + `.timer` ✅

7 timers precisam ser criados seguindo o mesmo padrão (systemd service + timer, `User=pi`, `WorkingDirectory=/home/pi/extra-consultoria`).

## Acceptance Criteria

- [x] **AC1:** Timer `dom-sc-crawl.timer` — DOM-SC crawler, 3x/dia (06:00, 14:00, 22:00 UTC)
- [x] **AC2:** Timer `pcp-crawl.timer` — PCP crawler, 2x/dia (06:30, 14:30 UTC)
- [x] **AC3:** Timer `compras-gov-crawl.timer` — ComprasGov crawler, 1x/dia (07:00 UTC)
- [x] **AC4:** Timer `pncp-contracts.timer` — PNCP contracts crawler, Mon/Wed/Fri 06:00 UTC
- [x] **AC5:** Timer `pncp-enrich.timer` — Enricher pipeline, 1x/dia (08:00 UTC)
- [x] **AC6:** Timer `pncp-purge.timer` — Data purge (>400 dias), 1x/dia (07:00 UTC)
- [x] **AC7:** Timer `pncp-report-weekly.timer` — Weekly report generation, Mon 07:00 UTC
- [x] **AC8:** Todos os timers ativos via `deploy/install.sh` (loop enable+start para 10 timers)
- [x] **AC9:** Logs configurados com `journalctl` (StandardOutput=journal, StandardError=journal)
- [x] **AC10:** OnFailure=notify via `onfailure@.service` template — webhook via curl, requer WEBHOOK_URL no `.env`

## Padrão de Service

```ini
# deploy/systemd/{crawler}-crawl.service
[Unit]
Description={Crawler Name} — Extra Consultoria
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=pi
WorkingDirectory=/home/pi/extra-consultoria
ExecStart=/home/pi/extra-consultoria/.venv/bin/python3 -m scripts.crawl.{crawler_module}
StandardOutput=journal
StandardError=journal
EnvironmentFile=/home/pi/extra-consultoria/.env
```

## Padrão de Timer

```ini
# deploy/systemd/{crawler}-crawl.timer
[Unit]
Description={Crawler Name} Timer — Extra Consultoria

[Timer]
OnCalendar={schedule}
RandomizedDelaySec=300
Persistent=true

[Install]
WantedBy=timers.target
```

## Schedules

| Timer | OnCalendar | Notas |
|-------|-----------|-------|
| dom-sc-crawl | `*-*-* 06,14,22:00:00` | DOM-SC atualiza manhã/tarde/noite |
| pcp-crawl | `*-*-* 06:30,14:30:00` | Offset 30min do DOM-SC para não colidir |
| compras-gov-crawl | `*-*-* 07:00:00` | Atualização diária |
| pncp-contracts | `Mon,Wed,Fri *-*-* 06:00:00` | Contratos não mudam todo dia |
| pncp-enrich | `*-*-* 08:00:00` | Após coletas da manhã |
| pncp-purge | `*-*-* 07:00:00` | Antes das coletas principais |
| pncp-report-weekly | `Mon *-*-* 07:00:00` | Após weekend |

## File List

- `deploy/systemd/dom-sc-crawl.service`
- `deploy/systemd/dom-sc-crawl.timer`
- `deploy/systemd/pcp-crawl.service`
- `deploy/systemd/pcp-crawl.timer`
- `deploy/systemd/compras-gov-crawl.service`
- `deploy/systemd/compras-gov-crawl.timer`
- `deploy/systemd/pncp-contracts.service`
- `deploy/systemd/pncp-contracts.timer`
- `deploy/systemd/pncp-enrich.service`
- `deploy/systemd/pncp-enrich.timer`
- `deploy/systemd/pncp-purge.service`
- `deploy/systemd/pncp-purge.timer`
- `deploy/systemd/pncp-report-weekly.service`
- `deploy/systemd/pncp-report-weekly.timer`
- `deploy/install.sh` (*) — update para copiar novos timers

## Riscos

| Risco | Impacto | Mitigação |
|-------|---------|-----------|
| Timer conflitar com outro job | Duas coletas simultâneas sobrecarregam VPS | RandomizedDelaySec=300 em todos os timers, offset escalonado (30min entre fontes) |
| Falha silenciosa sem alerta | Dados param de entrar, ninguém percebe | OnFailure= notifica via webhook; `systemctl list-timers --failed` no coverage-report |
| Script Python não encontrar dependência | Timer falha na primeira execução | `WorkingDirectory` + `EnvironmentFile` corretos; `ExecStartPre=/usr/bin/test -f .venv/bin/python3` |
| Timer habilitado mas VPS reiniciado | Serviços não sobem após reboot | `WantedBy=timers.target` + `systemctl enable` garante restart |

## Dependencies

- Crawlers existentes já funcionais (chamada via `python3 -m scripts.crawl.{module}`)
- Environment `.env` configurado no Hetzner VPS

## DoD

- [x] 7 serviços + 7 timers + template onFailure criados em `deploy/systemd/` (15 arquivos)
- [x] `deploy/install.sh` atualizado com loop enable+start para todos os 10 timers
- [ ] Todos os 10 timers listados em `systemctl list-timers` no Hetzner (pendente execução no VPS)
- [ ] Primeira execução de cada timer sem erro (verificar `journalctl -u {service} --since "5 min ago"`) (pendente VPS)
- [ ] `systemctl status {timer}` mostra `active (waiting)` para cada um (pendente VPS)

## 🤖 CodeRabbit Integration

- **Story Type:** Infrastructure/Deploy
- **Complexity:** Low
- **Primary Agent:** @devops
- **Self-Healing:** light mode (2 iterations, 30min, CRITICAL only)
- **Severity Behavior:**
  - CRITICAL: auto_fix
  - HIGH: auto_fix (iteration < 2), else document_as_debt
  - MEDIUM: document_as_debt
  - LOW: ignore
- **Quality Gates:**
  - [ ] Pre-Commit (@devops) — systemd syntax check, file permissions, path validation
  - [ ] Pre-PR (@devops) — timer schedule sanity, idempotency check
- **Focus Areas:** systemd unit syntax, file permissions, timer schedule conflicts, idempotency

## Change Log

| Data | Versão | Mudança | Autor |
|------|--------|---------|-------|
| 2026-07-10 | 1.0.0 | Story criada — EPIC-001 | @pm |
| 2026-07-10 | 1.1.0 | Validação PO: adicionados Status, executor, riscos, CodeRabbit, Change Log | @po |
| 2026-07-10 | 1.1.0 | Validated GO (10/10) — Status: Draft → Ready | @po |
| 2026-07-10 | 1.2.0 | Implementação: 14 arquivos systemd + template onFailure + install.sh atualizado — Status: Ready → InReview | @devops |
