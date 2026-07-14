---
story_id: B2G-DB-03
title: "Geocodificar 604 entidades não resolvidas"
status: ready
priority: P0
risk_level: STANDARD
effort: M
agent: "@dev"
epic: EPIC-MASTER-B2G-READINESS
phase: 2
depends_on: [B2G-FIX-03]
blocks: [B2G-INTEL-02]
---

# Story B2G-DB-03: Geocodificar 604 Entidades

## Problema

604 entidades na planilha seed não têm coordenadas (latitude/longitude). Sem coordenadas: impossível calcular distância Haversine, confirmar raio 200km, ou incluí-las no universo canônico. Essas 604 entidades são o "unresolved block" que impede coverage ≥95%.

**Causa raiz:** A planilha `Extra - alvos de licitação. R-0.xlsx` tem 2.085 linhas mas apenas ~1.481 com coordenadas. O geocode atual depende de coordenadas pré-preenchidas — não consulta API externa automaticamente.

Módulos existentes: `scripts/lib/geocode.py` (Haversine distance, cache IBGE), `scripts/fix/geocode_missing_entities.py` (13K LOC, nunca executado), `scripts/fix/resolve_unresolved_entities.py` (16K LOC, nunca executado).

## Escopo

**IN:** Extrair município/CEP de cada entidade sem coordenadas, consultar IBGE API de localidades, fallback dataset `kelvins/Municipios-Brasileiros`, atualizar planilha seed, recarregar `sc_public_entities`, reprojetar coverage, documentar método e confidence.

**OUT:** Geocodificação de endereço exato (não apenas centro do município), Google Maps API.

## Acceptance Criteria

1. **AC1:** Diagnóstico completo — quantos municípios únicos, quantos resolvíveis via IBGE, quantos requerem fallback
2. **AC2:** ≥90% das 604 entidades geocodificadas (coordenadas do centro do município)
3. **AC3:** Planilha seed atualizada com coordenadas (backup original preservado)
4. **AC4:** `sc_public_entities` recarregado — `raio_200km` recalculado para todas as entidades
5. **AC5:** Coverage reprojetado — novo denominador e % de cobertura reportados
6. **AC6:** Entidades que permanecem sem coordenadas documentadas com justificativa

## Tasks

- [ ] Task 1: Extrair municípios únicos das 604 entidades
- [ ] Task 2: Consultar IBGE API (`servicodados.ibge.gov.br/api/docs/localidades`) para cada município
- [ ] Task 3: Fallback dataset `kelvins/Municipios-Brasileiros` para não encontrados
- [ ] Task 4: Atualizar planilha seed com coordenadas (preservar backup)
- [ ] Task 5: Recarregar `sc_public_entities` via seed script
- [ ] Task 6: Recalcular `raio_200km` (Haversine de Florianópolis)
- [ ] Task 7: Executar `monitor.py --report-coverage` e documentar resultado

## Definition of Done

- [ ] 604 → ≤60 entidades sem coordenadas
- [ ] Planilha seed atualizada e backup preservado
- [ ] Coverage reprojetado com novo denominador
- [ ] Relatório documentando método e confidence por entidade

## Arquivos Afetados

- `Extra - alvos de licitação. R-0.xlsx` (atualizado)
- `scripts/fix/geocode_missing_entities.py`
- `scripts/fix/resolve_unresolved_entities.py`
- `db/seed/001_sc_entities.py`
- `scripts/lib/geocode.py`
