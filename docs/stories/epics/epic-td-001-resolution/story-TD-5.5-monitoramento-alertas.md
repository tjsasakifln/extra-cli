# Story TD-5.5: Monitoramento e Alertas

**Status:** Done
**Epic:** EPIC-TD-001
**Executor:** @dev
**Quality Gate:** @architect
**Quality Gate Tools:** [coderabbit, pytest]
**Fase:** 5 -- Resiliencia & Observabilidade
**Estimativa:** 4 horas
**Prioridade:** P1

## Description

Expandir a observabilidade para incluir metricas operacionais e alertas proativos, complementando o logging estruturado da TD-5.1 e o healthcheck da TD-4.2.

Implementar:
1. Metricas de cobertura de crawl (quantos orgaos crawlados por dia, taxa de sucesso)
2. Alertas para falhas de crawl, backup, e expiracao de API keys
3. Dashboard simples via script ou integracao com ferramenta de monitoramento
4. Notificacoes (email, webhook) para eventos criticos

## Business Value

Sem metricas e alertas, falhas no sistema passam despercebidas por horas ou dias ate que um usuario reporte. Monitoramento proativo permite resposta rapida a incidentes, minimizando downtime e perda de dados. Alertas para expiracao de API keys previnem interrupcoes no servico. O dashboard CLI da visibilidade immediata do estado do sistema sem necessidade de ferramentas externas.

## Acceptance Criteria

- [x] AC1: Dado que os crawlers estao em execucao, Quando as metricas de cobertura sao coletadas, Entao os dados de orgaos crawlados por dia e taxa de sucesso/falha sao armazenados e consultaveis via script
- [x] AC2: Dado que o backup diario falha, Quando o script de alertas e executado, Entao uma notificacao e disparada informando a falha (baseado nos logs da TD-0.1)
- [x] AC3: Dado que um crawler falha N vezes consecutivas, Quando o limiar configurado e atingido, Entao um alerta de falha recorrente e disparado
- [x] AC4: Dado que uma API key esta proxima da expiracao (conforme configurado na TD-4.1), Quando o script de verificacao e executado, Entao um alerta preventivo e disparado
- [x] AC5: Dado um evento critico detectado, Quando o script de notificacao e acionado, Entao uma mensagem e enviada via email ou webhook (Slack/Discord) com detalhes do evento
- [x] AC6: Dado o comando `python scripts/health-dashboard.py` executado, Quando o dashboard CLI e chamado, Entao um resumo do estado do sistema e exibido (orgaos crawlados, status de backup, alertas ativos)
- [x] AC7: Dado que o sistema de monitoramento esta completo, Quando a documentacao e criada, Entao ela descreve como coletar metricas, interpretar alertas e configurar notificacoes

## Scope

### IN
- Metricas de cobertura
- Alertas para falhas
- Notificacoes
- Dashboard CLI basico

### OUT
- Integracao com PagerDuty, OpsGenie, etc.
- Dashboard web/Grafana
- Tracing distribuido

## Dependencies

- Bloqueado por: TD-5.1 (logging estruturado como base), TD-4.1 (API key renewal), TD-0.1 (backup logs)
- Bloqueia: NONE

## Risks

| Risco | Probabilidade | Impacto | Mitigacao |
|-------|---------------|---------|-----------|
| Alertas falsos positivos causam dessensibilizacao da equipe | ALTA | MEDIO | Configurar limiares conservadores; revisar alertas apos primeira semana |
| Notificacoes nao chegam por configuracao incorreta de SMTP/webhook | MEDIA | ALTO | Testar notificacao apos configuracao; log de envio |
| Dashboard CLI mostra dados inconsistentes | BAIXA | BAIXO | Validar metricas contra dados brutos do banco |
| Cobertura de metricas insuficiente para diagnostico | MEDIA | MEDIO | Planejar metricas em colaboracao com operadores; iterar |

## Technical Notes

Referencia ao assessment: TD-OPS-03 (MEDIUM) -- Observabilidade expandida -- 4h
- Baseado no logging estruturado da TD-5.1
- Healthcheck basico da TD-4.2 como entrada
- Notificacao via SMTP (email) ou webhook (Slack, Discord)
- Metricas podem ser coletadas via script Python ou SQL queries

## Definition of Done

- [x] Metricas de coleta funcionais
- [x] Alertas configurados e testados
- [x] Notificacao enviada em evento de teste
- [x] Dashboard CLI funcional
- [x] Documentacao do sistema

## File List

- `scripts/collect-metrics.py` (novo)
- `scripts/check-alerts.py` (novo) -- verificacao periodica de alertas
- `scripts/notify.py` (novo) -- envio de notificacoes
- `scripts/health-dashboard.py` (novo) -- dashboard CLI (AC6)
- `docs/ops/monitoring.md` (novo)
- `config/settings.py` (modificado -- config de alertas/notificacao)
- `deploy/systemd/extra-collect-metrics.service` (novo)
- `deploy/systemd/extra-collect-metrics.timer` (novo)
- `deploy/systemd/extra-check-alerts.service` (novo)
- `deploy/systemd/extra-check-alerts.timer` (novo)
- `tests/scripts/test_monitoring.py` (novo)
- `plan/self-critique-TD-5.5.json` (novo)

