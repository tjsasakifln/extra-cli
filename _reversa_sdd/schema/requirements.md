# Requirements — Schema Helpers / Official Acts (`schema`)

> Writer re-extração 2026-07-17 | confiança majoritária 🟢

## Propósito
Persistência de atos oficiais e auditoria de referências SQL.

## Requisitos funcionais
- RF-SC-01 OfficialActsStore upsert idempotente por hash 🟢
- RF-SC-02 Suportar resources, acts, classifications, links, matches 🟢
- RF-SC-03 audit_sql_references deve detectar refs quebradas 🟢

## Requisitos não-funcionais
- NFR-01 Fail-closed: ausência de evidência ≠ sucesso 🟢
- NFR-02 Logs estruturados / reasons explícitos em degradação 🟢
- NFR-03 Artefatos raw fora do git (ADR-020) 🟢

## Fora de escopo
- UI web multi-tenant
- Alteração do denominador 1093

## Fontes
- `scripts/schema/`
- `db/migrations/052_official_acts.sql`
