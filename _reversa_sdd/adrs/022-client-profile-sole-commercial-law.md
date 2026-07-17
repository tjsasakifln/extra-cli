# ADR-022 — Client Profile Sole Commercial Law (retroativo Reversa)

| Campo | Valor |
|-------|-------|
| **Status** | Accepted |
| **Data** | 2026-07-17 |
| **Fonte** | `docs/architecture/adr/ADR-022-client-profile-sole-commercial-law.md` |
| **Implementação** | `config/client_profiles/`, `opportunity_intel/profile.py`, workspace |
| **Confiança** | 🟢 decisão / 🟡 aderência total de scorers legados |

## Contexto
Scores explicáveis ponta a ponta exigem uma única lei comercial versionada.

## Decisão
Client Profile YAML é única fonte de pesos, exclusões e preferências para ranking/triagem/filtros default; labels humanos sobrescrevem modelo.

## Consequências
Hard exclusions (ex.: tracking de obra física fora de escopo plataforma); GO/REVIEW/NO_GO alinhados ao mandato Extra/CONFENGE.
