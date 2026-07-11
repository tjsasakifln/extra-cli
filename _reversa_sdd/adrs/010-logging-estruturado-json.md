# ADR-010: Logging Estruturado JSON com Correlation ID

**Status:** ✅ Implementado
**Data:** 2026-07-11
**Epic:** EPIC-TD-001 / Story TD-5.1
**Commit:** `e9729e1`

## Contexto

Logs do sistema eram não-estruturados (print statements + logging básico), dificultando:
- Debug de falhas em crawlers que rodam em horários diferentes (20 systemd timers)
- Correlação de eventos em pipelines multi-estágio (7 stages do Intel)
- Monitoramento automatizado (scripts de alerta precisavam parsear texto livre)

## Decisão

**Logging JSON estruturado com `correlation_id` baseado em contextvars (PEP 567).**

**Formato de saída:**
```json
{
  "timestamp": "2026-07-11T06:00:00.123Z",
  "level": "INFO",
  "module": "crawl.pncp",
  "correlation_id": "a1b2c3d4e5f6",
  "message": "Crawl concluído",
  "extra_data": {"source": "pncp", "fetched": 1234},
  "exc_info": null
}
```

**Propriedades:**
- `correlation_id` é um contextvar — thread-safe e async-safe
- 12-char hex gerado automaticamente se não definido
- Rotação de arquivos em produção: 10MB por arquivo, 5 backups
- Fallback para stderr se rotação falhar
- Fallback para string plana se JSON serialization falhar

## Evidência

🟢 CONFIRMADO — `config/logging_config.py:1-199`.
🟢 CONFIRMADO — `set_correlation_id()`, `get_correlation_id()`, `reset_correlation_id()`.
🟢 CONFIRMADO — `docs/td-001/logging.md` documenta a migração de print → logging.

## Alternativas Consideradas

- **structlog:** Rejeitado — dependência adicional para funcionalidade que 199 linhas resolvem.
- **OpenTelemetry:** Rejeitado — overkill para single-instance VPS. Adicionar quando houver múltiplos serviços.
- **Manter print statements:** Rejeitado — impossibilita monitoramento automatizado e debugging cross-timer.

## Consequências

- **Positivo:** Scripts de alerta (`check-alerts.py`) podem fazer parse determinístico de JSON.
- **Positivo:** `correlation_id` permite rastrear um edital do crawl ao PDF final.
- **Positivo:** Rotação previne disco cheio por logs (10MB × 5 = 50MB máximo).
- **Negativo:** Logs JSON são menos legíveis para `journalctl -u` direto. Mitigação: `--json` flag opcional, fallback texto puro para desenvolvimento.
