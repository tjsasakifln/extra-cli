# Story: Recover PNCP contracts freshness cadence and dispose live residuals

Status: InProgress
Risk: HIGH-RISK (produção, timer, backup/restore)
Campaign: CONFENGE-PNCP-FRESHNESS-RECOVERY-AND-SOAK-01
Issues: #241 #248 #319 #277 (disposition); reuse PR #443 / #444

## Problem

A cadence Mon/Wed/Fri não fecha janela em ≤24h. PR #444 mediu `FRESHNESS_DEGRADED` (lag ~28,8h, `UNCLOSED_CURRENT_WINDOW`). Falta remediar o timer e fechar residuals live sem redo de backfill.

## Scope IN

- Integrar #443/#444; remediar `pncp-contracts.timer` para 4h (fallback 6h) com timezone explícita
- `LOCK_BUSY` ≠ freshness success; catch-up via Persistent + próximo slot
- Detectabilidade via JSON + check-alerts + journal
- Canário live, disposition #241/#319, soak #248 só com recoverability

## Scope OUT

- Backfill histórico #249; novos adapters; crawler rebuild; Kafka/K8s; `VPS_OPERATIONAL`

## Acceptance

1. Given host capacity ~21 min/run, When o timer shipped é lido, Then max inter-run é 4h e `America/Sao_Paulo` é explícito.
2. Given `last_exec_status=75`, When classifica, Then não `FRESH` (`LOCK_BUSY_NO_CLOSE`).
3. Given cadence 4h, When o produtor emite SLO, Then `CADENCE_CANNOT_MEET_24H` está ausente e `sustainable_hard_guardrail=true`.
