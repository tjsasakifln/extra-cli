# Requirements — Workspace CLI Facade (`workspace`)

> Writer re-extração 2026-07-17 | confiança majoritária 🟢

## Propósito
Interface operacional única do consultor (ADR-017): fila do dia, coverage dual-metric, decide, scaffolds.

## Requisitos funcionais
- RF-WS-01 Comando today deve montar seções new/near_deadline/review/source_health/expiring 🟢
- RF-WS-02 Offline PG deve degradar para session JSON com UNAVAILABLE/EMPTY 🟢
- RF-WS-03 coverage deve expor M1 e M2 lado a lado 🟢
- RF-WS-04 decide deve gravar ledger/overrides sem inventar GO 🟢
- RF-WS-05 scaffold edital/proposta default REVIEW 🟢

## Requisitos não-funcionais
- NFR-01 Fail-closed: ausência de evidência ≠ sucesso 🟢
- NFR-02 Logs estruturados / reasons explícitos em degradação 🟢
- NFR-03 Artefatos raw fora do git (ADR-020) 🟢

## Fora de escopo
- UI web multi-tenant
- Alteração do denominador 1093

## Fontes
- `scripts/workspace/`
- `docs/architecture/adr/ADR-017-workspace-cli-facade.md`
