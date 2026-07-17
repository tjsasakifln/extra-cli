# Requirements — Ops Resilience (`ops`)

> Writer re-extração 2026-07-17 | confiança majoritária 🟢

## Propósito
Ciclo resiliente pré-VPS, health, schema audit, validate systemd (ADR-021).

## Requisitos funcionais
- RF-OP-01 run_cycle deve executar adapters PNCP/CIGA/SC em live ou fixture 🟢
- RF-OP-02 Health e schema_audit devem falhar fechado em inconsistências críticas 🟢
- RF-OP-03 validate_systemd deve checar units deploy 🟢

## Requisitos não-funcionais
- NFR-01 Fail-closed: ausência de evidência ≠ sucesso 🟢
- NFR-02 Logs estruturados / reasons explícitos em degradação 🟢
- NFR-03 Artefatos raw fora do git (ADR-020) 🟢

## Fora de escopo
- UI web multi-tenant
- Alteração do denominador 1093

## Fontes
- `scripts/ops/`
- `scripts/crawl/resilience/`
