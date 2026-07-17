# Design — Workspace CLI Facade (`workspace`)

> Writer 2026-07-17

## Contexto
Ver `_reversa_sdd/code-analysis.md` seção do módulo e ADRs 017–022 quando aplicável.

## Componentes
- `scripts/workspace/`
- `docs/architecture/adr/ADR-017-workspace-cli-facade.md`

## Fluxos
Ver `_reversa_sdd/flowcharts/` (coverage, source_registry, workspace, crawl, matching conforme módulo).

## Dados
Ver `_reversa_sdd/data-dictionary.md` e `erd-complete.md`.

## Decisões
- Reuso > reimplementação (workspace facade, registry SoT)
- Dual-metric e strict operational quando módulo toca cobertura
- Adapter FetchResult tipado quando módulo toca coleta

## Riscos
- 🟡 Duplicação com pastas históricas crawl/*
- 🔴 M2 operacional ainda 0/1093 (produto)
