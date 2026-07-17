---
story_id: B2G-E3.S3
title: "Scheduler permanente + prova journalctl/last_success"
status: Draft
priority: P0
risk_level: HIGH-RISK
effort: L
agent: "@devops"
epic: EPIC-B2G-OPERATIONAL-PLATFORM
vertical: E3
depends_on: [B2G-E3.S1, B2G-E3.S2]
blocks: [B2G-E4.S2]
adr: [ADR-021]
---

# Story B2G-E3.S3: Scheduler permanente com prova

## Contexto

Timers no repo ≠ operação permanente. Precisamos de **evidência**: units ativas + last_success por fonte P0/P1.

## Acceptance Criteria

1. **Given** ambiente alvo (VPS ou host ops acordado), **When** timers P0 (PNCP inc) ativos, **Then** `systemctl list-timers` mostra next/last.
2. **Given** 24h de operação (ou janela acordada), **When** consulta evidence, **Then** last_success dentro do SLA ou alerta aberto.
3. **Given** falha de job, **When** OnFailure, **Then** notificação/log acionável (template unificado).

## Riscos

Credenciais/VPS — se indisponível, documentar BLOCKED com evidência de tentativa (não marcar Done).

## DoD

- [ ] Runbook + evidência stamp docs/ops (sem raw)
- [ ] Nomenclatura timer unificada no path ativado

## Comandos de validação

```bash
# Em host ops:
systemctl list-timers 'extra-*'
journalctl -u extra-crawl-pncp.service -n 30
python scripts/opportunity_intel/cli.py source-health
```

## Change Log

| Data | Autor | Nota |
|------|-------|------|
| 2026-07-17 | Morgan (PM) | Draft |
| 2026-07-17 | Dex (Dev) | Units e timers futuros validados estaticamente; story permanece Draft/BLOCKED até host, ativação, reboot e prova de 24 h. |
