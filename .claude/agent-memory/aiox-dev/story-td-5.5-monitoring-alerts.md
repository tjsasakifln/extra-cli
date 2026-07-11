---
name: monitoring-alerts-td-5-5
description: Sistema de monitoramento e alertas — scripts collect-metrics, check-alerts, notify, health-dashboard
metadata:
  type: project
---

# Monitoring & Alerts System (TD-5.5)

Implementado na story TD-5.5: quatro scripts Python que formam o sistema de monitoramento.

**Arquivos criados:**
- `scripts/collect-metrics.py` — coleta metricas de crawl (ingestion_runs), cobertura (entity_coverage), status de backup (log parser). Output JSON estruturado.
- `scripts/check-alerts.py` — verifica condicoes: falhas consecutivas de crawl (3x), disco > 80%/90%, DB offline, Storage Box desmontado, backup desatualizado (>28h), API keys faltando. Dispara notificacoes via notify.py.
- `scripts/notify.py` — dispatch multi-canal: SMTP email e webhook Slack/Discord. Testado com --test.
- `scripts/health-dashboard.py` — dashboard CLI com resumo do sistema. Suporta --watch, --json, --summary.
- `deploy/systemd/extra-collect-metrics.{service,timer}` — coleta a cada 60min.
- `deploy/systemd/extra-check-alerts.{service,timer}` — verificacao a cada 15min.

**Configuracoes em settings.py:**
- `ALERT_CONSECUTIVE_FAILURES`, `ALERT_DISK_WARN_PCT`, `ALERT_DISK_CRIT_PCT`, `ALERT_BACKUP_MAX_HOURS`
- `NOTIFY_SMTP_*` (host, port, user, password, from, to, use_tls)
- `NOTIFY_WEBHOOK_URL`
- `COLLECT_METRICS_INTERVAL_MINUTES`

**Testes:** 39 testes unitarios em `tests/scripts/test_monitoring.py` (cobertura: notify, collect-metrics, check-alerts, health-dashboard).

**Documentacao:** `docs/ops/monitoring.md` — arquitetura, uso de cada script, configuracao de env vars, troubleshooting.

**Por que:** Sem metricas e alertas, falhas passam despercebidas por horas/dias ate usuario reportar. TD-OPS-03 do assessment tecnico.