## Change Log

| Data | Mudanca | Autor |
|------|---------|-------|
| 2026-07-11 | Story criada | @pm |
| 2026-07-11 | Validated GO (10/10) — adicionado Business Value, Risks, Executor, QG, Prioridade; ACs convertidas para Given/When/Then | @po |
| 2026-07-11 | 1.0.0 | Development complete — Status: Ready → InProgress → InReview | @dev |
| 2026-07-11 | 1.0.1 | QA Gate CONCERNS — Status: InReview → Done — 4 low-severity issues documented (MNT-001 thru MNT-004), 39/39 tests passing | @qa |
| 2026-07-11 | 1.0.2 | MNT fixes applied — MNT-001 (unused imports removed), MNT-002 (f-strings converted), MNT-003 (l -> line), MNT-004 (lines broken) — Status: Done → InReview for re-validation | @dev |
| 2026-07-11 | 1.0.3 | QA Gate PASS — Status: InReview → Done — all 4 MNT issues resolved, ruff 0 errors, 39/39 tests | @qa |

## QA Results

### Review Date: 2026-07-11
### Reviewed By: Quinn (Guardian)

| Check | Result | Details |
|-------|--------|---------|
| 1. Code Review | PASS | Clean code, consistent patterns, good error handling. Minor lint issues: unused imports, f-string placeholders, line length, ambiguous variable |
| 2. Unit Tests | PASS | 39/39 tests passing. Coverage of all 4 modules (notify, collect-metrics, check-alerts, health-dashboard) |
| 3. Acceptance Criteria | PASS | All 7 ACs verified as implemented (AC1-AC7) |
| 4. No Regressions | PASS | config/settings.py extended (not modified); new systemd units alongside existing ones; no existing functionality affected |
| 5. Performance | PASS | Acceptable — subprocess calls have 10-30s timeouts; periodic execution via systemd timers |
| 6. Security | PASS | No hardcoded credentials; all config via env vars; SMTP uses STARTTLS; webhook payloads safe |
| 7. Documentation | PASS | docs/ops/monitoring.md covers all 4 components, config reference, troubleshooting, systemd setup |

### Issues Found

| ID | Severity | Finding | Location |
|----|----------|---------|----------|
| MNT-001 | low | Unused imports: subprocess (collect-metrics.py), logging (notify.py) | scripts/collect-metrics.py:25, scripts/notify.py:25 |
| MNT-002 | low | F-strings without placeholders used instead of plain strings | scripts/health-dashboard.py:300,313 |
| MNT-003 | low | Ambiguous variable name 'l' should be more descriptive | scripts/collect-metrics.py:225 |
| MNT-004 | low | Line length exceeds 100-char limit in several places | scripts/check-alerts.py:84,543,544; scripts/notify.py:171,267 |

### Gate Status

Gate: CONCERNS -> docs/qa/gates/story-TD-5.5-monitoramento-alertas.yml

### Re-validation (MNT Fixes) — 2026-07-11

All 4 previous MNT issues verified as resolved:

| ID | Status | Verification |
|----|--------|-------------|
| MNT-001 | FIXED | `subprocess` (collect-metrics.py) and `logging` (notify.py) imports removed — confirmed 0 occurrences |
| MNT-002 | FIXED | f-strings without placeholders converted to plain strings (lines 300, 313 health-dashboard.py) |
| MNT-003 | FIXED | Variable `l` renamed to descriptive name (collect-metrics.py line 225) — grep confirms 0 ambiguous usage |
| MNT-004 | FIXED | Lines exceeding 100 chars wrapped — current lines at positions 84,543,544 (check-alerts.py) and 171,267 (notify.py) all within limits |

### Quality Checks (Re-validation)

| Check | Result | Details |
|-------|--------|---------|
| 1. Code Review (MNT fixes) | PASS | All 4 MNT issues resolved. ruff check: 0 errors (project conventions N999/E402 excluded as project-wide false positives) |
| 2. Unit Tests | PASS | 39/39 tests passing — all notify, collect-metrics, check-alerts, health-dashboard tests green |
| 3. Acceptance Criteria | PASS | All 7 ACs verified (AC1-AC7) — no changes needed to implementation |
| 4. No Regressions | PASS | config/settings.py extended only; new systemd units alongside existing; no existing function affected |
| 5. Performance | PASS | Timeouts at 10-15s for all subprocess/network calls; systemd timer-based execution |
| 6. Security | PASS | No hardcoded credentials; SMTP_USER/SMTP_PASSWORD from env vars; SMTP uses STARTTLS |
| 7. Documentation | PASS | docs/ops/monitoring.md (326 lines) covers all 4 components with config reference and troubleshooting |

### Gate Status

Gate: PASS -> docs/qa/gates/story-TD-5.5-monitoramento-alertas.yml
