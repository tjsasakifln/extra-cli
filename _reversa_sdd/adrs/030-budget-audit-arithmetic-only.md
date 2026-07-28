# ADR-030 — Budget audit apenas aritmético (non-legal)

- **Data:** 2026-07-28 (retroativo)
- **Status:** Aceito
- **Confiança:** 🟢

## Contexto
Auditoria de planilhas orçamentárias (BDI) é oferta comercial, mas claim jurídico é risco.

## Decisão
Módulo `budget_audit` classifica diferenças aritméticas/materialidade; interpreta percent points BR; **nunca** legal/ilegal/abusivo sem humano; BDI ≠ margem.

## Consequências
- Gates de campanha validam processo, não veredito jurídico.
- Hypothesis/adversarial para regressões numéricas.
