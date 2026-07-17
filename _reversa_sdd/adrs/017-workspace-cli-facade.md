# ADR-017 — Workspace CLI Facade (retroativo Reversa)

| Campo | Valor |
|-------|-------|
| **Status** | Accepted |
| **Data** | 2026-07-17 |
| **Fonte primária** | `docs/architecture/adr/ADR-017-workspace-cli-facade.md` |
| **Implementação** | `scripts/workspace/` |
| **Confiança** | 🟢 CONFIRMADO |

## Contexto
Fragmentação de CLIs impede rotina diária repetível do consultor único.

## Decisão
Facade CLI `python -m scripts.workspace` como interface operacional primária; orquestra módulos existentes; degradação offline com seções UNAVAILABLE.

## Consequências
- Onboarding e SLA de briefing matinal viáveis  
- Dual-metric coverage obrigatória no comando coverage  
- Default REVIEW em scaffolds de edital/proposta  
