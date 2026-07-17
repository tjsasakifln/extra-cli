# Requirements — Entity Source Registry (`source_registry`)

> Writer re-extração 2026-07-17 | confiança majoritária 🟢

## Propósito
Mapear 1093 entidades do raio 200km para portais, plataformas, status de acesso, blockers e estratégia de coleta (ADR-019).

## Requisitos funcionais
- RF-SR-01 Sistema deve construir registry a partir do CSV universo + YAMLs de aplicabilidade/transparência 🟢
- RF-SR-02 Cada entidade deve ter canonical_id único e access_status controlado 🟢
- RF-SR-03 is_strict_operational deve decidir inclusão em M2 🟢
- RF-SR-04 Discovery deve gerar candidatos de URL e probe 🟢
- RF-SR-05 Gap report deve classificar blockers e emitir MD/JSON 🟢
- RF-SR-06 Sync opcional para tabela entity_source_registry 🟢

## Requisitos não-funcionais
- NFR-01 Fail-closed: ausência de evidência ≠ sucesso 🟢
- NFR-02 Logs estruturados / reasons explícitos em degradação 🟢
- NFR-03 Artefatos raw fora do git (ADR-020) 🟢

## Fora de escopo
- UI web multi-tenant
- Alteração do denominador 1093

## Fontes
- `scripts/source_registry/`
- `db/migrations/053_entity_source_registry.sql`
