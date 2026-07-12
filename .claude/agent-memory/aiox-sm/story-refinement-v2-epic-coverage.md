---
name: story-refinement-v2-epic-coverage
description: Refinamento v2.0 de 4 stories do EPIC-COVERAGE-100PCT com ACs SQL, funções completas, riscos detalhados e métricas (2026-07-11)
metadata:
  type: project
---

# Story Refinement v2.0 — EPIC-COVERAGE-100PCT

Em 2026-07-11, refinei 4 stories de Draft para v2.0 com melhorias significativas:

## Stories Refinadas

1. **COVERAGE-1.8** (170 -> 481 linhas): Match Hierarquico Secretaria -> Prefeitura
   - ACs com SQL verificavel, funcao `build_entity_hierarchy()` completa com edge cases
   - Tratamento de camaras de vereadores (AC8: verificar bids proprios antes de aplicar hierarquia)
   - Tabela de riscos com probabilidade numerica, fallback plan, metricas quantificaveis
   - Scripts de teste e verificacao

2. **COVERAGE-1.9** (143 -> 615 linhas): SC Dados Abertos Municipality Fix
   - Schema da tabela, queries de diagnostico, funcao `infer_municipio_from_cnpj()` com 3 niveis
   - Rate limit Brasil API (2 req/s) com semaforo e retry
   - Cache mechanism em `data/cnpj_cache.json`, fallback plan se API offline
   - Antes/depois queries de validacao, testes unitarios

3. **COVERAGE-1.10** (122 -> 346 linhas): PCP Diagnostic & Fix
   - 6 hipoteses testaveis com procedimentos de teste para cada
   - Comandos curl exatos (6 testes diferentes)
   - Estrutura completa do relatorio de diagnostico
   - Planos de correcao e remocao (se inviavel), metricas

4. **COVERAGE-1.11** (149 -> 660 linhas): Geocoding 604 Entes Sem Coordenadas
   - Classe `Geocoder` completa com cache, batch processing, Haversine
   - Agrupamento por municipio (295 chamadas vs 604 entes = 51% de reducao)
   - Bounding box SC, validacao de coordenadas, edge cases
   - Cache em `data/geocode_cache.json` com estrutura padrao

## Padrao de Qualidade Aplicado

Referencia: `story-001.3-entity-name-matching.md` (modelo de qualidade)

Melhorias aplicadas a cada story:
- ACs com SQL verificavel (copiar e colar)
- Funcoes Python completas com edge cases, nao pseudo-codigo
- Tabela de riscos com Probabilidade, Impacto, Mitigacao concreta
- Comandos bash exatos (curl, psql, python)
- Fallback plans especificos
- Metricas de sucesso com queries de verificacao
- Testes unitarios com pytest
- CodeRabbit Integration com Focus Areas especificas
- Change Log completo

**Why:** Stories precisavam de mais detalhe implementavel para @dev e @data-engineer executarem sem ambiguidade.

**How to apply:** Este padrao de qualidade (ACs SQL, funcoes completas, riscos com probabilidade, fallback plans) deve ser usado como baseline para todas as stories futuras do EPIC-COVERAGE-100PCT e outros epics.
