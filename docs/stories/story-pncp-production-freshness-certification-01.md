# Story: PNCP contracts production freshness certification

Status: Ready
Risk: HIGH-RISK (produção, dados, timer)
Campaign: CONFENGE-PNCP-PRODUCTION-FRESHNESS-CERTIFICATION-01
Issues: #241 #248 #319 (residual); #351/#285/#341/#343 via PR #443

## Problem

O backfill histórico de contratos PNCP está concluído. Falta prova operacional auditável de que o incremental na VPS/Netcup atualiza a base com freshness mensurável, checkpoints duráveis e falha explícita.

## Scope IN

- Contrato versionado `PNCP_CONTRACT_FRESHNESS/1.0` sobre o path incremental existente
- Integração fail-closed em `check-alerts`
- Testes focados (paginação, ZERO, HTTP, schema, replay, checkpoint, UNKNOWN ≠ zero)
- Relatório + runbook + artefato; canário live se o host responder
- Comentários nas issues existentes (sem duplicatas)

## Scope OUT

- Refazer backfill; novos adapters; cobertura nacional perfeita
- Auto-declarar `VPS_OPERATIONAL`; completar soak de 7 dias
- Reimplementar PR #443; Kafka/K8s; web-cfg/Warmbly/SmartLic

## Acceptance (Given/When/Then)

1. Given snapshot sem evidência, When o produtor classifica, Then status `UNKNOWN` (nunca `FRESH`).
2. Given janela incompleta ou lag > 24h, When classifica, Then não `FRESH` (`STALE`).
3. Given lag > 6h e ≤ 24h com janela fechada, When classifica, Then `DEGRADED`.
4. Given timer Mon/Wed/Fri, When o artefato é emitido, Then `sustainable_operational_target=false` e não afirma aderência a 6h.
5. Given checkpoint no worktree em produção, When resolve, Then recusa. Replay não duplica. Restart retoma a próxima unidade.

## DoD

Veredito nomeado `FRESHNESS_CERTIFIED` | `FRESHNESS_DEGRADED` | `BLOCKED_ON_LIVE_HOST_EVIDENCE`. Sem selo `VPS_OPERATIONAL`.
