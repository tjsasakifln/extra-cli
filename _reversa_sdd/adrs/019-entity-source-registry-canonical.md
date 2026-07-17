# ADR-019 — Entity Source Registry Canonical (retroativo Reversa)

| Campo | Valor |
|-------|-------|
| **Status** | Accepted |
| **Data** | 2026-07-17 |
| **Fonte** | `docs/architecture/adr/ADR-019-entity-source-registry-canonical.md` |
| **Implementação** | `scripts/source_registry/`, mig `053_entity_source_registry.sql` |
| **Confiança** | 🟢 CONFIRMADO |

## Contexto
Registry de fontes (11) existia; faltava binding entidade→fonte→método→status para M2.

## Decisão
ESR como SoT operacional por entidade do universo 1093, com discovery, gap report e sync Postgres.

## Consequências
M2 calculável honestamente; crawls globais não bastam como prova de cobertura do universo.
