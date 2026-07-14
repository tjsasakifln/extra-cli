---
story_id: B2G-FIX-03
title: "Universo canônico único — eliminar 6 denominadores divergentes"
status: InReview
priority: P0
risk_level: STANDARD
effort: M
agent: "@dev"
epic: EPIC-MASTER-B2G-READINESS
phase: 0
depends_on: []
blocks: [B2G-DB-03, B2G-INTEL-02]
---

# Story B2G-FIX-03: Universo canônico único

## Problema

6 módulos diferentes usam 6 denominadores diferentes para o universo de entidades:

| Módulo | Denominador | Origem |
|--------|------------|--------|
| `manifest.py` (opportunity_intel) | 1.448 | Query sem filtro `raio_200km` |
| `target_universe.py` (contract_intel) | 1.093 | Haversine distance de Florianópolis |
| `coverage_manifest.json` | 1.697 | 1.093 dentro + 604 unresolved |
| PRD v2.0 | 1.481 | Universo confirmado com coordenadas |
| `sc_public_entities` count | 2.085 | Todas as entidades ativas SC |
| `consulting_readiness.py` | 1.000 | Hardcoded |

**Consequências:**
- `manifest.py` reporta cobertura de 265.95% (3.851/1.448 — matematicamente impossível)
- `entities_with_data: 3.851` conta entes de todo o Brasil, não só SC raio 200km
- `entities_without_data: -2.403` — valor negativo
- Impossível ter um único número de verdade para o negócio
- Viola Regra Não-Negociável #1: "Definição canônica única do universo"

## Causa Raiz

`_build_manifest()` em `manifest.py` executa query `entities_with_data` SEM filtrar `raio_200km = TRUE`. Conta entes de todo SC (3.851). Ao dividir pelo universo declarado (1.448), produz 265.95%. CNPJ8 não normalizado consistentemente entre módulos.

## Valor de Negócio

Um único número de cobertura confiável é pré-requisito para qualquer decisão de negócio. Sem ele, não é possível saber se a cobertura está melhorando ou piorando.

## Escopo

### IN
- Criar/atualizar `scripts/lib/universe.py` como fonte única de verdade
- Constante: `CANONICAL_UNIVERSE = 1093` (entes dentro do raio 200km com coordenadas)
- Função: `get_canonical_universe()` que consulta `sc_public_entities WHERE raio_200km = TRUE`
- Função: `get_conservative_population()` = incluídos + unresolved (nunca subestima)
- Atualizar `manifest.py` para usar `universe.py`
- Atualizar `consulting_readiness.py` para usar `universe.py`
- Atualizar `coverage_truth.py` para usar `universe.py`
- Corrigir query de `entities_with_data` com filtro `raio_200km = TRUE`
- Garantir CNPJ8 normalizado consistentemente (`LEFT(orgao_cnpj, 8)`)

### OUT
- Geocodificação das 604 entidades (B2G-DB-03)
- Correção de schema (B2G-FIX-04)

## Acceptance Criteria

### AC1: Módulo universo canônico
**Given** o módulo `scripts/lib/universe.py`
**When** `get_canonical_universe()` é chamado
**Then** retorna 1.093 (entes dentro do raio 200km)
**And** `get_conservative_population()` retorna 1.697 (1.093 + 604 unresolved)

### AC2: manifest.py usa universo canônico
**Given** `manifest.py` atualizado
**When** `python3 scripts/opportunity_intel/manifest.py` executa
**Then** coverage reportado está entre 39% e 65% (valor realista)
**And** `entities_with_data` ≤ 1.093
**And** `entities_without_data` ≥ 0

### AC3: consulting_readiness.py usa universo canônico
**Given** `consulting_readiness.py` atualizado
**When** `python3 scripts/consulting_readiness.py` executa
**Then** denominador usado é 1.093
**And** coverage reportado é consistente com manifest.py

### AC4: coverage_truth.py consistente
**Given** `coverage_truth.py` atualizado
**When** executa com universo canônico
**Then** reporta o mesmo denominador que manifest.py e consulting_readiness.py

### AC5: CNPJ8 normalizado
**Given** queries em todos os módulos
**When** comparam CNPJ de entidade
**Then** usam `LEFT(orgao_cnpj, 8)` consistentemente

### AC6: Sem regressões
**Given** as correções aplicadas
**When** testes de manifest, coverage_truth e consulting_readiness executam
**Then** passam sem falha

## Tasks

- [ ] Task 1: Refatorar `scripts/lib/universe.py` como módulo canônico
- [ ] Task 2: Corrigir `_build_manifest()` com filtro `raio_200km`
- [ ] Task 3: Atualizar `consulting_readiness.py` — remover hardcoded 1.000
- [ ] Task 4: Atualizar `coverage_truth.py` — usar `get_canonical_universe()`
- [ ] Task 5: Normalizar `LEFT(orgao_cnpj, 8)` em todas as queries
- [ ] Task 6: Rodar pytest de regressão

## Definition of Done

- [ ] 6 denominadores → 1 denominador canônico
- [ ] `manifest.py` reporta cobertura realista (não 265.95%)
- [ ] `entities_without_data` nunca negativo
- [ ] todos os módulos usam mesma definição de universo
- [ ] pytest sem falhas
- [ ] ruff check limpo nos arquivos alterados

## Arquivos Afetados

- `scripts/lib/universe.py`
- `scripts/opportunity_intel/manifest.py`
- `scripts/consulting_readiness.py`
- `scripts/coverage_truth.py`
- `scripts/contract_intel/target_universe.py`
