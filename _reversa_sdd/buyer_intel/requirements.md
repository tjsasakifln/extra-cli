# Requirements — Buyer Intelligence (`buyer_intel`)

> Writer re-extração 2026-07-17 | confiança majoritária 🟢

## Propósito
Perfil e ranking de órgãos compradores AEC no raio 200km.

## Requisitos funcionais
- RF-BI-01 Classificar objeto AEC por keywords 🟢
- RF-BI-02 Calcular BuyerProfile multi-fator (volume, HHI, vencimentos) 🟢
- RF-BI-03 CLI de ranking explicável 🟢

## Requisitos não-funcionais
- NFR-01 Fail-closed: ausência de evidência ≠ sucesso 🟢
- NFR-02 Logs estruturados / reasons explícitos em degradação 🟢
- NFR-03 Artefatos raw fora do git (ADR-020) 🟢

## Fora de escopo
- UI web multi-tenant
- Alteração do denominador 1093

## Fontes
- `scripts/buyer_intel/`
