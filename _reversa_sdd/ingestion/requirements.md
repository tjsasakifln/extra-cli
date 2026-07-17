# Requirements — Ingestion (top-level) (`ingestion`)

> Writer re-extração 2026-07-17 | confiança majoritária 🟢

## Propósito
Camada de ingestão top-level paralela a crawl/ingestion.

## Requisitos funcionais
- RF-IN-01 Pipeline de load transformável e observável 🟢
- RF-IN-02 Compatível com DSN e run_id de evidência 🟢

## Requisitos não-funcionais
- NFR-01 Fail-closed: ausência de evidência ≠ sucesso 🟢
- NFR-02 Logs estruturados / reasons explícitos em degradação 🟢
- NFR-03 Artefatos raw fora do git (ADR-020) 🟢

## Fora de escopo
- UI web multi-tenant
- Alteração do denominador 1093

## Fontes
- `scripts/ingestion/`
