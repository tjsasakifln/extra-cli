# Requirements — Extra Ledger (`extra_ledger`)

> Writer re-extração 2026-07-17 | confiança majoritária 🟢

## Propósito
Ledger operacional de decisões/evidências de sessão do consultor.

## Requisitos funcionais
- RF-EL-01 CLI deve ler/gravar ledger de decisões 🟢
- RF-EL-02 Integrar com workspace decide 🟢

## Requisitos não-funcionais
- NFR-01 Fail-closed: ausência de evidência ≠ sucesso 🟢
- NFR-02 Logs estruturados / reasons explícitos em degradação 🟢
- NFR-03 Artefatos raw fora do git (ADR-020) 🟢

## Fora de escopo
- UI web multi-tenant
- Alteração do denominador 1093

## Fontes
- `scripts/extra_ledger/`
