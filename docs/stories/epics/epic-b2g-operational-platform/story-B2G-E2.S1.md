---
story_id: B2G-E2.S1
title: "Entity source registry canônico — 1093 bindings"
status: InProgress
priority: P0
risk_level: STANDARD
effort: L
agent: "@dev"
epic: EPIC-B2G-OPERATIONAL-PLATFORM
vertical: E2
depends_on: []
blocks: [B2G-E2.S2, B2G-E1.S2, B2G-E2.S4]
adr: [ADR-019]
---

# Story B2G-E2.S1: Entity source registry (ESR) — 1093

## Contexto

Registry de fontes existe (`scripts/crawl/registry.py`); **não** há registry canônico entidade→fonte para o universo 1.093. Sem ESR, M2 e discovery não fecham.

## Valor de negócio

Base para provar cobertura operacional 95% e direcionar aquisição.

## Escopo

**IN:** Modelo ESR (tabela e/ou store versionável); bootstrap 1093 linhas; statuses applicable/not_applicable/unknown/blocked; CLI list/stats; testes integridade.

**OUT:** Discovery automático completo (E2.S2); 95% M2.

## Acceptance Criteria

1. **AC1**  
   **Given** universo `raio_200km` ativo,  
   **When** bootstrap ESR executa,  
   **Then** existem **1093** entidades com ≥1 binding row (unknown permitido).

2. **AC2**  
   **Given** source_id inválido,  
   **When** insert binding,  
   **Then** rejeitado (FK/validação contra registry de fontes).

3. **AC3**  
   **Given** ESR carregado,  
   **When** `stats`,  
   **Then** conta applicable / unknown / blocked / not_applicable.

4. **AC4**  
   **Given** export,  
   **When** gera JSON,  
   **Then** path operacional (output/, não commit raw) com schema documentado.

5. **AC5**  
   **Given** entidade sem qualquer fonte known,  
   **When** bootstrap,  
   **Then** binding `unknown` explícito (não omitir a entidade).

## Fontes de dados

- `sc_public_entities` (1093)
- `scripts/crawl/registry.py` (sources)
- Inferência inicial opcional: matches PNCP/CNPJ, artefatos sessão CIGA/SC Compras

## Dependências

Nenhuma hard; convive com L1 registry de fontes.

## Riscos

| Risco | Mitigação |
|-------|-----------|
| Inferência errada applicable | confidence=low + last_verified null |
| Duplicar entity_coverage semantics | ESR = applicability; evidence = success |

## Testes

- Unit: validação schema binding
- Integration: count == 1093 pós-bootstrap (DB test)
- Contract: source_id ∈ registry

## Evidência

- `output/registry/entity-source-registry.json` (gitignore)
- Contagem stats em log de teste

## Definition of Done

- [ ] AC1–5
- [ ] ADR-019 referenciado
- [ ] Sem commit de dump completo no git (stamp summary ok)

## Comandos de validação

```bash
pytest tests/ -k "entity_source_registry or esr_" -v
# Pós-impl (exemplo):
# python -m scripts.registry.esr bootstrap --universe 200km
# python -m scripts.registry.esr stats
```

## File List (dev)

- (a preencher)

## Change Log

| Data | Autor | Nota |
|------|-------|------|
| 2026-07-17 | Morgan (PM) | InProgress — implementação agents |
