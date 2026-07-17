# Requirements — HTTP Clients (top-level) (`clients`)

> Writer re-extração 2026-07-17 | confiança majoritária 🟢

## Propósito
Clientes HTTP compartilhados fora de crawl/clients.

## Requisitos funcionais
- RF-CL-01 Expor clientes reutilizáveis com timeout/retry 🟢
- RF-CL-02 Não duplicar credenciais hardcoded 🟢

## Requisitos não-funcionais
- NFR-01 Fail-closed: ausência de evidência ≠ sucesso 🟢
- NFR-02 Logs estruturados / reasons explícitos em degradação 🟢
- NFR-03 Artefatos raw fora do git (ADR-020) 🟢

## Fora de escopo
- UI web multi-tenant
- Alteração do denominador 1093

## Fontes
- `scripts/clients/`
