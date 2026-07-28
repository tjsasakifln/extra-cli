# ADR-024 — Campanha CONFENGE fail-closed com packages e dual-head SHA

- **Data:** 2026-07-28 (retroativo)
- **Status:** Aceito
- **Confiança:** 🟢

## Contexto
Liberação “commercial ready” exigia evidência reproduzível, freeze de inputs e status terminal auditável sem greenwash de CI.

## Decisão
Pipeline `ops/confenge_*` + gates + `confenge_final_status` como SSoT; packages com inventário SHA; distinção `pr_head` vs workflow merge SHA; freeze de inputs imutáveis.

## Consequências
- Muitos commits de rebind/re-freeze são esperados e operacionais.
- Dummy SHA / inventário desalinhado → FAIL.
- Artefatos de campanha não substituem DoD ACCEPTED sem controller.
